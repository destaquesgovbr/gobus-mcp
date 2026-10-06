"""gobus://health/pipelines — saúde das fontes de dados que alimentam as tools.

A detecção é sempre dinâmica, na própria resposta da API:
- ``themes``: Σ ``topThemes`` / ``analyticsKpis.total`` dos últimos 7 dias;
- ``readability``: fração de artigos (das agências mais ativas, últimos 7 dias fechados)
  em linhas com Flesch — **nulo não é dado** (antes, nulo virava 0.0 e contava como ok);
- ``sentiment_analytics``: nulidade de ``avgSentimentScore``; ``pctPositive`` é fração
  0..1 e pode vir 0.0 sem dado, então só entra como métrica;
- ``entity_ranking``: linhas no piso antigo (``volumeRatio/windowCount ≥ 100``), execuções
  misturadas (``computedAt`` espalhado) e idade da última execução;
- ``indexing_lag`` (G2): artigos do dia D (UTC) no Typesense (``articles{found}``) contra
  o Postgres (soma do ``agencyAnalytics`` DAY de todas as agências do catálogo, sem
  duplicatas). Medido em D, não em D−1, porque o sync diário completa D−1 e esconderia o
  tempo real parado; com menos de ``INDEXING_MIN_SAMPLE`` artigos em D (começo do dia
  UTC), a amostra vira D−1..D;
- ``agency_activity`` (G2): snapshot de atividade (cache de 6 h), com as agências
  silenciadas (≥ 14 dias sem publicar) e as retomadas no bloco ``agencyActivity``. A
  lista ``resumed`` é genérica (qualquer silêncio ≥ 14 dias, volta nos últimos 35 dias);
  ``afterBlackout`` marca as que voltaram depois do defeso, as únicas contadas em
  ``calendar.resumedAgencies``.

Uma consulta que falha deixa só a sua chave ``unavailable``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

from gobus_mcp.agency_activity import ActivitySnapshot, AgencyActivityService, activity_status
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import (
    agency_analytics_bounds,
    calendar_context,
    closed_window,
    now_brt,
    reference_date,
)
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import (
    entity_ranking_status,
    failed_status,
    indexing_lag_status,
    metric_coverage_status,
    notices_for,
    sentiment_analytics_status,
    theme_coverage,
    worst_status,
)
from gobus_mcp.payloads.common import DataKey, DataStatus
from gobus_mcp.readability import period_start, weighted_metric

SCHEMA_VERSION = 2
WINDOW_DAYS = 7
SAMPLE_AGENCIES = 5  # agências mais ativas amostradas no agencyAnalytics
ACTIVE_DAYS = 30
INDEXING_MIN_SAMPLE = 20  # artigos no Postgres em D para medir só o dia D

_ANALYTICS_QUERY = """
query HealthAnalytics($agencies: [String!]!, $dateFrom: String!, $dateTo: String!) {
  agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: MONTH) {
    agencyKey
    articleCount
    avgSentimentScore
    pctPositive
    avgReadabilityFlesch
  }
}
"""

_RANKING_QUERY = """
query HealthTrendingEntities {
  trendingEntities(limit: 50) {
    entityId
    volumeRatio
    windowCount
    computedAt
  }
}
"""

_INDEXING_QUERY = """
query HealthIndexingLag(
  $agencies: [String!]!
  $dateFrom: String!
  $dateTo: String!
  $dayStart: String!
  $prevStart: String!
  $end: String!
) {
  day: articles(limit: 1, filter: {startDate: $dayStart, endDate: $end}) {
    found
  }
  twoDays: articles(limit: 1, filter: {startDate: $prevStart, endDate: $end}) {
    found
  }
  agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: DAY) {
    period
    agencyKey
    articleCount
  }
}
"""


def _failed(key: DataKey, exc: BaseException) -> DataStatus:
    return failed_status(key, exc)


def _analytics_statuses(rows: list[dict]) -> list[DataStatus]:
    readability = metric_coverage_status("readability", rows, "avgReadabilityFlesch")
    sentiment = sentiment_analytics_status(rows)
    pct = weighted_metric(rows, "pctPositive").value
    sentiment.metric["pctPositive"] = None if pct is None else round(pct, 4)
    return [readability, sentiment]


def _utc_midnight(day: date) -> str:
    return datetime.combine(day, time(0), UTC).isoformat()


def _stored_by_day(rows: list[Mapping]) -> dict[date, int]:
    """Artigos por dia UTC do ``agencyAnalytics`` DAY, sem duplicatas ``(period, agencyKey)``."""
    seen: set[tuple[date, str]] = set()
    totals: dict[date, int] = {}
    for row in rows:
        key, raw = row.get("agencyKey"), row.get("period")
        if not key or not raw:
            continue
        day = period_start(raw)
        if (day, key) in seen:
            continue
        seen.add((day, key))
        totals[day] = totals.get(day, 0) + int(row.get("articleCount") or 0)
    return totals


def indexing_sample(data: Mapping, day: date) -> DataStatus:
    """``DataStatus`` de ``indexing_lag`` a partir da resposta ``HealthIndexingLag``."""
    stored = _stored_by_day(data.get("agencyAnalytics") or [])
    prev = day - timedelta(days=1)
    if stored.get(day, 0) >= INDEXING_MIN_SAMPLE:
        indexed = int((data.get("day") or {}).get("found") or 0)
        return indexing_lag_status(indexed, stored[day], label=f"{day:%d/%m} (UTC)")
    indexed = int((data.get("twoDays") or {}).get("found") or 0)
    total = stored.get(day, 0) + stored.get(prev, 0)
    return indexing_lag_status(indexed, total, label=f"{prev:%d}–{day:%d/%m} (UTC)")


def _activity_detail(snapshot: ActivitySnapshot | None) -> dict | None:
    """Agências silenciadas e retomadas (``null`` sem snapshot)."""
    if snapshot is None:
        return None

    def iso(d: date | None) -> str | None:
        return d.isoformat() if d else None

    by_agency = snapshot.by_agency
    return {
        "silenced": [
            {
                "key": key,
                "name": by_agency[key].name,
                "silentSince": iso(by_agency[key].silent_since),
                "lastActive": iso(by_agency[key].last_active),
            }
            for key in sorted(snapshot.silenced)
        ],
        "resumed": [
            {
                "key": key,
                "name": by_agency[key].name,
                "resumedOn": iso(by_agency[key].resumed_on),
                "afterBlackout": key in snapshot.resumed_after_blackout,
            }
            for key in sorted(snapshot.resumed)
        ],
    }


async def fetch_health_pipelines(
    client: GobusGraphQLClient,
    *,
    catalog: AgencyCatalog | None = None,
    activity: AgencyActivityService | None = None,
    now: datetime | None = None,
) -> str:
    """JSON (``schemaVersion`` 2) com o ``DataStatus`` de cada fonte e os avisos."""
    catalog = catalog or AgencyCatalog(client)
    activity = activity or AgencyActivityService(client, catalog)
    now = now or now_brt()
    today = reference_date(now)
    window = closed_window(WINDOW_DAYS, today)
    date_from, date_to = agency_analytics_bounds(window, "MONTH")  # inclui D−1
    utc_day = now.astimezone(UTC).date()

    async def analytics() -> list[DataStatus]:
        agencies = await catalog.active(ACTIVE_DAYS, limit=SAMPLE_AGENCIES)
        data = await client.execute(
            _ANALYTICS_QUERY,
            {"agencies": agencies, "dateFrom": date_from, "dateTo": date_to},
        )
        return _analytics_statuses(data.get("agencyAnalytics") or [])

    async def ranking() -> DataStatus:
        data = await client.execute(_RANKING_QUERY)
        return entity_ranking_status(data.get("trendingEntities") or [], now=now)

    async def indexing() -> DataStatus:
        prev = utc_day - timedelta(days=1)
        data = await client.execute(
            _INDEXING_QUERY,
            {
                "agencies": sorted(await catalog.codes()),
                "dateFrom": prev.isoformat(),
                "dateTo": utc_day.isoformat(),  # DAY: dateTo inclusivo
                "dayStart": _utc_midnight(utc_day),
                "prevStart": _utc_midnight(prev),
                "end": _utc_midnight(utc_day + timedelta(days=1)),
            },
        )
        return indexing_sample(data, utc_day)

    themes_r, analytics_r, ranking_r, indexing_r, snapshot_r = await asyncio.gather(
        theme_coverage(client, WINDOW_DAYS),
        analytics(),
        ranking(),
        indexing(),
        activity.snapshot(today),
        return_exceptions=True,
    )
    statuses: list[DataStatus] = [
        _failed("themes", themes_r) if isinstance(themes_r, BaseException) else themes_r
    ]
    if isinstance(analytics_r, BaseException):
        statuses += [
            _failed("readability", analytics_r),
            _failed("sentiment_analytics", analytics_r),
        ]
    else:
        statuses += analytics_r
    statuses.append(
        _failed("entity_ranking", ranking_r) if isinstance(ranking_r, BaseException) else ranking_r
    )
    statuses.append(
        _failed("indexing_lag", indexing_r) if isinstance(indexing_r, BaseException) else indexing_r
    )
    snapshot = None if isinstance(snapshot_r, BaseException) else snapshot_r
    statuses.append(
        activity_status(
            snapshot, error=str(snapshot_r) if isinstance(snapshot_r, BaseException) else None
        )
    )

    result = {
        "schemaVersion": SCHEMA_VERSION,
        "checkedAt": now.isoformat(),
        "referenceDate": today.isoformat(),
        "calendar": calendar_context(
            today,
            silenced_agencies=len(snapshot.silenced) if snapshot else None,
            resumed_agencies=len(snapshot.resumed_after_blackout) if snapshot else None,
        ).model_dump(mode="json"),
        "status": worst_status(s.status for s in statuses),
        "pipelines": {s.key: s.model_dump(mode="json") for s in statuses},
        "agencyActivity": _activity_detail(snapshot),
        "notices": [n.model_dump(mode="json") for n in notices_for(statuses)],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
