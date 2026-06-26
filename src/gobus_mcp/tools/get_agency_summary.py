from datetime import date, timedelta
from gobus_mcp.client import GobusGraphQLClient

_ANALYTICS_QUERY = """
query AgencyAnalytics(
    $agencies: [String!]!, $dateFrom: String!, $dateTo: String!, $granularity: Granularity!
) {
    agencyAnalytics(
        agencies: $agencies dateFrom: $dateFrom dateTo: $dateTo granularity: $granularity
    ) {
        period agencyKey agencyName articleCount avgSentimentScore pctPositive avgReadabilityFlesch
    }
}
"""

_TRENDS_QUERY = """
query TrendingThemes(
    $windowDays: Int!, $baselineDays: Int!, $growthThreshold: Float, $agencyKey: String, $limit: Int
) {
    trendingThemes(
        windowDays: $windowDays baselineDays: $baselineDays
        growthThreshold: $growthThreshold agencyKey: $agencyKey limit: $limit
    ) {
        themeLabel growthScore windowCount
        topArticles { uniqueId title publishedAt }
    }
}
"""


async def get_agency_summary(
    agency_key: str,
    client: GobusGraphQLClient,
    days: int = 30,
) -> str:
    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=days)).isoformat()

    analytics_data = await client.execute(_ANALYTICS_QUERY, {
        "agencies": [agency_key],
        "dateFrom": date_from,
        "dateTo": date_to,
        "granularity": "MONTH",
    })
    trends_data = await client.execute(_TRENDS_QUERY, {
        "windowDays": 7,
        "baselineDays": 28,
        "growthThreshold": 1.0,
        "agencyKey": agency_key,
        "limit": 5,
    })

    rows = analytics_data.get("agencyAnalytics") or []
    themes = trends_data.get("trendingThemes") or []

    if not rows and not themes:
        return f"Sem dados para agência: `{agency_key}`"

    agency_name = rows[0].get("agencyName", agency_key) if rows else agency_key
    total_articles = sum(r.get("articleCount", 0) for r in rows)

    lines = [
        f"# Resumo: {agency_name}\n",
        f"**Período:** últimos {days} dias ({date_from} → {date_to})\n",
        f"**Volume:** {total_articles} artigos publicados\n",
    ]

    if rows:
        avg_flesch = next(
            (r.get("avgReadabilityFlesch") for r in rows if r.get("avgReadabilityFlesch")),
            None,
        )
        if avg_flesch is not None:
            nivel = "fácil" if avg_flesch > 70 else ("médio" if avg_flesch > 50 else "difícil")
            lines.append(f"**Legibilidade:** {avg_flesch:.1f} ({nivel})\n")

    if themes:
        lines.append("## Temas em alta (últimos 7 dias)\n")
        for t in themes:
            lines.append(f"- 📈 **{t['themeLabel']}** · {t['growthScore']:.1f}× crescimento")
            for art in (t.get("topArticles") or [])[:2]:
                title = art.get("title", "")[:70]
                lines.append(f"  - {title}")

    return "\n".join(lines)
