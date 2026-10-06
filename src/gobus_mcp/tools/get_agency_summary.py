"""Resumo executivo de uma agência: volume, legibilidade, sentimento e temas em alta.

Métricas nulas aparecem como "indisponível" (nunca 0). Os temas vêm do ``trendingThemes``
com o limiar convertido para o baseline sobreposto da API (``analytics.ratios``); sem
temas, a cobertura de classificação diz se é estabilidade ou falta de dado.
"""

from __future__ import annotations

import asyncio
from datetime import date

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.analytics.ratios import overlap_growth_threshold, ratio_from_trending_row
from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import metric_coverage_status, theme_coverage
from gobus_mcp.readability import FleschValue, describe_flesch, weighted_metric

TREND_WINDOW_DAYS = 7
TREND_BASELINE_DAYS = 28
TREND_MIN_RATIO = 1.5  # mesmo default do gobus_detect_trends (razão sem sobreposição)
TREND_LIMIT = 5

_ANALYTICS_QUERY = """
query AgencySummaryAnalytics(
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
query AgencySummaryTrends(
    $windowDays: Int!, $baselineDays: Int!, $growthThreshold: Float, $agencyKey: String, $limit: Int
) {
    trendingThemes(
        windowDays: $windowDays baselineDays: $baselineDays
        growthThreshold: $growthThreshold agencyKey: $agencyKey limit: $limit
    ) {
        themeLabel growthScore windowCount baselineDailyAvg
        topArticles { uniqueId title publishedAt }
    }
}
"""


def _readability_line(rows: list[dict]) -> str:
    clamped = weighted_metric(rows, "avgReadabilityFlesch", clamp=True)
    if clamped.value is None:
        return "**Legibilidade:** indisponível — nenhum artigo do período com Flesch"
    raw = weighted_metric(rows, "avgReadabilityFlesch").value
    fv = FleschValue(raw, clamped.value, clamped.clamped_rows > 0)
    return (
        f"**Legibilidade:** {describe_flesch(fv)} — {clamped.covered_articles} de "
        f"{clamped.total_articles} artigos com Flesch"
    )


def _sentiment_line(rows: list[dict]) -> str:
    score = weighted_metric(rows, "avgSentimentScore")
    if score.value is None:
        # sem score, o pctPositive 0.0 da API é artefato (nenhum artigo com rótulo)
        return "**Sentimento:** indisponível — nenhum artigo do período com sentimento"
    pct = weighted_metric(rows, "pctPositive")
    pct_txt = f" · {pct.value:.0%} positivos" if pct.value is not None else ""
    return f"**Sentimento:** {score.value:.2f} (média){pct_txt}"


async def get_agency_summary(
    agency_key: str,
    client: GobusGraphQLClient,
    days: int = 30,
    *,
    catalog: AgencyCatalog | None = None,
    today: date | None = None,
) -> str:
    """Resumo da agência nos últimos ``days`` dias fechados (D−days … D−1, BRT)."""
    catalog = catalog or AgencyCatalog(client)
    today = today or reference_date()
    check = await catalog.validate(agency_key)
    if not check.ok:
        return check.message
    code = check.code
    window = closed_window(max(1, days), today)
    g0 = round(overlap_growth_threshold(TREND_MIN_RATIO, TREND_WINDOW_DAYS, TREND_BASELINE_DAYS), 4)

    analytics_data, trends_data, coverage, name = await asyncio.gather(
        client.execute(
            _ANALYTICS_QUERY,
            {
                "agencies": [code],
                "dateFrom": window.start.isoformat(),
                "dateTo": window.end.isoformat(),
                "granularity": "MONTH",
            },
        ),
        client.execute(
            _TRENDS_QUERY,
            {
                "windowDays": TREND_WINDOW_DAYS,
                "baselineDays": TREND_BASELINE_DAYS,
                "growthThreshold": g0,
                "agencyKey": code,
                "limit": TREND_LIMIT,
            },
        ),
        theme_coverage(client, TREND_WINDOW_DAYS),
        catalog.display_name(code),
    )
    rows = analytics_data.get("agencyAnalytics") or []
    themes = trends_data.get("trendingThemes") or []

    if not rows and not themes:
        return (
            f"Sem dados para a agência {name} (`{code}`) entre "
            f"{window.start:%d/%m/%Y} e {window.end:%d/%m/%Y}."
        )
    if name == code and rows and rows[0].get("agencyName"):
        name = rows[0]["agencyName"]

    total_articles = sum(r.get("articleCount") or 0 for r in rows)
    lines = [
        f"# Resumo: {name} (`{code}`)\n",
        f"**Período:** {window.start:%d/%m/%Y}–{window.end:%d/%m/%Y} ({window.days} dias)",
        f"**Volume:** {total_articles} artigos publicados",
        _readability_line(rows),
        _sentiment_line(rows),
    ]
    readability = metric_coverage_status("readability", rows, "avgReadabilityFlesch")
    for status in (readability, coverage):
        if status.status != "ok":
            lines.append(f"> {status.message}")

    lines.append(
        f"\n## Temas em alta (últimos {TREND_WINDOW_DAYS} dias, razão ≥ "
        f"{TREND_MIN_RATIO:.1f}× sem sobreposição)\n"
    )
    if themes:
        for t in themes:
            ratio = ratio_from_trending_row(t, TREND_WINDOW_DAYS, TREND_BASELINE_DAYS)
            ratio_txt = "novo" if ratio.is_new else f"razão {ratio.ratio:.1f}×"
            lines.append(
                f"- 📈 **{t['themeLabel']}** · {ratio_txt} · "
                f"growthScore {(t.get('growthScore') or 0.0):.1f} · "
                f"{t.get('windowCount') or 0} artigos"
            )
            for art in (t.get("topArticles") or [])[:2]:
                title = (art.get("title") or "")[:70]
                lines.append(f"  - {title}")
    elif coverage.status == "unavailable":
        lines.append("Temas indisponíveis: a classificação de temas não cobre a janela.")
    else:
        lines.append("Nenhum tema da agência em crescimento.")

    return "\n".join(lines)
