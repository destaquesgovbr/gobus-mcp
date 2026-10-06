"""Atividade das agências: snapshot diário de ``agencyAnalytics`` para todas as agências.

Uma chamada ``agencyAnalytics(agências do catálogo, DAY)`` cobre o período do snapshot:
``[D−90, D−1]``, estendido até 28 dias antes do início do defeso **só** nas fases
``blackout`` e ``recovery`` (o baseline pré-defeso; fora delas o período não cresce).
``DAY`` tem ``dateTo`` inclusivo (``calendario.agency_analytics_bounds``). Os dias são UTC.

Dá, por agência: série diária (zeros preenchidos), ``last_active``, ``silent_since``
(≥ 14 dias zerados até D−1, depois de ter publicado no período), ``resumed_on`` (volta
depois de um silêncio ≥ 14 dias), ``resumed_after_blackout_on`` (volta depois de um
silêncio ≥ 14 dias que **atravessa o último dia do defeso**: calada em 25/10 e de volta
depois) e a média diária pré-defeso; e, para a plataforma, o volume diário
(``platform_daily``, base do perfil de dia útil). Linhas duplicadas por
``(period, agencyKey)`` (agência com dois nomes no CTE da API) contam uma vez.

Duas listas de retomada:
- ``resumed``: genérica (qualquer silêncio ≥ 14 dias, volta nos últimos 35 dias), só
  informativa no health; inclui agência esporádica e volta dentro do defeso;
- ``resumed_after_blackout``: só a volta pós-defeso. É a que explica sinal na recuperação
  (``analytics.entities``) e a contagem ``resumed_agencies`` do calendário.

Cache de 6 h por D, single-flight; falha levanta (o chamador degrada para o perfil padrão)
e não é cacheada. Timeout próprio de 30 s: ~19 mil linhas levam 3–7 s.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import fmean

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import BLACKOUTS, BlackoutPeriod, DateRange, agency_analytics_bounds
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import data_status_for
from gobus_mcp.payloads.common import DataStatus
from gobus_mcp.readability import period_start

logger = logging.getLogger(__name__)

ACTIVITY_TTL = 21_600.0  # 6 h
ACTIVITY_TIMEOUT = 30.0
LOOKBACK_DAYS = 90
PRE_BLACKOUT_DAYS = 28  # baseline pré-defeso (D2)
SILENCE_MIN_DAYS = 14
RESUMED_LOOKBACK_DAYS = 35  # janela 7 + baseline 28: retomada que ainda afeta as razões

_ACTIVITY_QUERY = """
query AgencyActivitySnapshot($agencies: [String!]!, $dateFrom: String!, $dateTo: String!) {
  agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: DAY) {
    period
    agencyKey
    agencyName
    articleCount
  }
}
"""


@dataclass(frozen=True)
class AgencyActivity:
    key: str
    name: str | None
    last_active: date | None
    silent_since: date | None  # ≥ 14 dias zerados até D−1 (None se publicando)
    resumed_on: date | None  # primeiro dia ativo depois do silêncio ≥ 14 dias mais recente
    pre_daily_mean: float | None  # média diária antes do defeso (só no defeso/recuperação)
    series: Mapping[date, int]
    # primeiro dia ativo depois de um silêncio ≥ 14 dias que inclui o último dia do defeso
    resumed_after_blackout_on: date | None = None


@dataclass(frozen=True)
class ActivitySnapshot:
    by_agency: Mapping[str, AgencyActivity]
    platform_daily: Mapping[date, int]
    silenced: frozenset[str]
    resumed: frozenset[str]  # retomadas nos últimos 35 dias (genérica, informativa)
    start: date
    end: date
    resumed_after_blackout: frozenset[str] = frozenset()  # voltaram depois do defeso


def _current_period(today: date, periods: tuple[BlackoutPeriod, ...]) -> BlackoutPeriod | None:
    """Defeso em curso ou em recuperação em ``today``."""
    return next((p for p in periods if p.start <= today <= p.recovery_until), None)


def snapshot_period(
    today: date,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    *,
    lookback_days: int = LOOKBACK_DAYS,
    pre_days: int = PRE_BLACKOUT_DAYS,
) -> DateRange:
    """``[D−90, D−1]``; no defeso e na recuperação começa no máximo em ``início − 28``."""
    start = today - timedelta(days=lookback_days)
    period = _current_period(today, periods)
    if period is not None:
        start = min(start, period.start - timedelta(days=pre_days))
    return DateRange(start, today - timedelta(days=1))


def _zero_runs(series: list[tuple[date, int]]) -> list[tuple[int, int]]:
    """Corridas de zeros como pares de índices (início, fim) inclusivos."""
    runs, start = [], None
    for i, (_, count) in enumerate(series):
        if count == 0 and start is None:
            start = i
        elif count > 0 and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(series) - 1))
    return runs


def _agency_activity(
    key: str,
    name: str | None,
    series: list[tuple[date, int]],
    *,
    silence_min_days: int,
    pre_start: date | None,
    blackout_end: date | None,
) -> AgencyActivity:
    active_days = [day for day, count in series if count > 0]
    last_active = active_days[-1] if active_days else None
    silent_since = resumed_on = after_blackout = None
    for start, end in _zero_runs(series):
        length = end - start + 1
        preceded = start > 0  # houve atividade antes da corrida, dentro do período
        if length < silence_min_days or not preceded:
            continue
        if end == len(series) - 1:
            silent_since = series[start][0]
            continue
        resumed_on = series[end + 1][0]
        # calada no último dia do defeso e de volta depois dele
        if blackout_end is not None and series[start][0] <= blackout_end < resumed_on:
            after_blackout = resumed_on
    pre = [count for day, count in series if pre_start is not None and day < pre_start]
    return AgencyActivity(
        key=key,
        name=name,
        last_active=last_active,
        silent_since=silent_since,
        resumed_on=resumed_on,
        pre_daily_mean=fmean(pre) if pre else None,
        series=dict(series),
        resumed_after_blackout_on=after_blackout,
    )


def summarize_activity(
    rows: list[dict],
    *,
    today: date,
    period: DateRange | None = None,
    silence_min_days: int = SILENCE_MIN_DAYS,
    resumed_lookback_days: int = RESUMED_LOOKBACK_DAYS,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
) -> ActivitySnapshot:
    """Snapshot puro a partir das linhas DAY do ``agencyAnalytics``. Ignora D (parcial) e o
    que estiver fora do período."""
    period = period or snapshot_period(today, periods)
    end = min(period.end, today - timedelta(days=1))
    days = list(DateRange(period.start, end)) if end >= period.start else []

    counts: dict[str, dict[date, int]] = {}
    names: dict[str, str] = {}
    for row in rows:
        key = row.get("agencyKey")
        raw = row.get("period")
        if not key or not raw:
            continue
        day = period_start(raw)
        if not (period.start <= day <= end):
            continue
        per_agency = counts.setdefault(key, {})
        if day in per_agency:
            continue  # duplicata (period, agencyKey)
        per_agency[day] = int(row.get("articleCount") or 0)
        if row.get("agencyName") and key not in names:
            names[key] = row["agencyName"]

    current = _current_period(today, periods)
    pre_start = current.start if current is not None else None
    by_agency = {
        key: _agency_activity(
            key,
            names.get(key),
            [(day, per_agency.get(day, 0)) for day in days],
            silence_min_days=silence_min_days,
            pre_start=pre_start,
            blackout_end=current.end if current is not None else None,
        )
        for key, per_agency in sorted(counts.items())
    }
    platform_daily = {day: sum(c.get(day, 0) for c in counts.values()) for day in days}
    recent = today - timedelta(days=resumed_lookback_days)
    silenced = frozenset(k for k, a in by_agency.items() if a.silent_since is not None)
    resumed = frozenset(
        k
        for k, a in by_agency.items()
        if a.resumed_on is not None and a.resumed_on >= recent and k not in silenced
    )
    # Só existe na recuperação (no defeso, ninguém voltou "depois" dele ainda); dentro dela
    # a volta é sempre recente (a recuperação dura 35 dias), então não precisa do corte.
    resumed_after_blackout = frozenset(
        k
        for k, a in by_agency.items()
        if a.resumed_after_blackout_on is not None and k not in silenced
    )
    return ActivitySnapshot(
        by_agency=by_agency,
        platform_daily=platform_daily,
        silenced=silenced,
        resumed=resumed,
        start=period.start,
        end=end,
        resumed_after_blackout=resumed_after_blackout,
    )


def _mean_over(series: Mapping[date, int], r: DateRange) -> float | None:
    values = [series[day] for day in r if day in series]
    return fmean(values) if values else None


def activity_ratio(a: AgencyActivity, window: DateRange, baseline: DateRange) -> float | None:
    """Produção total da agência: média diária na janela ÷ média diária no baseline.

    ``None`` sem dias do snapshot em algum dos intervalos ou com baseline zerado.
    """
    w = _mean_over(a.series, window)
    b = _mean_over(a.series, baseline)
    if w is None or b is None or b <= 0:
        return None
    return w / b


def activity_status(snapshot: ActivitySnapshot | None, *, error: str | None = None) -> DataStatus:
    """``DataStatus`` de ``agency_activity``: ok com o snapshot; indisponível na falha."""
    if snapshot is None:
        detail = f"snapshot indisponível ({error or 'erro desconhecido'}); perfil semanal padrão"
        return data_status_for("agency_activity", "unavailable", detail)
    detail = (
        f"{len(snapshot.by_agency)} agências de {snapshot.start.strftime('%d/%m/%Y')} a "
        f"{snapshot.end.strftime('%d/%m/%Y')}; {len(snapshot.silenced)} sem publicar há "
        f"≥{SILENCE_MIN_DAYS} dias; {len(snapshot.resumed)} retomadas "
        f"({len(snapshot.resumed_after_blackout)} depois do defeso)"
    )
    metric = {
        "agencies": len(snapshot.by_agency),
        "silenced": len(snapshot.silenced),
        "resumed": len(snapshot.resumed),
        "resumedAfterBlackout": len(snapshot.resumed_after_blackout),
        "days": len(snapshot.platform_daily),
    }
    return data_status_for("agency_activity", "ok", detail, metric=metric)


class AgencyActivityService:
    """Snapshot de atividade com cache de 6 h por D (single-flight)."""

    def __init__(
        self,
        client: GobusGraphQLClient,
        catalog: AgencyCatalog,
        *,
        cache: TTLCache | None = None,
        ttl: float = ACTIVITY_TTL,
        timeout: float = ACTIVITY_TIMEOUT,
        periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    ) -> None:
        self._client = client
        self._catalog = catalog
        self._cache = cache or TTLCache()
        self._ttl = ttl
        self._timeout = timeout
        self._periods = periods

    async def snapshot(self, today: date) -> ActivitySnapshot:
        """Snapshot de D (``today``). Levanta se a API falhar."""

        async def load() -> ActivitySnapshot:
            codes = sorted(await self._catalog.codes())
            period = snapshot_period(today, self._periods)
            date_from, date_to = agency_analytics_bounds(period, "DAY")
            data = await self._client.execute(
                _ACTIVITY_QUERY,
                {"agencies": codes, "dateFrom": date_from, "dateTo": date_to},
                timeout=self._timeout,
            )
            rows = data.get("agencyAnalytics") or []
            logger.info("atividade: %d linhas de %s a %s", len(rows), date_from, date_to)
            return summarize_activity(rows, today=today, period=period, periods=self._periods)

        return await self._cache.get_or_load(("agency_activity", today), load, self._ttl)
