import asyncio
import datetime
import json

from gobus_mcp.client import GobusGraphQLClient

_HEALTH_AGENCIES = ["secom", "agencia_brasil", "saude"]

_ANALYTICS_QUERY = """
query HealthAnalytics($agencies: [String!]!, $dateFrom: String!, $dateTo: String!, $granularity: Granularity!) {
    agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: $granularity) {
        agencyKey
        articleCount
        pctPositive
        avgReadabilityFlesch
    }
}
"""

_ENTITIES_QUERY = """
query HealthEntities($limit: Int!) {
    trendingEntities(limit: $limit) {
        entityId
        trendingScore
    }
}
"""


def _check_trending_score(entities: list[dict]) -> dict:
    """Diagnóstico do pipeline de trendingScore a partir de trendingEntities."""
    scores = [e.get("trendingScore") for e in entities]
    if scores and all(s is not None and s < 1.0 for s in scores):
        return {"status": "DEAD", "note": "todos os trendingScore < 1.0 (campo degenerado/nulo)"}
    if any(s is None for s in scores):
        return {"status": "DEGRADED", "note": "alguns trendingScore nulos"}
    return {"status": "OK", "note": "trendingScore com variância utilizável"}


def _check_sentiment(agency_pct: list[float]) -> dict:
    """Diagnóstico do pipeline de sentimento a partir da média de pctPositive."""
    mean = sum(agency_pct) / len(agency_pct) if agency_pct else 0.0
    if mean <= 0.0:
        return {"status": "DEAD", "note": "pctPositive médio <= 0 (pipeline de sentimento parado)"}
    if mean < 5.0:
        return {"status": "DEGRADED", "note": f"pctPositive médio baixo ({mean:.1f})"}
    return {"status": "OK", "note": f"pctPositive médio {mean:.1f}"}


def _check_flesch(agency_flesch: list[float]) -> dict:
    """Diagnóstico do pipeline de legibilidade a partir de Fleschs negativos."""
    negatives = sum(1 for f in agency_flesch if f < 0)
    if agency_flesch and negatives == len(agency_flesch):
        return {"status": "DEAD", "note": "todas as agências com Flesch negativo"}
    if negatives > 0:
        return {"status": "DEGRADED", "note": f"{negatives} agência(s) com Flesch negativo"}
    return {"status": "OK", "note": "Flesch positivo em todas as agências amostradas"}


async def fetch_health_pipelines(client: GobusGraphQLClient) -> str:
    """Health-check JSON dos pipelines de dados que alimentam o Gobus.

    Amostra agencyAnalytics (30 dias) e trendingEntities para diagnosticar três
    pipelines conhecidamente frágeis: trendingScore, sentimento e legibilidade.

    Args:
        client: Cliente GraphQL.

    Returns:
        JSON string com checkedAt e status por pipeline (OK | DEGRADED | DEAD).
    """
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=30)).isoformat()
    date_to = today.isoformat()

    analytics_data, entities_data = await asyncio.gather(
        client.execute(_ANALYTICS_QUERY, {
            "agencies": _HEALTH_AGENCIES,
            "dateFrom": date_from,
            "dateTo": date_to,
            "granularity": "MONTH",
        }),
        client.execute(_ENTITIES_QUERY, {"limit": 5}),
    )
    rows = analytics_data.get("agencyAnalytics") or []
    entities = entities_data.get("trendingEntities") or []

    by_agency: dict[str, dict] = {}
    for row in rows:
        key = row.get("agencyKey") or ""
        agg = by_agency.setdefault(key, {"count": 0, "fleschW": 0.0, "pctW": 0.0})
        count = row.get("articleCount") or 0
        agg["count"] += count
        agg["fleschW"] += (row.get("avgReadabilityFlesch") or 0.0) * count
        agg["pctW"] += (row.get("pctPositive") or 0.0) * count

    agency_flesch = [a["fleschW"] / a["count"] for a in by_agency.values() if a["count"] > 0]
    agency_pct = [a["pctW"] / a["count"] for a in by_agency.values() if a["count"] > 0]

    result = {
        "checkedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pipelines": {
            "trendingScore": _check_trending_score(entities),
            "sentiment": _check_sentiment(agency_pct),
            "flesch": _check_flesch(agency_flesch),
        },
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
