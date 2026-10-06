"""gobus://health/pipelines — saúde das fontes de dados que alimentam as tools.

Só ``data_status`` (G1): temas, legibilidade, sentimento (analytics) e ranking de
entidades. Atraso de indexação e atividade das agências entram no G2.

A detecção é sempre dinâmica, na própria resposta da API:
- ``themes``: Σ ``topThemes`` / ``analyticsKpis.total`` dos últimos 7 dias;
- ``readability``: fração de artigos (das agências mais ativas, últimos 7 dias fechados)
  em linhas com Flesch — **nulo não é dado** (antes, nulo virava 0.0 e contava como ok);
- ``sentiment_analytics``: nulidade de ``avgSentimentScore``; ``pctPositive`` é fração
  0..1 e pode vir 0.0 sem dado, então só entra como métrica;
- ``entity_ranking``: linhas no piso antigo (``volumeRatio/windowCount ≥ 100``), execuções
  misturadas (``computedAt`` espalhado) e idade da última execução.

Uma consulta que falha deixa só a sua chave ``unavailable``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import (
    calendar_context,
    closed_window,
    now_brt,
    reference_date,
    utc_day_bounds,
)
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import (
    KEY_LABELS,
    entity_ranking_status,
    metric_coverage_status,
    notices_for,
    sentiment_analytics_status,
    theme_coverage,
)
from gobus_mcp.payloads.common import DataKey, DataStatus
from gobus_mcp.readability import weighted_metric

SCHEMA_VERSION = 2
WINDOW_DAYS = 7
SAMPLE_AGENCIES = 5  # agências mais ativas amostradas no agencyAnalytics
ACTIVE_DAYS = 30
_STATUS_RANK = {"ok": 0, "degraded": 1, "unavailable": 2}

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


def _failed(key: DataKey, exc: BaseException) -> DataStatus:
    return DataStatus(
        key=key,
        status="unavailable",
        message=f"{KEY_LABELS[key]}: indisponível — falha ao consultar a graphql-api ({exc})",
        metric={},
    )


def _analytics_statuses(rows: list[dict]) -> list[DataStatus]:
    readability = metric_coverage_status("readability", rows, "avgReadabilityFlesch")
    sentiment = sentiment_analytics_status(rows)
    pct = weighted_metric(rows, "pctPositive").value
    sentiment.metric["pctPositive"] = None if pct is None else round(pct, 4)
    return [readability, sentiment]


async def fetch_health_pipelines(
    client: GobusGraphQLClient,
    *,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> str:
    """JSON (``schemaVersion`` 2) com o ``DataStatus`` de cada fonte e os avisos."""
    catalog = catalog or AgencyCatalog(client)
    now = now or now_brt()
    today = reference_date(now)
    window = closed_window(WINDOW_DAYS, today)
    date_from, date_to = utc_day_bounds(window, end_exclusive=False)

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

    themes_r, analytics_r, ranking_r = await asyncio.gather(
        theme_coverage(client, WINDOW_DAYS),
        analytics(),
        ranking(),
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

    worst = max((s.status for s in statuses), key=_STATUS_RANK.__getitem__)
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "checkedAt": now.isoformat(),
        "referenceDate": today.isoformat(),
        "calendar": calendar_context(today).model_dump(mode="json"),
        "status": worst,
        "pipelines": {s.key: s.model_dump(mode="json") for s in statuses},
        "notices": [n.model_dump(mode="json") for n in notices_for(statuses)],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
