from gobus_mcp.client import GobusGraphQLClient

_ANALYTICS_QUERY = """
query AgencyAnalytics(
    $agencies: [String!]!
    $dateFrom: String!
    $dateTo: String!
    $granularity: Granularity!
) {
    agencyAnalytics(
        agencies: $agencies
        dateFrom: $dateFrom
        dateTo: $dateTo
        granularity: $granularity
    ) {
        period
        agencyKey
        agencyName
        articleCount
        avgSentimentScore
        pctPositive
        pctNegative
        avgReadabilityFlesch
        avgWordCount
    }
}
"""


async def get_agency_analytics(
    agencies: list[str],
    date_from: str,
    date_to: str,
    client: GobusGraphQLClient,
    granularity: str = "MONTH",
) -> str:
    """Métricas de publicação de uma ou mais agências num período.

    Args:
        agencies: Lista de agency_keys (ex: ["mec", "ms"])
        date_from: Data de início ISO (ex: "2024-01-01")
        date_to: Data de fim ISO (ex: "2024-12-31")
        granularity: DAY | WEEK | MONTH (default: MONTH)

    Returns:
        Markdown com tabela de métricas por agência e período.
    """
    data = await client.execute(_ANALYTICS_QUERY, {
        "agencies": agencies,
        "dateFrom": date_from,
        "dateTo": date_to,
        "granularity": granularity.upper(),
    })
    rows = data.get("agencyAnalytics") or []

    if not rows:
        return f"Nenhum dado encontrado para {', '.join(agencies)} em {date_from}–{date_to}"

    lines = [f"# Analytics: {', '.join(agencies)}\n**{date_from} → {date_to}** (granularity: {granularity})\n"]

    current_period = None
    for row in rows:
        raw_period = (row["period"] or "")[:10]
        if raw_period != current_period:
            current_period = raw_period
            lines.append(f"\n## {current_period}")

        agency = row.get("agencyName") or row.get("agencyKey", "")
        count = row.get("articleCount", 0)
        sent = row.get("avgSentimentScore")
        pct_pos = row.get("pctPositive")
        pct_neg = row.get("pctNegative")
        flesch = row.get("avgReadabilityFlesch")
        avg_wc = row.get("avgWordCount")

        metrics = [f"**{count}** artigos"]
        if pct_pos is not None:
            neg_part = f" / {pct_neg*100:.0f}% neg" if pct_neg is not None else ""
            metrics.append(f"😊 {pct_pos*100:.0f}% pos{neg_part}")
        if sent is not None:
            metrics.append(f"sentimento {sent:.2f}")
        if flesch is not None:
            nivel = "fácil" if flesch > 70 else ("médio" if flesch > 50 else "difícil")
            metrics.append(f"legibilidade {flesch:.1f} ({nivel})")
        if avg_wc is not None:
            metrics.append(f"📝 {avg_wc:.0f} palavras/artigo")

        lines.append(f"- **{agency}**: {' · '.join(metrics)}")

    return "\n".join(lines)
