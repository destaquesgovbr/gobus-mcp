import datetime
import json

from gobus_mcp.client import GobusGraphQLClient

# Top ~20 agências por volume esperado.
_AGENCIES = [
    "agencia_brasil", "secom", "saude", "mec", "trabalho", "fazenda", "mre",
    "defesa", "mj", "planejamento", "cgu", "agu", "ipea", "fnde", "inss",
    "sus", "anvisa", "ibge", "senado", "camara",
]

_TARGET_FLESCH = 50

_ANALYTICS_QUERY = """
query ReadabilityReport($agencies: [String!]!, $dateFrom: String!, $dateTo: String!, $granularity: Granularity!) {
    agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: $granularity) {
        period
        agencyKey
        agencyName
        articleCount
        avgReadabilityFlesch
    }
}
"""


async def fetch_readability_report(client: GobusGraphQLClient) -> str:
    """Relatório JSON de legibilidade por agência (últimos 90 dias).

    Agrega os últimos 90 dias por agência: soma de artigos e média ponderada do
    índice Flesch, com o gap até a meta (Flesch 50). Agências ordenadas por Flesch
    decrescente.

    Args:
        client: Cliente GraphQL.

    Returns:
        JSON string com generatedAt, targetFlesch e lista de agências.
    """
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=90)).isoformat()
    date_to = today.isoformat()

    data = await client.execute(_ANALYTICS_QUERY, {
        "agencies": _AGENCIES,
        "dateFrom": date_from,
        "dateTo": date_to,
        "granularity": "MONTH",
    })
    rows = data.get("agencyAnalytics") or []

    by_agency: dict[str, dict] = {}
    for row in rows:
        key = row.get("agencyKey") or ""
        agg = by_agency.setdefault(key, {
            "agencyKey": key,
            "agencyName": row.get("agencyName") or key,
            "articleCount": 0,
            "_fleschWeighted": 0.0,
        })
        count = row.get("articleCount") or 0
        flesch = row.get("avgReadabilityFlesch") or 0.0
        agg["articleCount"] += count
        agg["_fleschWeighted"] += flesch * count

    agencies = []
    for agg in by_agency.values():
        total = agg["articleCount"]
        avg_flesch = round(agg["_fleschWeighted"] / total, 2) if total > 0 else 0.0
        agencies.append({
            "agencyKey": agg["agencyKey"],
            "agencyName": agg["agencyName"],
            "articleCount": total,
            "avgReadabilityFlesch": avg_flesch,
            "gapToTarget": round(avg_flesch - _TARGET_FLESCH, 2),
        })

    agencies.sort(key=lambda a: a["avgReadabilityFlesch"], reverse=True)

    result = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "targetFlesch": _TARGET_FLESCH,
        "agencies": agencies,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
