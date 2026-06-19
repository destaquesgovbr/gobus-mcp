from gobus_mcp.client import GobusGraphQLClient

_TRENDING_QUERY = """
query TrendingThemes(
    $windowDays: Int!
    $baselineDays: Int!
    $minArticles: Int
    $growthThreshold: Float
    $agencyKey: String
    $limit: Int
) {
    trendingThemes(
        windowDays: $windowDays
        baselineDays: $baselineDays
        minArticles: $minArticles
        growthThreshold: $growthThreshold
        agencyKey: $agencyKey
        limit: $limit
    ) {
        themeLabel
        themeCode
        windowCount
        baselineDailyAvg
        growthScore
        topArticles {
            uniqueId title agencyName publishedAt trendingScore
        }
    }
}
"""


async def detect_trends(
    client: GobusGraphQLClient,
    window_days: int = 7,
    baseline_days: int = 28,
    min_articles: int = 3,
    growth_threshold: float = 1.5,
    agency_key: str | None = None,
    limit: int = 10,
) -> str:
    """Detecta temas em crescimento comparando janela recente com baseline histórico.

    Args:
        window_days: Janela recente em dias (default 7)
        baseline_days: Baseline histórico em dias (default 28)
        min_articles: Mínimo de artigos na janela recente (default 3)
        growth_threshold: Score mínimo de crescimento (default 1.5×)
        agency_key: Filtrar por agência (opcional)
        limit: Máximo de temas (default 10)

    Returns:
        Markdown com ranking de temas em crescimento.
    """
    variables: dict = {
        "windowDays": window_days,
        "baselineDays": baseline_days,
        "minArticles": min_articles,
        "growthThreshold": growth_threshold,
        "limit": limit,
    }
    if agency_key:
        variables["agencyKey"] = agency_key

    data = await client.execute(_TRENDING_QUERY, variables)
    themes = data.get("trendingThemes") or []

    if not themes:
        return f"Nenhum tema em crescimento detectado (últimos {window_days}d vs {baseline_days}d baseline, threshold {growth_threshold}×)"

    lines = [
        f"# Radar de Tendências\n",
        f"**Janela:** últimos {window_days} dias · **Baseline:** {baseline_days} dias · **Threshold:** {growth_threshold}×\n",
        f"## {len(themes)} temas em crescimento\n",
    ]

    for i, theme in enumerate(themes, 1):
        growth = theme.get("growthScore", 0)
        window = theme.get("windowCount", 0)
        baseline_avg = theme.get("baselineDailyAvg", 0)
        emoji = "🔥" if growth >= 3.0 else ("📈" if growth >= 2.0 else "↗")

        lines.append(
            f"{i}. {emoji} **{theme['themeLabel']}** · "
            f"Growth: **{growth:.1f}×** · "
            f"{window} artigos (janela) vs {baseline_avg:.1f}/dia (baseline)"
        )

    return "\n".join(lines)
