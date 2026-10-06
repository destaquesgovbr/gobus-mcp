"""``gobus_get_message_coherence``: coerência de mensagem entre agências (F5, G3).

Fluxo de ``build_coherence_output`` (I/O aqui; a análise fica em ``analytics.coherence``):

1. Parâmetros, sem I/O: exatamente um entre ``entity_id`` e ``theme``; janela padrão
   D−14..D−1 (dias em BRT), no máximo 92 dias; ``agencies`` validadas pelo catálogo
   (aliases curados antes do difflib: ``ms`` → ``saude``).
2. Assunto:
   - ``entity_id`` com cara de id (``Q123``, ``dgb_…``) → ``entity(id)``, em paralelo com a
     página 1 e o prior; um nome → ``entitySearch(limit:3)``, escolhendo o maior
     ``articleCount`` e listando as outras como alternativas;
   - ``theme`` → label L1 pela taxonomia (``themes``, cache 24 h): igualdade sem acento,
     senão prefixo ou trecho único. A cobertura de classificação **da janela** é medida por
     aliases de contagem (total contra Σ labels L1): aviso ``THEMES_UNCLASSIFIED`` dinâmico
     (some quando o re-enriquecimento e o reindex cobrem a janela).
3. ``articles(limit:250, page, filter, sort:DATE)``: página 1; com ``found > 250``, páginas
   2–4 em gather (teto de 1000 → ``SAMPLE_TRUNCATED``). Sem ``content`` (pesado).
4. Tom: aliases de contagem ``articles(limit:1, filter:{…, agencies:[a], sentiment:[l]})
   {found}`` para os 12 maiores emissores (mais o total por agência se a amostra foi
   truncada). Uma requisição; a query é gerada por ``counts_query`` (forma validada pelo
   teste de contrato via ``_COUNTS_SAMPLE_QUERY``).
5. Só entidade, em paralelo com a página 1: ``entityCoverage(DAY)`` (Postgres) dos 30 dias
   antes da janela e da própria janela, numa chamada (com ``agencies``, só as linhas dessas
   agências, a mesma base do ``found``):
   - "início truncado" quando a taxa diária do prior ≥ metade da taxa da janela;
   - conferência do índice de busca: ``found`` do Typesense contra o Postgres na janela
     (``indexing_lag``, aviso ``INDEXING_LAG``). O filtro ``entityCanonical`` depende do
     reindex; sem ele (0 contra N), o relatório fica indisponível em vez de "nenhum artigo".
6. ``assess`` → ``CoherenceReport`` → Markdown (``summary`` = o mesmo texto até 6 KB).

Típico: 3–4 requisições em 1–2,5 s. Cada fonte degrada sozinha; a tool não cai.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from gobus_mcp.agency_catalog import AgencyCatalog, normalize_code
from gobus_mcp.analytics.coherence import (
    PRIOR_DAYS,
    TONE_LABELS,
    Assessment,
    CoherenceArticle,
    assess,
    excluded_entities,
    parse_article,
    split_agencies,
    truncated_start,
)
from gobus_mcp.analytics.framing import normalize_text
from gobus_mcp.analytics.render import fit_summary, render_coherence_markdown
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import (
    BLACKOUTS,
    CLASSIFIER_CUTOFF,
    DateRange,
    as_window,
    brt_bounds,
    calendar_context,
    classifier_changed_within,
    now_brt,
    reference_date,
    utc_day_bounds,
)
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import (
    failed_status,
    indexing_lag_status,
    notices_for,
    share_status,
    theme_coverage_status,
)
from gobus_mcp.payloads.coherence import (
    DIMENSION_ORDER,
    DIMENSION_WEIGHTS,
    MAX_ALTERNATIVES,
    CoherenceDimension,
    CoherenceIndex,
    CoherenceReport,
    CoherenceSubject,
    EntityAlternative,
    IndexStatus,
    PriorInfo,
    RepublishersBlock,
    SampleInfo,
)
from gobus_mcp.payloads.common import DataStatus, Notice, ReportStatus
from gobus_mcp.tools.detect_anomalies import FALLBACK_REPUBLISHERS

logger = logging.getLogger(__name__)

TITLE = "## Coerência de Mensagem"
DEFAULT_DAYS = 14
MAX_WINDOW_DAYS = 92
PAGE_SIZE = 250
MAX_PAGES = 4
SAMPLE_CAP = PAGE_SIZE * MAX_PAGES
MAX_TONE_AGENCIES = 12
TAXONOMY_TTL = 86_400.0
NAMES_DEADLINE = 2.0  # segundos desde o início: depois disso a tabela usa os códigos
SENTIMENT_MIN_COVERAGE = 0.5

_ID_RE = re.compile(r"^(Q\d+|dgb_\S+)$")

_ENTITY_QUERY = """
query CoherenceEntity($id: String!) {
  entity(id: $id) {
    entityId
    canonicalName
    type
  }
}
"""

_ENTITY_SEARCH_QUERY = """
query CoherenceEntitySearch($query: String!) {
  entitySearch(query: $query, limit: 3) {
    entityId
    canonicalName
    type
    articleCount
  }
}
"""

_THEMES_QUERY = """
query CoherenceThemes {
  themes {
    label
  }
}
"""

_ARTICLES_QUERY = """
query CoherenceArticles($filter: ArticleFilter!, $page: Int!) {
  articles(limit: 250, page: $page, filter: $filter, sort: DATE) {
    found
    page
    articles {
      uniqueId
      title
      agency
      agencyName
      publishedAt
      subtitle
      editorialLead
      summary
      tags
      features {
        entities {
          canonicalId
          text
          type
          salience
        }
      }
    }
  }
}
"""

_COVERAGE_QUERY = """
query CoherenceCoverage($id: String!, $dateFrom: String!, $dateTo: String!) {
  entityCoverage(entityId: $id, dateFrom: $dateFrom, dateTo: $dateTo, granularity: DAY) {
    period
    agencyKey
    articleCount
  }
}
"""


def counts_query(n: int) -> str:
    """Query de contagem com ``n`` aliases ``cK: articles(limit: 1, filter: $fK) { found }``
    (tom por agência × rótulo e cobertura de temas, numa requisição)."""
    if n < 1:
        raise ValueError("counts_query exige n >= 1")
    params = ", ".join(f"$f{i}: ArticleFilter!" for i in range(n))
    aliases = "\n".join(f"  c{i}: articles(limit: 1, filter: $f{i}) {{ found }}" for i in range(n))
    return f"query CoherenceCounts({params}) {{\n{aliases}\n}}\n"


# Forma da query gerada, validada pelo teste de contrato (o gerador só muda o número de aliases).
_COUNTS_SAMPLE_QUERY = counts_query(2)


# ── parâmetros ──────────────────────────────────────────────────────────────


class CoherenceInputError(ValueError):
    """Erro para o usuário (parâmetro, entidade, tema ou agência); vira Markdown."""

    def __init__(self, label: str, message: str) -> None:
        self.label = label
        super().__init__(message)

    def markdown(self) -> str:
        return f"{TITLE}\n\n**{self.label}:** {self}"


@dataclass(frozen=True)
class CoherenceParams:
    entity: str | None
    theme: str | None
    agencies: list[str] | None
    window: DateRange


def _fmt(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _parse_date(value: str | None, name: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise CoherenceInputError(
            "Parâmetro inválido", f"data inválida em {name}: '{text}' (use AAAA-MM-DD)."
        ) from None


def parse_params(
    entity_id: str | None,
    theme: str | None,
    agencies: list[str] | None,
    date_from: str | None,
    date_to: str | None,
    *,
    today: date,
) -> CoherenceParams:
    """Valida as entradas sem I/O. Janela padrão D−14..D−1; só ``date_from`` → 14 dias a
    partir dele, limitados a ontem; máximo de 92 dias."""
    entity = (entity_id or "").strip()
    subject_theme = (theme or "").strip()
    if bool(entity) == bool(subject_theme):
        raise CoherenceInputError(
            "Parâmetro inválido",
            'informe exatamente um entre entity_id (ex.: "Q575545" ou "Bolsa Família") e '
            'theme (label L1 de tema, ex.: "Saúde").',
        )
    start = _parse_date(date_from, "date_from")
    end = _parse_date(date_to, "date_to")
    yesterday = today - timedelta(days=1)
    if end is None:
        end = yesterday if start is None else max(start, min(start + timedelta(13), yesterday))
    if start is None:
        start = end - timedelta(days=DEFAULT_DAYS - 1)
    if end > today:
        raise CoherenceInputError(
            "Parâmetro inválido", f"date_to ({_fmt(end)}) está no futuro (hoje é {_fmt(today)})."
        )
    if start > end:
        raise CoherenceInputError(
            "Parâmetro inválido",
            f"date_from ({_fmt(start)}) precisa ser anterior ou igual a date_to ({_fmt(end)}).",
        )
    days = (end - start).days + 1
    if days > MAX_WINDOW_DAYS:
        raise CoherenceInputError(
            "Parâmetro inválido",
            f"janela de {days} dias; o máximo é {MAX_WINDOW_DAYS} dias.",
        )
    cleaned = [a.strip() for a in agencies or [] if a and a.strip()]
    return CoherenceParams(
        entity=entity or None,
        theme=subject_theme or None,
        agencies=cleaned or None,
        window=DateRange(start, end),
    )


async def _validate_agencies(
    catalog: AgencyCatalog, agencies: list[str] | None
) -> tuple[list[str] | None, str | None]:
    """Códigos validados (ordem preservada, sem repetição) e uma nota se o catálogo caiu."""
    if not agencies:
        return None, None
    codes: list[str] = []
    try:
        for agency in agencies:
            check = await catalog.validate(agency)
            if not check.ok:
                raise CoherenceInputError("Agência inválida", check.message)
            codes.append(check.code)
    except CoherenceInputError:
        raise
    except Exception as exc:  # catálogo fora do ar: segue com os códigos normalizados
        logger.warning("coerência: catálogo indisponível para validar agências (%s)", exc)
        codes = [normalize_code(a) for a in agencies]
        note = f"Catálogo indisponível: agências não validadas ({exc})."
        return list(dict.fromkeys(codes)), note
    return list(dict.fromkeys(codes)), None


# ── assunto ─────────────────────────────────────────────────────────────────


def looks_like_id(value: str) -> bool:
    """``Q123`` (Wikidata) ou ``dgb_…`` (id interno)."""
    return bool(_ID_RE.match(value))


async def _search_entity(client: GobusGraphQLClient, query: str) -> CoherenceSubject:
    try:
        data = await client.execute(_ENTITY_SEARCH_QUERY, {"query": query})
    except Exception as exc:
        raise CoherenceInputError(
            "Entidade não resolvida",
            f"falha ao buscar '{query}' na graphql-api ({exc}). Informe o entityId "
            "(gobus_resolve_entity).",
        ) from None
    rows: dict[str, dict] = {}
    for row in data.get("entitySearch") or []:
        if row.get("entityId") and row["entityId"] not in rows:
            rows[row["entityId"]] = row
    if not rows:
        raise CoherenceInputError(
            "Entidade não encontrada",
            f"nenhuma entidade para '{query}'. Use gobus_resolve_entity para descobrir o entityId.",
        )
    ordered = list(rows.values())
    best = max(ordered, key=lambda r: (r.get("articleCount") or 0, -ordered.index(r)))
    alternatives = [
        EntityAlternative(
            entity_id=r["entityId"],
            name=r.get("canonicalName") or r["entityId"],
            type=r.get("type"),
            article_count=r.get("articleCount"),
        )
        for r in ordered
        if r is not best
    ]
    return CoherenceSubject(
        kind="entity",
        id=best["entityId"],
        label=best.get("canonicalName") or best["entityId"],
        type=best.get("type"),
        resolved_by="search",
        query=query,
        alternatives=alternatives[:MAX_ALTERNATIVES],
    )


async def _taxonomy(client: GobusGraphQLClient, cache: TTLCache | None) -> list[str]:
    async def load() -> list[str]:
        data = await client.execute(_THEMES_QUERY)
        return [t["label"] for t in data.get("themes") or [] if t.get("label")]

    if cache is None:
        return await load()
    return await cache.get_or_load(("coherence", "taxonomy"), load, TAXONOMY_TTL)


def resolve_theme(theme: str, labels: list[str]) -> str:
    """Label L1 para ``theme``: igualdade sem acento; senão prefixo único; senão trecho
    único. Sem casamento (ou ambíguo) levanta ``CoherenceInputError`` com sugestões."""
    key = normalize_text(theme)
    by_norm = {normalize_text(label): label for label in labels}
    if key in by_norm:
        return by_norm[key]
    for candidates in (
        [label for norm, label in by_norm.items() if norm.startswith(key)],
        [label for norm, label in by_norm.items() if key and key in norm],
    ):
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            options = ", ".join(f'"{c}"' for c in candidates)
            raise CoherenceInputError(
                "Tema ambíguo", f'"{theme}" casa com várias labels L1: {options}.'
            )
    close = difflib.get_close_matches(key, list(by_norm), n=3, cutoff=0.5)
    hint = " Você quis dizer " + ", ".join(f'"{by_norm[c]}"' for c in close) + "?" if close else ""
    raise CoherenceInputError(
        "Tema não encontrado",
        f'"{theme}" não é uma label L1 de tema.{hint} Lista completa em gobus://themes.',
    )


# ── consultas ───────────────────────────────────────────────────────────────


async def _page(client: GobusGraphQLClient, filt: dict, page: int) -> dict:
    data = await client.execute(_ARTICLES_QUERY, {"filter": filt, "page": page})
    return data.get("articles") or {}


async def _counts(client: GobusGraphQLClient, filters: list[dict]) -> list[int]:
    if not filters:
        return []
    variables = {f"f{i}": f for i, f in enumerate(filters)}
    data = await client.execute(counts_query(len(filters)), variables)
    return [int((data.get(f"c{i}") or {}).get("found") or 0) for i in range(len(filters))]


def _prior_range(window: DateRange) -> DateRange:
    return DateRange(window.start - timedelta(days=PRIOR_DAYS), window.start - timedelta(days=1))


async def _coverage(client: GobusGraphQLClient, entity_id: str, window: DateRange) -> list[dict]:
    """``entityCoverage(DAY)`` (Postgres) dos 30 dias antes da janela **e** da janela, numa
    chamada: o prior do "início truncado" e a referência para conferir o Typesense."""
    rng = DateRange(_prior_range(window).start, window.end)
    date_from, date_to = utc_day_bounds(rng)  # dateTo exclusivo
    data = await client.execute(
        _COVERAGE_QUERY, {"id": entity_id, "dateFrom": date_from, "dateTo": date_to}
    )
    return list(data.get("entityCoverage") or [])


@dataclass(frozen=True)
class _PgCoverage:
    """Contagens do Postgres por dia UTC: antes da janela e dentro dela."""

    prior: int
    window: int


def _split_coverage(
    rows: list[dict], window: DateRange, agencies: list[str] | None = None
) -> _PgCoverage:
    """Soma o ``entityCoverage`` antes e dentro da janela. Com ``agencies``, só as linhas
    dessas agências: o ``found`` do Typesense já vem filtrado por elas, e o prior precisa
    da mesma base para comparar taxas."""
    allowed = set(agencies) if agencies else None
    prior = inside = 0
    for row in rows:
        if allowed is not None and row.get("agencyKey") not in allowed:
            continue
        try:
            day = date.fromisoformat(str(row.get("period") or "")[:10])
        except ValueError:
            continue
        count = int(row.get("articleCount") or 0)
        if day < window.start:
            prior += count
        elif day <= window.end:
            inside += count
    return _PgCoverage(prior, inside)


@dataclass
class _CatalogInfo:
    republishers: frozenset[str]
    codes: frozenset[str]
    fallback: bool = False


async def _catalog_info(catalog: AgencyCatalog) -> _CatalogInfo:
    """Republicadoras e códigos (``agencies``, rápido). Os nomes vêm à parte: a consulta de
    nomes do catálogo é a mais lenta (~1,3–1,9 s a frio) e não pode segurar a análise."""
    try:
        return _CatalogInfo(await catalog.republishers(), await catalog.codes())
    except Exception as exc:
        logger.warning("coerência: catálogo indisponível (%s)", exc)
        return _CatalogInfo(FALLBACK_REPUBLISHERS, frozenset(), fallback=True)


# Tarefas de nomes que passaram do prazo: seguem em segundo plano e enchem o cache do
# catálogo para a próxima chamada (referência guardada para não serem coletadas).
_BACKGROUND: set[asyncio.Task] = set()


def _detach(task: asyncio.Task) -> None:
    """Deixa a carga de nomes terminar em segundo plano (enche o cache do catálogo)."""
    if not task.done():
        _BACKGROUND.add(task)
        task.add_done_callback(_BACKGROUND.discard)


async def _names_within(task: asyncio.Task, deadline: float) -> dict[str, str]:
    """Nomes do catálogo se chegarem até ``deadline`` (``time.monotonic``); senão ``{}``
    (a tabela mostra os códigos) e a carga continua em segundo plano."""
    timeout = max(0.0, deadline - time.monotonic())
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        return task.result() if not task.exception() else {}
    _detach(task)
    return {}


def _error_text(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


# ── montagem ────────────────────────────────────────────────────────────────


@dataclass
class _Fetch:
    found: int = 0
    rows: list[dict] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    pages_requested: int = 1


def _window_notices(window: DateRange, *, theme_path: bool) -> list[Notice]:
    """Avisos de calendário da **janela** (não da data de hoje)."""
    notices: list[Notice] = []
    for period in BLACKOUTS:
        span = f"{period.start.strftime('%d/%m')}–{_fmt(period.end)}"
        if window.start <= period.end and period.start <= window.end:
            notices.append(
                Notice(
                    code="ELECTORAL_BLACKOUT",
                    severity="info",
                    message=(
                        f"A janela cruza o {period.label.lower()} ({span}): parte das "
                        "agências está calada e as republicadoras pesam mais no volume."
                    ),
                    since=period.start,
                    affects=["agencies"],
                )
            )
        recovery_start = period.end + timedelta(days=1)
        if window.start <= period.recovery_until and recovery_start <= window.end:
            notices.append(
                Notice(
                    code="POST_BLACKOUT_RECOVERY",
                    severity="info",
                    message=(
                        f"A janela cruza a recuperação pós-defeso (até "
                        f"{_fmt(period.recovery_until)}): agências retomando a publicação "
                        "podem parecer atrasadas ou dessincronizadas."
                    ),
                    since=recovery_start,
                    affects=["timing"],
                )
            )
    if theme_path and CLASSIFIER_CUTOFF and classifier_changed_within(window):
        notices.append(
            Notice(
                code="CLASSIFIER_CHANGED",
                severity="warn",
                message=(
                    f"A janela cruza a troca do classificador de temas ({_fmt(CLASSIFIER_CUTOFF)}): "
                    "o filtro por tema mistura dois modelos."
                ),
                since=CLASSIFIER_CUTOFF,
                affects=["subject"],
            )
        )
    return notices


def _empty_dimensions(detail: str) -> list[CoherenceDimension]:
    return [
        CoherenceDimension(
            key=k,
            weight=DIMENSION_WEIGHTS[k],
            effective_weight=None,
            value=None,
            status="unavailable",
            detail=detail,
        )
        for k in DIMENSION_ORDER
    ]


def _report_status(
    index_status: IndexStatus,
    assessment: Assessment | None,
    statuses: list[DataStatus],
    fetch: _Fetch,
) -> ReportStatus:
    if index_status == "unavailable":
        return "unavailable"
    if index_status == "no_articles":
        return "empty"
    partial = (
        index_status == "insufficient"
        or fetch.page_errors
        or fetch.found > len(fetch.rows)
        or any(s.status != "ok" for s in statuses)
        or (assessment is not None and any(d.status != "ok" for d in assessment.dimensions))
    )
    return "partial" if partial else "ok"


def _truncation_notice(fetch: _Fetch, fetched: int, oldest: datetime | None) -> Notice | None:
    parts = []
    if fetch.found > SAMPLE_CAP:
        since = f" (desde {oldest.strftime('%d/%m')})" if oldest else ""
        parts.append(
            f"Amostra limitada aos {SAMPLE_CAP} artigos mais recentes de {fetch.found}{since}: "
            "timing, âncoras e enquadramento usam só a amostra."
        )
    if fetch.page_errors:
        parts.append(
            f"Páginas seguintes indisponíveis ({'; '.join(fetch.page_errors)}): a análise usa "
            f"{fetched} de {fetch.found} artigos."
        )
    if not parts:
        return None
    return Notice(
        code="SAMPLE_TRUNCATED",
        severity="warn",
        message=" ".join(parts),
        since=None,
        affects=["sample"],
    )


async def build_coherence_output(
    client: GobusGraphQLClient,
    *,
    entity_id: str = "",
    theme: str = "",
    agencies: list[str] | None = None,
    date_from: str = "",
    date_to: str = "",
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
    cache: TTLCache | None = None,
) -> tuple[CoherenceReport, str]:
    """``(CoherenceReport, Markdown completo)``.

    Levanta ``CoherenceInputError`` (parâmetro inválido, entidade ou tema não encontrado,
    agência inválida) antes de buscar artigos; falhas de dados degradam o relatório."""
    started = time.monotonic()
    now = now or now_brt()
    today = reference_date(now)
    params = parse_params(entity_id, theme, agencies, date_from, date_to, today=today)
    catalog = catalog or AgencyCatalog(client)
    agency_codes, agency_note = await _validate_agencies(catalog, params.agencies)
    window = params.window
    start_iso, end_iso = brt_bounds(window)
    base: dict = {"startDate": start_iso, "endDate": end_iso}
    if agency_codes:
        base["agencies"] = agency_codes
    notes = [agency_note] if agency_note else []
    statuses: list[DataStatus] = []

    # ── assunto + página 1 (+ prior, catálogo, cobertura de temas) em paralelo ──
    entity_task = None
    labels: list[str] = []
    if params.entity is not None:
        if looks_like_id(params.entity):
            subject = CoherenceSubject(
                kind="entity", id=params.entity, label=params.entity, type=None, resolved_by="id"
            )
            entity_task = client.execute(_ENTITY_QUERY, {"id": params.entity})
        else:
            subject = await _search_entity(client, params.entity)
        filt = {"entityCanonical": [subject.id], **base}
    else:
        try:
            labels = await _taxonomy(client, cache)
            label = resolve_theme(params.theme, labels) if labels else params.theme
            resolved_by = "taxonomy" if labels else "literal"
        except CoherenceInputError:
            raise
        except Exception as exc:
            logger.warning("coerência: taxonomia de temas indisponível (%s)", exc)
            statuses.append(failed_status("themes", exc))
            label, resolved_by, labels = params.theme, "literal", []
        subject = CoherenceSubject(
            kind="theme",
            id=None,
            label=label,
            type=None,
            resolved_by=resolved_by,
            query=params.theme,
        )
        filt = {**base, "themeLabel": label}

    async def none() -> None:
        return None

    # Nomes das agências em paralelo com tudo (a consulta mais lenta a frio); só a tabela
    # final espera por eles, até NAMES_DEADLINE.
    names_task = asyncio.ensure_future(catalog.display_names())  # nunca levanta

    coverage_filters = [dict(base)] + [{**base, "themeLabel": lbl} for lbl in labels]
    entity_r, page1_r, pg_result, coverage_result, catalog_info = await asyncio.gather(
        entity_task if entity_task is not None else none(),
        _page(client, filt, 1),
        _coverage(client, subject.id, window) if subject.kind == "entity" else none(),
        _counts(client, coverage_filters) if labels else none(),
        _catalog_info(catalog),
        return_exceptions=True,
    )
    if isinstance(catalog_info, BaseException):  # defensivo: _catalog_info não levanta
        catalog_info = _CatalogInfo(FALLBACK_REPUBLISHERS, frozenset(), fallback=True)
    if catalog_info.fallback:
        notes.append(
            "Catálogo indisponível: republicadoras por lista fixa e sem exclusão das "
            "entidades das agências (dgb_{código})."
        )

    if subject.kind == "entity" and subject.resolved_by == "id":
        if isinstance(entity_r, BaseException):
            notes.append(f"Nome da entidade indisponível ({_error_text(entity_r)}).")
        elif (entity_r or {}).get("entity"):
            node = entity_r["entity"]
            subject = subject.model_copy(
                update={"label": node.get("canonicalName") or subject.id, "type": node.get("type")}
            )
    if subject.kind == "theme" and labels:
        if isinstance(coverage_result, BaseException):
            statuses.append(failed_status("themes", coverage_result))
        else:
            total, classified = coverage_result[0], sum(coverage_result[1:])
            scope = f"da janela {window.start.strftime('%d/%m')}–{_fmt(window.end)}"
            statuses.append(theme_coverage_status(classified, total, days=window.days, scope=scope))

    # Postgres (entityCoverage) contra o Typesense (articles.found) na janela: o filtro
    # entityCanonical do Typesense depende do reindex; sem ele, "nenhum artigo" mentiria.
    pg: _PgCoverage | None = None
    span = f"{window.start.strftime('%d/%m')}–{_fmt(window.end)}"
    if subject.kind == "entity":
        if isinstance(pg_result, BaseException):
            notes.append(
                f"Cobertura do Postgres indisponível ({_error_text(pg_result)}): sem prior e "
                "sem conferência do índice de busca."
            )
        elif pg_result is not None:
            pg = _split_coverage(pg_result, window, agency_codes)

    fetch = _Fetch()
    common = dict(
        generated_at=now,
        reference_date=today,
        params={
            "entity_id": subject.id if subject.kind == "entity" else None,
            "theme": subject.label if subject.kind == "theme" else None,
            "agencies": agency_codes,
            "date_from": window.start.isoformat(),
            "date_to": window.end.isoformat(),
        },
        calendar=calendar_context(today),
        window=as_window(window, bucket_tz="America/Sao_Paulo"),
    )
    window_notices = _window_notices(window, theme_path=subject.kind == "theme")

    def finish(report: CoherenceReport) -> tuple[CoherenceReport, str]:
        _detach(names_task)
        markdown = render_coherence_markdown(report, max_bytes=None)
        return report.model_copy(update={"summary": fit_summary(markdown)}), markdown

    def without_index(index_status: IndexStatus, note: str, detail: str) -> CoherenceReport:
        return CoherenceReport(
            summary="",
            status=_report_status(index_status, None, statuses, fetch),
            data_status=statuses,
            notices=window_notices + notices_for(statuses),
            subject=subject,
            index_status=index_status,
            index_note=note,
            index=CoherenceIndex(score=None, level=None),
            dimensions=_empty_dimensions(detail),
            sample=SampleInfo(
                found=fetch.found,
                fetched=0,
                truncated=False,
                emitters=0,
                emitter_articles=0,
                single_article_agencies=0,
                republisher_articles=0,
                mock_summaries_ignored=0,
            ),
            agencies=[],
            shared_anchors=[],
            divergences=[],
            republishers=RepublishersBlock(articles=0, share=None, agencies=[]),
            notes=notes,
            **common,
        )

    if isinstance(page1_r, BaseException):
        logger.warning("coerência: artigos indisponíveis (%s)", page1_r)
        error = f"falha ao consultar a graphql-api ({_error_text(page1_r)})."
        return finish(without_index("unavailable", error, "artigos indisponíveis"))

    fetch.found = int(page1_r.get("found") or 0)
    fetch.rows = list(page1_r.get("articles") or [])
    if pg is not None:
        statuses.append(
            indexing_lag_status(fetch.found, pg.window, label=f"{subject.label} em {span}")
        )
    if fetch.found == 0:
        if subject.kind == "entity" and subject.resolved_by == "id":
            if not isinstance(entity_r, BaseException) and not (entity_r or {}).get("entity"):
                _detach(names_task)
                raise CoherenceInputError(
                    "Entidade não encontrada",
                    f"`{subject.id}` não existe no grafo de entidades. Use "
                    "gobus_resolve_entity para descobrir o entityId.",
                )
        if pg is not None and pg.window > 0:
            gap = (
                f"o índice de busca (Typesense) não tem a marcação de {subject.label} na "
                f"janela {span} (0 de {pg.window} artigos do Postgres): histórico ainda não "
                "reindexado. Tente uma janela mais recente."
            )
            return finish(without_index("unavailable", gap, "índice de busca sem a entidade"))
        hint = (
            f"Nenhum artigo de {subject.label} na janela {span}. Amplie a janela (até "
            f"{MAX_WINDOW_DAYS} dias) ou confira o assunto (gobus_resolve_entity para "
            "entidades; gobus://themes para temas)."
        )
        return finish(without_index("no_articles", hint, "sem artigos na janela"))

    # ── páginas 2–4 ──
    pages = min(MAX_PAGES, math.ceil(fetch.found / PAGE_SIZE))
    fetch.pages_requested = pages
    if pages > 1:
        more = await asyncio.gather(
            *(_page(client, filt, p) for p in range(2, pages + 1)), return_exceptions=True
        )
        for page, result in zip(range(2, pages + 1), more, strict=True):
            if isinstance(result, BaseException):
                fetch.page_errors.append(f"página {page}: {_error_text(result)}")
            else:
                fetch.rows += list(result.get("articles") or [])
    seen: set[str] = set()
    articles: list[CoherenceArticle] = []
    for row in fetch.rows:
        uid = row.get("uniqueId") or ""
        if uid and uid in seen:
            continue
        seen.add(uid)
        parsed = parse_article(row)
        if parsed is not None:
            articles.append(parsed)
    truncated = fetch.found > len(fetch.rows) and fetch.found > SAMPLE_CAP

    # ── tom (aliases de contagem) ──
    split = split_agencies(articles, catalog_info.republishers)
    tone_agencies = list(split.emitters)[:MAX_TONE_AGENCIES]
    tone_counts = tone_totals = None
    tone_error: str | None = None
    if len(split.emitters) >= 2:
        filters, keys = [], []
        for agency in tone_agencies:
            scoped = {**filt, "agencies": [agency]}
            for label in TONE_LABELS:
                filters.append({**scoped, "sentiment": [label]})
                keys.append((agency, label))
            if truncated:
                filters.append(scoped)
                keys.append((agency, None))
        try:
            found = await _counts(client, filters)
        except Exception as exc:
            logger.warning("coerência: contagens de sentimento indisponíveis (%s)", exc)
            tone_error = _error_text(exc)
            statuses.append(failed_status("sentiment_labels", exc))
        else:
            tone_counts = {a: {} for a in tone_agencies}
            tone_totals = {a: len(split.emitters[a]) for a in tone_agencies}
            for (agency, label), count in zip(keys, found, strict=True):
                if label is None:
                    tone_totals[agency] = count
                else:
                    tone_counts[agency][label] = count
            labeled = sum(sum(c.values()) for c in tone_counts.values())
            total = sum(tone_totals.values())
            statuses.append(
                share_status(
                    "sentiment_labels",
                    min(labeled, total),
                    total,
                    dead=SENTIMENT_MIN_COVERAGE,
                )
            )

    exclude = excluded_entities(subject.id, catalog_info.codes)
    names = await _names_within(names_task, started + NAMES_DEADLINE)
    assessment = assess(
        articles,
        republishers=catalog_info.republishers,
        exclude=exclude,
        names=names,
        tone_counts=tone_counts,
        tone_totals=tone_totals,
        tone_error=tone_error,
    )
    with_entities = sum(1 for a in articles if a.entities)
    if articles:
        statuses.insert(0, share_status("entities_ner", with_entities, len(articles)))

    # ── prior (só entidade) ──
    prior: PriorInfo | None = None
    dimensions = assessment.dimensions
    if subject.kind == "entity":
        if pg is not None:
            # taxas na mesma fonte (Postgres); se o Typesense achou mais, vale o maior
            window_count = max(fetch.found, pg.window)
            flag = truncated_start(pg.prior, PRIOR_DAYS, window_count, window.days)
            prior = PriorInfo(
                window=as_window(_prior_range(window), bucket_tz="UTC"),
                articles=pg.prior,
                daily_rate=round(pg.prior / PRIOR_DAYS, 3),
                window_daily_rate=round(window_count / window.days, 3),
                truncated_start=flag,
            )
            if flag and assessment.index_status == "scored":
                dimensions = [
                    d.model_copy(
                        update={"detail": d.detail + "; início truncado (a pauta já corria)"}
                    )
                    if d.key == "timing"
                    else d
                    for d in dimensions
                ]

    oldest = min((a.published_at for a in articles), default=None)
    notices = window_notices + notices_for(statuses)
    truncation = _truncation_notice(fetch, len(fetch.rows), oldest)
    if truncation is not None:
        notices.append(truncation)
    sample = SampleInfo(
        found=fetch.found,
        fetched=len(fetch.rows),
        truncated=truncated,
        **assessment.sample,
    )
    report = CoherenceReport(
        summary="",
        status=_report_status(assessment.index_status, assessment, statuses, fetch),
        data_status=statuses,
        notices=notices,
        subject=subject,
        index_status=assessment.index_status,
        index_note=assessment.insufficient_reason,
        index=assessment.index,
        dimensions=dimensions,
        sample=sample,
        agencies=assessment.agencies,
        agencies_omitted=assessment.agencies_omitted,
        shared_anchors=assessment.shared_anchors,
        divergences=assessment.divergences,
        republishers=assessment.republishers,
        prior=prior,
        hhi=assessment.hhi,
        notes=notes,
        **common,
    )
    return finish(report)


async def build_coherence_report(client: GobusGraphQLClient, **kwargs) -> CoherenceReport:
    """Só o ``CoherenceReport`` (payload de um app futuro); mesmos parâmetros."""
    report, _ = await build_coherence_output(client, **kwargs)
    return report


async def get_message_coherence(
    client: GobusGraphQLClient,
    entity_id: str = "",
    theme: str = "",
    agencies: list[str] | None = None,
    date_from: str = "",
    date_to: str = "",
    *,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
    cache: TTLCache | None = None,
) -> str:
    """Markdown da coerência de mensagem. Entrada inválida (ou entidade/tema/agência não
    encontrados) devolve a mensagem, sem levantar."""
    try:
        _, markdown = await build_coherence_output(
            client,
            entity_id=entity_id,
            theme=theme,
            agencies=agencies,
            date_from=date_from,
            date_to=date_to,
            catalog=catalog,
            now=now,
            cache=cache,
        )
    except CoherenceInputError as exc:
        return exc.markdown()
    return markdown
