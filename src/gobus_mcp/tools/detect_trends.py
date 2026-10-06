"""Radar de temas em crescimento (``trendingThemes`` da graphql-api).

O resolver compara a janela com um baseline que **inclui** a janela. O limiar do usuário
(``growth_threshold``) é a razão sem sobreposição e é convertido para o limiar da API
(``analytics.ratios.overlap_growth_threshold``); nunca se envia ``growthThreshold: 0``.
Sem temas, a tool distingue "nada cresceu" de "temas sem classificação" pela cobertura
(``topThemes``/``analyticsKpis``) da mesma janela.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.analytics.ratios import overlap_growth_threshold, ratio_from_trending_row
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import theme_coverage

MIN_GROWTH_THRESHOLD = 1.0  # abaixo disso entram temas em queda (e o N+1 de topArticles)

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
        windowCount
        baselineDailyAvg
        growthScore
        topArticles {
            uniqueId title agencyName publishedAt
        }
    }
}
"""


def _ratio_text(theme: dict, window_days: int, baseline_days: int) -> str:
    g = ratio_from_trending_row(theme, window_days, baseline_days)
    if g.is_new:
        return "**novo** (sem artigos antes da janela)"
    return f"razão **{g.ratio:.1f}×**"


async def detect_trends(
    client: GobusGraphQLClient,
    window_days: int = 7,
    baseline_days: int = 28,
    min_articles: int = 3,
    growth_threshold: float = 1.5,
    agency_key: str | None = None,
    limit: int = 10,
    *,
    catalog: AgencyCatalog | None = None,
) -> str:
    """Detecta temas em crescimento comparando janela recente com baseline histórico.

    Args:
        window_days: Janela recente em dias (default 7)
        baseline_days: Baseline histórico em dias (default 28, inclui a janela na API)
        min_articles: Mínimo de artigos na janela recente (default 3)
        growth_threshold: Razão mínima sem sobreposição (default 1.5×; mínimo 1.0)
        agency_key: Filtrar por agência (opcional; validada no catálogo)
        limit: Máximo de temas (default 10)

    Returns:
        Markdown com ranking de temas em crescimento, ou o aviso de temas indisponíveis.
    """
    if baseline_days <= window_days:
        return (
            f"Parâmetros inválidos: baseline_days ({baseline_days}) deve ser maior que "
            f"window_days ({window_days})."
        )
    notes = []
    r0 = growth_threshold
    if r0 < MIN_GROWTH_THRESHOLD:
        r0 = MIN_GROWTH_THRESHOLD
        notes.append(
            f"> growth_threshold {growth_threshold} abaixo do mínimo: usando {r0:.1f}× "
            "(abaixo de 1 entrariam temas em queda)."
        )
    g0 = round(overlap_growth_threshold(r0, window_days, baseline_days), 4)

    variables: dict = {
        "windowDays": window_days,
        "baselineDays": baseline_days,
        "minArticles": min_articles,
        "growthThreshold": g0,
        "limit": limit,
    }
    if agency_key:
        catalog = catalog or AgencyCatalog(client)
        check = await catalog.validate(agency_key)
        if not check.ok:
            return check.message
        variables["agencyKey"] = check.code

    data, coverage = await asyncio.gather(
        client.execute(_TRENDING_QUERY, variables),
        theme_coverage(client, window_days),
    )
    themes = data.get("trendingThemes") or []

    header = [
        "# Radar de Tendências\n",
        f"**Janela:** últimos {window_days} dias · **Baseline:** {baseline_days} dias "
        f"(os {baseline_days - window_days} anteriores à janela) · "
        f"**Limiar:** razão ≥ {r0:.1f}× sem sobreposição "
        f"(= growthScore ≥ {g0:.2f} na API, cujo baseline inclui a janela)",
        *notes,
    ]
    if coverage.status != "ok":
        header.append(f"> {coverage.message}")

    if not themes:
        if coverage.status == "unavailable":
            return "\n".join(
                [
                    *header,
                    "\nSem temas para comparar: a classificação de temas não cobre a janela, "
                    "então a ausência de tendências não significa estabilidade.",
                ]
            )
        return "\n".join(
            [
                *header,
                f"\nNenhum tema em crescimento detectado (últimos {window_days}d vs "
                f"{baseline_days}d, razão ≥ {r0:.1f}×).",
            ]
        )

    lines = [*header, f"\n## {len(themes)} temas em crescimento\n"]
    for i, theme in enumerate(themes, 1):
        growth = theme.get("growthScore") or 0.0
        window = theme.get("windowCount") or 0
        baseline_avg = theme.get("baselineDailyAvg") or 0.0
        emoji = "🔥" if growth >= 3.0 else ("📈" if growth >= 2.0 else "↗")
        lines.append(
            f"{i}. {emoji} **{theme['themeLabel']}** · "
            f"{_ratio_text(theme, window_days, baseline_days)} · "
            f"growthScore {growth:.1f} · "
            f"{window} artigos (janela) vs {baseline_avg:.1f}/dia (baseline)"
        )
        top_arts = theme.get("topArticles") or []
        if top_arts:
            agency_counts = Counter(a.get("agencyName") for a in top_arts if a.get("agencyName"))
            agency_str = " · ".join(f"{name} ({cnt})" for name, cnt in agency_counts.most_common(3))
            lines.append(f"   Agências: {agency_str}")
            for art in top_arts[:3]:
                title = (art.get("title") or "")[:80]
                uid = art.get("uniqueId") or ""
                lines.append(f"   - {title}  `{uid}`")

    lines.append(
        "\n_Razão = artigos/dia na janela ÷ artigos/dia nos dias anteriores do baseline "
        "(suavização de Laplace). growthScore = cálculo da API, com o baseline incluindo a "
        "janela._"
    )
    return "\n".join(lines)
