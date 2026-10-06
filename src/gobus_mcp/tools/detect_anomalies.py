"""``gobus_detect_anomalies``: anomalias de tema e de entidade cientes do defeso (G2, F3).

Fluxo de ``build_anomaly_report`` (I/O aqui; a análise fica em ``analytics/``):

1. Em paralelo:
   - temas: ``ThemeRangeCounts`` nos ranges 3, 21, 7 e 28 (``theme_data``);
   - entidades: ``trendingEntities(50){… computedAt}`` → ``select_candidates`` (só a última
     execução, sem o piso antigo ``vr/wc ≥ 100``) → contexto de cada candidato
     (``entity`` + ``entityCoverage(DAY)`` + ``policyDetails``) com ``Semaphore(8)``;
   - snapshot de atividade das agências (``AgencyActivityService``, cache de 6 h);
   - republicadoras do catálogo (lista fixa se o catálogo cair).
2. Temas: share-of-voice com gate de cobertura de classificação (``build_themes_block``).
3. Entidades: ``entity_signal`` por candidato (janela fechada ``[D−7, D−1]``, baseline de
   28 dias ou pré-defeso na recuperação, sem republicadoras, classes com precedência).
4. ``domain_filter`` filtra os sinais; os gauges ``domains`` resumem todos os domínios.
5. ``AnomalyReport`` → Markdown completo (``content`` da tool de app) → ``summary`` = o
   mesmo texto até 6 KB → payload compacto do app (``compact_anomaly_payload``: séries só
   nos sinais anômalos, teto de normais, omitidos contados; ≤ 20 KB).

Cada bloco degrada sozinho (``unavailable``/``degraded`` com nota); a tool não cai.
Caches (``cache=``): ranking 10 min, contexto de entidade 30 min por (id, D), temas 5 min.
Orçamento: p50 ≤ 2 s com cache quente, ≤ 6 s a frio (o snapshot de atividade domina).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from gobus_mcp.agency_activity import ActivitySnapshot, AgencyActivityService, activity_status
from gobus_mcp.agency_catalog import EXTRA_REPUBLISHERS, AgencyCatalog
from gobus_mcp.analytics.entities import (
    MAX_CANDIDATES,
    CandidateSelection,
    EntityWindows,
    entity_signal,
    entity_windows,
    select_candidates,
    selection_notices,
)
from gobus_mcp.analytics.render import fit_summary, render_anomalies_markdown
from gobus_mcp.analytics.themes import (
    LONG_WINDOW,
    SHORT_WINDOW,
    THEME_RANGE_DAYS,
    Sensitivity,
    build_themes_block,
    parse_sensitivity,
)
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import (
    as_window,
    calendar_context,
    calendar_notices,
    now_brt,
    reference_date,
    rolling_range,
    rolling_window,
    utc_day_bounds,
)
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import (
    entity_ranking_status,
    failed_status,
    notices_for,
    worst_status,
)
from gobus_mcp.domains import Domain, parse_domain
from gobus_mcp.payloads.anomalies import (
    AnomalyReport,
    ClassifiedCoverage,
    EntitiesBlock,
    EntitySignal,
    ThemesBlock,
    ThemeWindows,
    UpstreamInfo,
    compact_anomaly_payload,
    summarize_domains,
)
from gobus_mcp.payloads.common import DataStatus, ReportStatus, Status
from gobus_mcp.theme_data import ThemeRangeFetch, fetch_theme_ranges

logger = logging.getLogger(__name__)

TRENDING_TTL = 600.0  # 10 min (o ranking roda 2×/dia)
ENTITY_CONTEXT_TTL = 1_800.0  # 30 min
ENTITY_CONCURRENCY = 8

# Republicadoras conhecidas, para quando o catálogo estiver fora do ar.
FALLBACK_REPUBLISHERS: frozenset[str] = (
    frozenset({"agencia_brasil", "tvbrasil", "ebc"}) | EXTRA_REPUBLISHERS
)

TITLE = "## Detector de Anomalias Comunicacionais"

_TRENDING_QUERY = """
query AnomalyTrendingEntities {
  trendingEntities(limit: 50) {
    entityId
    canonicalName
    type
    trendingScore
    volumeRatio
    windowCount
    windowAgencies
    computedAt
  }
}
"""

_ENTITY_CONTEXT_QUERY = """
query AnomalyEntityContext($id: String!, $dateFrom: String!, $dateTo: String!) {
  entity(id: $id) {
    entityId
    canonicalName
    type
    agencyKey
  }
  entityCoverage(entityId: $id, dateFrom: $dateFrom, dateTo: $dateTo, granularity: DAY) {
    period
    agencyKey
    articleCount
  }
  policyDetails(entityId: $id) {
    domain
  }
}
"""


# ── I/O ─────────────────────────────────────────────────────────────────────


@dataclass
class _EntityFetch:
    rows: list[dict] = field(default_factory=list)
    error: str | None = None
    selection: CandidateSelection | None = None
    contexts: list = field(default_factory=list)  # dict ou exceção, por candidato


async def _ranking_rows(client: GobusGraphQLClient, cache: TTLCache | None) -> list[dict]:
    async def load() -> list[dict]:
        data = await client.execute(_TRENDING_QUERY)
        return list(data.get("trendingEntities") or [])

    if cache is None:
        return await load()
    return await cache.get_or_load(("anomalies", "trending_entities"), load, TRENDING_TTL)


async def _contexts(
    client: GobusGraphQLClient,
    candidates: list[dict],
    windows: EntityWindows,
    cache: TTLCache | None,
) -> list:
    """Contexto de cada candidato (no máximo ``ENTITY_CONCURRENCY`` em voo). A cobertura
    vai de ``windows.coverage_range.start`` a D (``dateTo`` exclusivo)."""
    semaphore = asyncio.Semaphore(ENTITY_CONCURRENCY)
    date_from, date_to = utc_day_bounds(windows.coverage_range)

    async def one(entity_id: str) -> dict:
        async def load() -> dict:
            async with semaphore:
                return await client.execute(
                    _ENTITY_CONTEXT_QUERY,
                    {"id": entity_id, "dateFrom": date_from, "dateTo": date_to},
                )

        if cache is None:
            return await load()
        key = ("anomalies", "entity_context", entity_id, windows.today)
        return await cache.get_or_load(key, load, ENTITY_CONTEXT_TTL)

    return await asyncio.gather(
        *(one(c.get("entityId") or "") for c in candidates), return_exceptions=True
    )


async def _fetch_entities(
    client: GobusGraphQLClient,
    windows: EntityWindows,
    *,
    cache: TTLCache | None,
    max_candidates: int,
) -> _EntityFetch:
    try:
        rows = await _ranking_rows(client, cache)
    except Exception as exc:
        logger.warning("anomalias: ranking de entidades indisponível (%s)", exc)
        return _EntityFetch(error=str(exc) or type(exc).__name__)
    selection = select_candidates(rows, max_candidates=max_candidates)
    contexts = await _contexts(client, selection.candidates, windows, cache)
    return _EntityFetch(rows=rows, selection=selection, contexts=list(contexts))


# ── blocos ──────────────────────────────────────────────────────────────────


def _themes(
    fetch: ThemeRangeFetch | BaseException, sens: Sensitivity, *, now, today
) -> tuple[ThemesBlock, DataStatus]:
    if isinstance(fetch, BaseException):
        error, as_of = str(fetch) or type(fetch).__name__, now
    else:
        short, long = fetch.pair(*SHORT_WINDOW), fetch.pair(*LONG_WINDOW)
        if short is not None and long is not None:
            return build_themes_block(short, long, sens=sens, now=fetch.as_of, today=today)
        error, as_of = fetch.error_text(), fetch.as_of
    block = ThemesBlock(
        status="unavailable",
        note=f"Bloco de temas indisponível: falha ao consultar a graphql-api ({error}).",
        windows=ThemeWindows(
            short=rolling_window(SHORT_WINDOW[0], as_of),
            long=rolling_window(LONG_WINDOW[0], as_of),
        ),
        classified_coverage=ClassifiedCoverage(short=None, long=None),
        signals=[],
    )
    return block, failed_status("themes", error)


def _entities(
    fetch: _EntityFetch | BaseException,
    windows: EntityWindows,
    *,
    sens: Sensitivity,
    republishers: frozenset[str],
    republishers_fallback: bool,
    snapshot: ActivitySnapshot | None,
    now,
) -> tuple[EntitiesBlock, DataStatus, CandidateSelection | None]:
    window = as_window(windows.window, bucket_tz="UTC")
    baseline = as_window(
        windows.baseline,
        baseline_overlaps_blackout=windows.baseline_overlaps_blackout,
        bucket_tz="UTC",
    )
    if isinstance(fetch, BaseException) or fetch.error is not None or fetch.selection is None:
        error = (
            (str(fetch) or type(fetch).__name__)
            if isinstance(fetch, BaseException)
            else (fetch.error or "erro desconhecido")
        )
        block = EntitiesBlock(
            status="unavailable",
            note=f"Ranking de entidades indisponível: falha ao consultar a graphql-api ({error}).",
            window=window,
            baseline=baseline,
            candidates=0,
            upstream=UpstreamInfo(
                last_run_at=None, rows_total=0, rows_last_run=0, rows_legacy_floor=0
            ),
            signals=[],
        )
        return block, failed_status("entity_ranking", error), None

    ranking = entity_ranking_status(fetch.rows, now=now)
    selection = fetch.selection
    signals: list[EntitySignal] = []
    failures = 0
    for candidate, ctx in zip(selection.candidates, fetch.contexts, strict=True):
        entity_id = candidate.get("entityId")
        if isinstance(ctx, BaseException):
            failures += 1
            logger.warning("anomalias: contexto de %s indisponível (%s)", entity_id, ctx)
            continue
        try:
            signal = entity_signal(
                entity=ctx.get("entity") or {},
                coverage_rows=ctx.get("entityCoverage") or [],
                policy_domain=(ctx.get("policyDetails") or {}).get("domain"),
                windows=windows,
                sens=sens,
                republishers=republishers,
                activity=snapshot,
                candidate=candidate,
            )
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            # dado malformado de um candidato não derruba a tool
            failures += 1
            logger.warning("anomalias: contexto de %s malformado (%s)", entity_id, exc)
            continue
        signals.append(signal)
    signals.sort(key=lambda s: (-s.severity, s.name))

    status: Status = ranking.status
    if status == "unavailable" and signals:
        status = "degraded"  # o upstream envelheceu, mas os sinais foram recalculados
    notes: list[str] = []
    upstream = selection.upstream
    dropped = selection.dropped_floor + selection.dropped_stale
    if dropped:
        notes.append(
            f"{dropped} de {upstream.rows_total} linhas do ranking descartadas como candidatas "
            f"({selection.dropped_floor} do piso antigo, {selection.dropped_stale} de "
            "execuções anteriores)"
        )
    if not selection.candidates and upstream.rows_total:
        notes.append("nenhum candidato restou para recalcular")
    if failures:
        status = (
            "unavailable"
            if failures == len(selection.candidates)
            else worst_status([status, "degraded"])
        )
        notes.append(
            f"{failures} de {len(selection.candidates)} candidatos sem contexto (falha da "
            "consulta ou dado malformado)"
        )
    if republishers_fallback:
        status = worst_status([status, "degraded"])
        notes.append("catálogo indisponível: republicadoras por lista fixa")
    if status != "ok" and signals:
        notes.append("sinais recalculados pela cobertura diária (entityCoverage)")
    note = (notes[0][0].upper() + "; ".join(notes)[1:] + ".") if notes else None

    block = EntitiesBlock(
        status=status,
        note=note,
        window=window,
        baseline=baseline,
        candidates=len(selection.candidates),
        upstream=upstream,
        signals=signals,
    )
    return block, ranking, selection


def _report_status(themes: ThemesBlock, entities: EntitiesBlock) -> ReportStatus:
    statuses = (themes.status, entities.status)
    if all(s == "unavailable" for s in statuses):
        return "unavailable"
    if any(s != "ok" for s in statuses):
        return "partial"
    if not themes.signals and not entities.signals:
        return "empty"
    return "ok"


# ── builder e tool ──────────────────────────────────────────────────────────


async def build_anomaly_output(
    client: GobusGraphQLClient,
    *,
    sensitivity: str = "medium",
    domain_filter: str = "",
    catalog: AgencyCatalog | None = None,
    activity: AgencyActivityService | None = None,
    now=None,
    cache: TTLCache | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> tuple[AnomalyReport, str]:
    """``(payload do app, Markdown completo)``.

    O Markdown vai inteiro no ``content`` da tool; o payload traz o mesmo texto até 6 KB
    em ``summary`` e só os sinais que o app desenha (``compact_anomaly_payload``).
    Parâmetro inválido levanta ``ValueError`` com as opções (antes de qualquer I/O)."""
    sens_name, sens = parse_sensitivity(sensitivity)
    domain: Domain | None = parse_domain(domain_filter)
    now = now or now_brt()
    today = reference_date(now)
    catalog = catalog or AgencyCatalog(client)
    activity = activity or AgencyActivityService(client, catalog)
    windows = entity_windows(today)

    theme_fetch, entity_fetch, snapshot_r, republishers_r = await asyncio.gather(
        fetch_theme_ranges(client, THEME_RANGE_DAYS, now=now, cache=cache),
        _fetch_entities(client, windows, cache=cache, max_candidates=max_candidates),
        activity.snapshot(today),
        catalog.republishers(),
        return_exceptions=True,
    )

    snapshot = None if isinstance(snapshot_r, BaseException) else snapshot_r
    activity_data = activity_status(
        snapshot, error=str(snapshot_r) if isinstance(snapshot_r, BaseException) else None
    )
    republishers_fallback = isinstance(republishers_r, BaseException)
    republishers = FALLBACK_REPUBLISHERS if republishers_fallback else republishers_r

    themes_block, theme_status = _themes(theme_fetch, sens, now=now, today=today)
    entities_block, ranking_status, selection = _entities(
        entity_fetch,
        windows,
        sens=sens,
        republishers=republishers,
        republishers_fallback=republishers_fallback,
        snapshot=snapshot,
        now=now,
    )
    domains = summarize_domains(themes_block.signals, entities_block.signals)
    if domain is not None:
        themes_block = themes_block.model_copy(
            update={"signals": [t for t in themes_block.signals if t.domain == domain]}
        )
        entities_block = entities_block.model_copy(
            update={"signals": [e for e in entities_block.signals if e.domain == domain]}
        )

    statuses = [theme_status, ranking_status, activity_data]
    notices = calendar_notices(
        today,
        baselines=[rolling_range(SHORT_WINDOW[1], today), rolling_range(LONG_WINDOW[1], today)],
        silenced_agencies=len(snapshot.silenced) if snapshot else None,
    )
    notices += notices_for(statuses)
    if selection is not None:
        notices += selection_notices(selection)

    report = AnomalyReport(
        summary="",
        status=_report_status(themes_block, entities_block),
        generated_at=now,
        reference_date=today,
        params={"sensitivity": sens_name, "domain_filter": domain.value if domain else None},
        calendar=calendar_context(
            today,
            silenced_agencies=len(snapshot.silenced) if snapshot else None,
            resumed_agencies=len(snapshot.resumed_after_blackout) if snapshot else None,
        ),
        data_status=statuses,
        notices=notices,
        thresholds=sens.thresholds(),
        themes=themes_block,
        entities=entities_block,
        domains=domains,
    )
    markdown = render_anomalies_markdown(report, max_bytes=None)
    report = report.model_copy(update={"summary": fit_summary(markdown)})
    return compact_anomaly_payload(report), markdown


async def build_anomaly_report(client: GobusGraphQLClient, **kwargs) -> AnomalyReport:
    """O payload do app (``AnomalyReport`` compacto, ``summary`` ≤ 6 KB); mesmos parâmetros
    de ``build_anomaly_output``."""
    report, _ = await build_anomaly_output(client, **kwargs)
    return report


def invalid_params_markdown(error: ValueError) -> str:
    return f"{TITLE}\n\n**Parâmetro inválido:** {error}"


def invalid_params(sensitivity: str, domain_filter: str) -> str | None:
    """Markdown com as opções se a sensibilidade ou o domínio é inválido; ``None`` se ok.
    Não consulta a API."""
    try:
        parse_sensitivity(sensitivity)
        parse_domain(domain_filter)
    except ValueError as exc:
        return invalid_params_markdown(exc)
    return None


async def detect_anomalies(
    client: GobusGraphQLClient,
    sensitivity: str = "medium",
    domain_filter: str = "",
    *,
    catalog: AgencyCatalog | None = None,
    activity: AgencyActivityService | None = None,
    now=None,
    cache: TTLCache | None = None,
) -> str:
    """Markdown completo do detector de anomalias (o ``content`` da tool de app; o
    ``summary`` do payload é o mesmo texto até 6 KB).

    Parâmetro inválido (sensibilidade ou domínio) devolve as opções, sem consultar a API.
    """
    invalid = invalid_params(sensitivity, domain_filter)
    if invalid is not None:
        return invalid
    _, markdown = await build_anomaly_output(
        client,
        sensitivity=sensitivity,
        domain_filter=domain_filter,
        catalog=catalog,
        activity=activity,
        now=now,
        cache=cache,
    )
    return markdown
