"""Anomalias de entidade: candidatos do ``trendingEntities`` recalculados via ``entityCoverage``.

Janelas (``entity_windows``): janela fechada ``[D−7, D−1]`` (nominal em BRT, contagens em
dias UTC da API) e baseline de 28 dias de ``calendario.baseline_for`` (rolante; na
recuperação, os 28 dias antes do defeso). A dona é procurada em ``[D−90, D−8]``.

Contagens **sem republicadoras** (``AgencyCatalog.republishers()``): republicação não é
cobertura própria. Razões com Laplace (baseline zero não explode).

Precedência das classes (``classify_entity``):
1. ``burst``: ``max_day_share ≥ 0,8`` (caso Censo: 57 de 60 artigos num dia);
2. ``new_entity``: ``baseline_count == 0`` (com menções na janela);
3. ``calendar_explained``: no defeso, dona silenciada (≥ 14 dias sem publicar) ou com
   produção < 0,2× do baseline; na recuperação, ≥ 50% da janela vindo de agências
   retomadas **e** o sinal não se sustenta sem elas (se sustenta, segue com a flag
   ``resumed_agencies``);
4. ``coordinated_silence``: outras agências com razão ≥ ``silence_ratio`` e ao menos
   ``min_count`` artigos na janela; dona com 0 menções ou ≤ 25% do próprio normal; dona
   ativa no geral (produção ≥ 0,5× do baseline); dona com baseline ≥ 3;
5. ``concentrated_coverage``: razão ≥ ``ratio``, ao menos ``min_count`` artigos, menos de
   ``window_agencies`` agências e ≥ 2 dias distintos;
6. ``normal``.

Severidade (0–1): pela razão contra ``sens.ratio`` (no silêncio, pelo ``silence_score``
contra ``sens.silence_ratio``); zero sem menções próprias na janela e em
``calendar_explained`` (explicado não é anomalia); abaixo de ``min_count`` artigos,
proporcional ao volume (``× w/min_count``).

O ``volumeRatio`` do upstream só é repassado ao payload; nunca decide nada aqui.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from gobus_mcp.agency_activity import ActivitySnapshot, activity_ratio
from gobus_mcp.analytics.ratios import band, laplace_ratio, severity
from gobus_mcp.analytics.themes import Sensitivity
from gobus_mcp.calendario import (
    BLACKOUTS,
    BlackoutPeriod,
    DateRange,
    PhaseName,
    baseline_for,
    closed_window,
    phase,
)
from gobus_mcp.data_status import LEGACY_FLOOR_RATIO, parse_api_datetime
from gobus_mcp.domains import entity_domain
from gobus_mcp.payloads.anomalies import (
    MAX_DAILY_POINTS,
    EntitySignal,
    EntitySignalKind,
    OwnerInfo,
    UpstreamInfo,
)
from gobus_mcp.payloads.common import Confidence, Notice
from gobus_mcp.readability import period_start

WINDOW_DAYS = 7
BASELINE_DAYS = 28
OWNER_LOOKBACK_DAYS = 90
OWNER_GAP_DAYS = 8  # o período da dona termina em D−8 (fora da janela)
MAX_CANDIDATES = 30

BURST_DAY_SHARE = 0.8
OWNER_MIN_SHARE = 0.3
OWNER_MIN_ARTICLES = 3
SILENCE_OWNER_REL = 0.25
OWNER_ACTIVE_RATIO = 0.5
OWNER_MIN_BASELINE = 3
CALENDAR_OWNER_ACTIVITY = 0.2
RESUMED_SHARE = 0.5

_CONFIDENCE = ("low", "medium", "high")


# ── janelas ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntityWindows:
    today: date
    window: DateRange
    baseline: DateRange
    owner_period: DateRange
    sparkline: DateRange  # os 28 dias até D−1 (``daily`` do payload)
    baseline_overlaps_blackout: bool
    pre_blackout: bool

    @property
    def coverage_range(self) -> DateRange:
        """Intervalo a pedir ao ``entityCoverage`` (cobre janela, baseline, dona e série)."""
        start = min(self.baseline.start, self.owner_period.start, self.sparkline.start)
        return DateRange(start, self.window.end)


def entity_windows(today: date, periods: tuple[BlackoutPeriod, ...] = BLACKOUTS) -> EntityWindows:
    window = closed_window(WINDOW_DAYS, today)
    base = baseline_for(window, BASELINE_DAYS, today=today, periods=periods)
    return EntityWindows(
        today=today,
        window=window,
        baseline=base.range,
        owner_period=DateRange(
            today - timedelta(days=OWNER_LOOKBACK_DAYS), today - timedelta(days=OWNER_GAP_DAYS)
        ),
        sparkline=closed_window(MAX_DAILY_POINTS, today),
        baseline_overlaps_blackout=base.overlaps_blackout,
        pre_blackout=base.pre_blackout,
    )


# ── cobertura ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CoverageStats:
    """Cobertura da entidade. ``by_agency_*``, contagens, agências, dias e ``max_day_share``
    excluem republicadoras; ``by_day_agency`` guarda todas (para consultas diretas)."""

    window: DateRange
    baseline: DateRange
    by_agency_window: Mapping[str, int]
    by_agency_baseline: Mapping[str, int]
    by_agency_owner_period: Mapping[str, int]
    window_count: int
    baseline_count: int
    window_agencies: int
    distinct_days: int
    max_day_share: float
    republisher_window_count: int
    republishers: frozenset[str]
    by_day_agency: Mapping[date, Mapping[str, int]] = field(repr=False)

    def agency_count(self, agency: str, r: DateRange) -> int:
        """Artigos de ``agency`` em ``r`` (inclusive republicadora)."""
        return sum(self.by_day_agency.get(day, {}).get(agency, 0) for day in r)

    def daily(self, r: DateRange, agency: str | None = None) -> list[int]:
        """Série diária em ``r``: de ``agency`` ou de todas as não republicadoras."""
        out = []
        for day in r:
            counts = self.by_day_agency.get(day, {})
            if agency is not None:
                out.append(counts.get(agency, 0))
            else:
                out.append(sum(n for a, n in counts.items() if a not in self.republishers))
        return out


def _sum_by_agency(
    by_day: Mapping[date, Mapping[str, int]], r: DateRange, republishers: frozenset[str]
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for day in r:
        for agency, n in by_day.get(day, {}).items():
            if agency not in republishers and n:
                totals[agency] = totals.get(agency, 0) + n
    return totals


def coverage_stats(
    rows: Iterable[Mapping],
    *,
    window: DateRange,
    baseline: DateRange,
    owner_period: DateRange,
    republishers: frozenset[str],
) -> CoverageStats:
    """Estatísticas das linhas ``entityCoverage(DAY)`` (``period`` em dias UTC).
    Duplicatas ``(dia, agência)`` contam uma vez."""
    by_day: dict[date, dict[str, int]] = {}
    for row in rows:
        agency, raw = row.get("agencyKey"), row.get("period")
        if not agency or not raw:
            continue
        per_day = by_day.setdefault(period_start(raw), {})
        if agency not in per_day:
            per_day[agency] = int(row.get("articleCount") or 0)

    in_window = _sum_by_agency(by_day, window, republishers)
    window_count = sum(in_window.values())
    day_totals = [
        sum(n for a, n in by_day.get(day, {}).items() if a not in republishers) for day in window
    ]
    rep_window = sum(
        n for day in window for a, n in by_day.get(day, {}).items() if a in republishers
    )
    in_baseline = _sum_by_agency(by_day, baseline, republishers)
    return CoverageStats(
        window=window,
        baseline=baseline,
        by_agency_window=in_window,
        by_agency_baseline=in_baseline,
        by_agency_owner_period=_sum_by_agency(by_day, owner_period, republishers),
        window_count=window_count,
        baseline_count=sum(in_baseline.values()),
        window_agencies=len(in_window),
        distinct_days=sum(1 for n in day_totals if n > 0),
        max_day_share=max(day_totals) / window_count if window_count else 0.0,
        republisher_window_count=rep_window,
        republishers=republishers,
        by_day_agency=by_day,
    )


# ── dona e silêncio ─────────────────────────────────────────────────────────


def owner_agency(
    entity_agency_key: str | None,
    stats: CoverageStats,
    *,
    names: Mapping[str, str] | None = None,
    min_share: float = OWNER_MIN_SHARE,
    min_articles: int = OWNER_MIN_ARTICLES,
) -> OwnerInfo | None:
    """``entity.agencyKey`` se houver; senão a agência dominante no período da dona
    (``[D−90, D−8]``, sem republicadoras) com share ≥ 0,3 e ≥ 3 artigos."""
    names = names or {}
    counts = stats.by_agency_owner_period
    total = sum(counts.values())
    if entity_agency_key:
        share = counts.get(entity_agency_key, 0) / total if total else None
        return OwnerInfo(
            agency_key=entity_agency_key,
            agency_name=names.get(entity_agency_key),
            method="agency_key",
            share=None if share is None else round(share, 3),
        )
    if not total:
        return None
    key, top = max(counts.items(), key=lambda item: (item[1], item[0]))
    if top < min_articles or top / total < min_share:
        return None
    return OwnerInfo(
        agency_key=key, agency_name=names.get(key), method="coverage", share=round(top / total, 3)
    )


def silence_score(
    others_ratio: float, owner_entity_ratio: float, owner_activity_ratio: float | None
) -> float:
    """``others_ratio / max(owner_entity_ratio / max(owner_activity_ratio or 1, 0,05), 0,1)``.

    Refina o BLUEPRINT ("volumeRatio da entidade ÷ atividade da dona"): a queda da dona na
    entidade é medida relativa à própria produção total (dona que parou de publicar tudo
    não está "calando" a entidade).
    """
    activity = max(owner_activity_ratio or 1.0, 0.05)
    return others_ratio / max(owner_entity_ratio / activity, 0.1)


# ── classificação ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntityAssessment:
    kind: EntitySignalKind
    ratio: float
    others_ratio: float | None
    owner_entity_ratio: float | None
    owner_window_count: int | None
    owner_baseline_count: int | None
    silence_score: float | None
    severity: float
    confidence: Confidence
    flags: tuple[str, ...]
    explanation: str


def _x(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + "×"


def _confidence(window_count: int, min_count: int, downgrades: int) -> Confidence:
    level = 2 if window_count >= 3 * min_count else 1 if window_count >= min_count else 0
    return _CONFIDENCE[max(level - downgrades, 0)]


def classify_entity(
    stats: CoverageStats,
    owner: OwnerInfo | None,
    *,
    owner_activity_ratio: float | None,
    owner_silenced: bool,
    resumed: frozenset[str],
    phase: PhaseName,
    sens: Sensitivity,
    window_days: int = WINDOW_DAYS,
    baseline_days: int = BASELINE_DAYS,
) -> EntityAssessment:
    """Classe do sinal pela precedência do módulo (ver docstring)."""
    W, B = window_days, baseline_days  # notação das fórmulas
    wc, bc = stats.window_count, stats.baseline_count
    ratio = laplace_ratio(wc, W, bc, B)
    flags: list[str] = []
    if stats.republisher_window_count:
        flags.append("republishers_excluded")
    if owner is not None and owner.method == "coverage":
        flags.append("owner_by_coverage")
    recovery = phase == "recovery"
    if recovery:
        flags.append("recovery")

    owner_key = owner.agency_key if owner else None
    owner_name = (owner.agency_name or owner.agency_key) if owner else None
    owner_w = owner_b = None
    others_w = 0
    others_ratio = owner_entity_ratio = owner_rel = score = None
    if owner_key is not None:
        owner_w = stats.agency_count(owner_key, stats.window)
        owner_b = stats.agency_count(owner_key, stats.baseline)
        own_in_w = owner_w if owner_key not in stats.republishers else 0
        own_in_b = owner_b if owner_key not in stats.republishers else 0
        others_w = wc - own_in_w
        others_ratio = laplace_ratio(others_w, W, bc - own_in_b, B)
        owner_entity_ratio = laplace_ratio(owner_w, W, owner_b, B)
        owner_rel = (owner_w / W) / (owner_b / B) if owner_b else None
        score = silence_score(others_ratio, owner_entity_ratio, owner_activity_ratio)

    kind: EntitySignalKind | None = None
    explanation = ""
    sev = severity(ratio, sens.ratio)
    downgrades = int(recovery)

    if wc > 0 and stats.max_day_share >= BURST_DAY_SHARE:
        kind = "burst"
        explanation = (
            f"{stats.max_day_share:.0%} das menções da janela num único dia: rajada pontual, "
            "não tendência sustentada."
        )
    elif bc == 0 and wc > 0:
        kind = "new_entity"
        explanation = f"Sem menções no baseline ({B} dias); {wc} artigos na janela."
    elif (
        phase == "blackout"
        and owner_key is not None
        and (
            owner_silenced
            or (owner_activity_ratio is not None and owner_activity_ratio < CALENDAR_OWNER_ACTIVITY)
        )
    ):
        kind = "calendar_explained"
        flags.append("owner_silenced")
        explanation = (
            f"A agência dona ({owner_name}) está sem publicar no defeso eleitoral; o padrão "
            "de cobertura é explicado pelo calendário."
        )
    elif recovery and wc:
        resumed_w = sum(n for a, n in stats.by_agency_window.items() if a in resumed)
        resumed_b = sum(n for a, n in stats.by_agency_baseline.items() if a in resumed)
        if resumed_w / wc >= RESUMED_SHARE:
            without = laplace_ratio(wc - resumed_w, W, bc - resumed_b, B)
            if without >= sens.ratio:
                flags.append("resumed_agencies")
            else:
                kind = "calendar_explained"
                explanation = (
                    f"{resumed_w / wc:.0%} da janela vem de agências que retomaram a "
                    f"publicação depois do defeso; sem elas a razão é {_x(without)}."
                )

    if kind is None and owner_key is not None and owner_b is not None:
        owner_quiet = owner_w == 0 or (owner_rel is not None and owner_rel <= SILENCE_OWNER_REL)
        owner_active = owner_activity_ratio is None or owner_activity_ratio >= OWNER_ACTIVE_RATIO
        if (
            others_ratio >= sens.silence_ratio
            and others_w >= sens.min_count
            and owner_quiet
            and owner_active
            and owner_b >= OWNER_MIN_BASELINE
        ):
            kind = "coordinated_silence"
            sev = severity(score, sens.silence_ratio)
            if owner_activity_ratio is None:
                flags.append("owner_activity_unknown")
                downgrades += 1
            activity_txt = (
                f"produção total {_x(owner_activity_ratio)} do baseline"
                if owner_activity_ratio is not None
                else "produção total desconhecida"
            )
            explanation = (
                f"Outras agências {_x(others_ratio)} acima do baseline; a dona ({owner_name}) "
                f"com {owner_w} menções na janela contra {owner_b} no baseline ({activity_txt})."
            )

    if kind is None:
        if (
            ratio >= sens.ratio
            and wc >= sens.min_count
            and stats.window_agencies < sens.window_agencies
            and stats.distinct_days >= 2
        ):
            kind = "concentrated_coverage"
            explanation = (
                f"Cobertura {_x(ratio)} acima do baseline concentrada em "
                f"{stats.window_agencies} agência(s) e {stats.distinct_days} dias."
            )
        elif wc == 0:
            kind = "normal"
            explanation = "Sem menções próprias na janela (republicadoras não contam)."
        else:
            kind = "normal"
            explanation = f"Razão {_x(ratio)} em {stats.window_agencies} agência(s)."

    # Sem menções próprias, a razão de Laplace (w=b=0 → B/W) não mede nada; e o que o
    # calendário explica não é anomalia. Nos dois casos, severidade zero (faixa normal).
    # Abaixo do volume mínimo da sensibilidade, a severidade é proporcional ao volume
    # (1 artigo é "rajada" por definição, mas não é alerta).
    if wc == 0 or kind == "calendar_explained":
        sev = 0.0
    elif wc < sens.min_count:
        sev *= wc / sens.min_count

    def _r(value: float | None) -> float | None:
        return None if value is None else round(value, 3)

    return EntityAssessment(
        kind=kind,
        ratio=round(ratio, 3),
        others_ratio=_r(others_ratio),
        owner_entity_ratio=_r(owner_entity_ratio),
        owner_window_count=owner_w,
        owner_baseline_count=owner_b,
        silence_score=_r(score),
        severity=round(sev, 3),
        confidence=_confidence(wc, sens.min_count, downgrades),
        flags=tuple(flags),
        explanation=explanation,
    )


# ── candidatos ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CandidateSelection:
    candidates: list[dict]
    upstream: UpstreamInfo
    dropped_stale: int  # execuções anteriores à última (sem contar as do piso)
    dropped_floor: int  # padrão do piso antigo (baseline zero: vr/wc ≥ 100)


def select_candidates(
    rows: Iterable[Mapping],
    *,
    max_candidates: int = MAX_CANDIDATES,
    floor_ratio: float = LEGACY_FLOOR_RATIO,
) -> CandidateSelection:
    """Candidatos do ``trendingEntities``: só a última execução e sem o piso antigo,
    por ``trendingScore`` (até ``max_candidates``)."""
    rows = [dict(r) for r in rows]
    stamps = [parse_api_datetime(r.get("computedAt")) for r in rows]
    known = [s for s in stamps if s is not None]
    last = max(known) if known else None

    def is_floor(r: Mapping) -> bool:
        return (r.get("volumeRatio") or 0) / max(r.get("windowCount") or 0, 1) >= floor_ratio

    kept, stale, floor = [], 0, 0
    for row, stamp in zip(rows, stamps, strict=True):
        if is_floor(row):
            floor += 1
        elif stamp is None or stamp != last:
            stale += 1
        else:
            kept.append(row)
    kept.sort(key=lambda r: (-(r.get("trendingScore") or 0), -(r.get("windowCount") or 0)))
    return CandidateSelection(
        candidates=kept[:max_candidates],
        upstream=UpstreamInfo(
            last_run_at=last,
            rows_total=len(rows),
            rows_last_run=sum(1 for s in stamps if s is not None and s == last),
            rows_legacy_floor=floor,
        ),
        dropped_stale=stale,
        dropped_floor=floor,
    )


def selection_notices(selection: CandidateSelection) -> list[Notice]:
    """``BASELINE_ZERO_SUPPRESSED`` quando linhas do piso antigo foram descartadas."""
    if not selection.dropped_floor:
        return []
    return [
        Notice(
            code="BASELINE_ZERO_SUPPRESSED",
            severity="warn",
            message=(
                f"{selection.dropped_floor} de {selection.upstream.rows_total} linhas do "
                "ranking de entidades com baseline zero (piso antigo) descartadas como "
                "candidatas; os sinais são recalculados pela cobertura."
            ),
            since=None,
            affects=["entities"],
        )
    ]


# ── sinal completo ──────────────────────────────────────────────────────────


def entity_signal(
    *,
    entity: Mapping,
    coverage_rows: Iterable[Mapping],
    policy_domain: str | None,
    windows: EntityWindows,
    sens: Sensitivity,
    republishers: frozenset[str],
    activity: ActivitySnapshot | None = None,
    names: Mapping[str, str] | None = None,
    candidate: Mapping | None = None,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
) -> EntitySignal:
    """``EntitySignal`` de um candidato: ``entity`` (``entityId canonicalName type
    agencyKey``), linhas do ``entityCoverage(DAY)`` em ``windows.coverage_range``,
    ``policyDetails.domain`` e, se houver, o snapshot de atividade e a linha do upstream."""
    candidate = candidate or {}
    names = dict(names or {})
    if activity is not None:
        for key, a in activity.by_agency.items():
            if a.name and key not in names:
                names[key] = a.name

    stats = coverage_stats(
        coverage_rows,
        window=windows.window,
        baseline=windows.baseline,
        owner_period=windows.owner_period,
        republishers=republishers,
    )
    owner = owner_agency(entity.get("agencyKey"), stats, names=names)
    owner_activity = None
    owner_silenced = False
    if owner is not None and activity is not None:
        record = activity.by_agency.get(owner.agency_key)
        if record is not None:
            owner_activity = activity_ratio(record, windows.window, windows.baseline)
        owner_silenced = owner.agency_key in activity.silenced
    resumed = activity.resumed if activity is not None else frozenset()

    entity_type = entity.get("type") or candidate.get("type") or "UNKNOWN"
    a = classify_entity(
        stats,
        owner,
        owner_activity_ratio=owner_activity,
        owner_silenced=owner_silenced,
        resumed=resumed,
        phase=phase(windows.today, periods),
        sens=sens,
    )
    flags = list(a.flags)
    if windows.baseline_overlaps_blackout:
        flags.append("blackout_baseline")
    if windows.pre_blackout:
        flags.append("pre_blackout_baseline")

    entity_id = entity.get("entityId") or candidate.get("entityId") or ""
    return EntitySignal(
        entity_id=entity_id,
        name=entity.get("canonicalName") or candidate.get("canonicalName") or entity_id,
        type=entity_type,
        domain=entity_domain(entity_type, policy_domain, owner.agency_key if owner else None),
        kind=a.kind,
        window_count=stats.window_count,
        baseline_count=stats.baseline_count,
        window_agencies=stats.window_agencies,
        distinct_days=stats.distinct_days,
        max_day_share=round(stats.max_day_share, 3),
        ratio=a.ratio,
        upstream_volume_ratio=candidate.get("volumeRatio"),
        upstream_computed_at=parse_api_datetime(candidate.get("computedAt")),
        owner=owner,
        owner_window_count=a.owner_window_count,
        owner_activity_ratio=None if owner_activity is None else round(owner_activity, 3),
        silence_score=a.silence_score,
        severity=a.severity,
        band=band(a.severity),
        confidence=a.confidence,
        explanation=a.explanation,
        flags=flags,
        daily=stats.daily(windows.sparkline),
        owner_daily=stats.daily(windows.sparkline, owner.agency_key) if owner else None,
    )
