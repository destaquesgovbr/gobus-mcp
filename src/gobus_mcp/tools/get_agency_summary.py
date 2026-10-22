"""Resumo executivo de uma agência: volume, legibilidade, sentimento e temas em alta.

Métricas nulas aparecem como "indisponível" (nunca 0). Legibilidade: Flesch pt-BR (média
dos artigos que o têm); sem ele, o inglês (legado), com aviso. Os temas vêm do ``trendingThemes``
com o limiar convertido para o baseline sobreposto da API (``analytics.ratios``); sem
temas, a cobertura de classificação diz se é estabilidade ou falta de dado.
"""

from __future__ import annotations

import asyncio
from datetime import date

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.analytics.ratios import overlap_growth_threshold, ratio_from_trending_row
from gobus_mcp.calendario import agency_analytics_bounds, closed_window, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import theme_coverage
from gobus_mcp.formatting import article_ref
from gobus_mcp.readability import (
    LEGACY_SCALE_MESSAGE,
    FleschScale,
    FleschValue,
    choose_scale,
    describe_flesch,
    readability_status,
    scale_metric,
    weighted_metric,
)
from gobus_mcp.schema_compat import ARTICLE_SUMMARY_URL, FLESCH_PTBR, execute_compatible

TREND_WINDOW_DAYS = 7
TREND_BASELINE_DAYS = 28
TREND_MIN_RATIO = 1.5  # mesmo default do gobus_detect_trends (razão sem sobreposição)
TREND_LIMIT = 5

_ANALYTICS_TEMPLATE = """
query AgencySummaryAnalytics__SUFFIX__(
    $agencies: [String!]!, $dateFrom: String!, $dateTo: String!, $granularity: Granularity!
) {
    agencyAnalytics(
        agencies: $agencies dateFrom: $dateFrom dateTo: $dateTo granularity: $granularity
    ) {
        period agencyKey agencyName articleCount avgSentimentScore pctPositive avgReadabilityFlesch__PTBR__
    }
}
"""

# Flesch pt-BR (GQL-1); sem ele na API, a antiga responde (schema_compat).
_ANALYTICS_QUERY = _ANALYTICS_TEMPLATE.replace("__SUFFIX__", "").replace(
    "__PTBR__", "\n        avgReadabilityFleschPtbr readabilityFleschPtbrCount"
)
_ANALYTICS_LEGACY_QUERY = _ANALYTICS_TEMPLATE.replace("__SUFFIX__", "Legacy").replace(
    "__PTBR__", ""
)

_TRENDS_TEMPLATE = """
query AgencySummaryTrends__SUFFIX__(
    $windowDays: Int!, $baselineDays: Int!, $growthThreshold: Float, $agencyKey: String, $limit: Int
) {
    trendingThemes(
        windowDays: $windowDays baselineDays: $baselineDays
        growthThreshold: $growthThreshold agencyKey: $agencyKey limit: $limit
    ) {
        themeLabel growthScore windowCount baselineDailyAvg
        topArticles { uniqueId title publishedAt__URL__ }
    }
}
"""

# ``ArticleSummary.url`` veio com o GQL-1; sem ele, a antiga responde (schema_compat).
_TRENDS_QUERY = _TRENDS_TEMPLATE.replace("__SUFFIX__", "").replace("__URL__", " url")
_TRENDS_LEGACY_QUERY = _TRENDS_TEMPLATE.replace("__SUFFIX__", "Legacy").replace("__URL__", "")


def _readability_line(rows: list[dict], scale: FleschScale) -> str:
    clamped = scale_metric(rows, scale, clamp=True)
    if clamped.value is None:
        return "**Legibilidade:** indisponível — nenhum artigo do período com Flesch"
    raw = scale_metric(rows, scale).value
    fv = FleschValue(raw, clamped.value, clamped.clamped_rows > 0)
    return (
        f"**Legibilidade ({scale.short}):** {describe_flesch(fv)} — "
        f"{clamped.covered_articles} de {clamped.total_articles} artigos com Flesch"
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
    date_from, date_to = agency_analytics_bounds(window, "MONTH")  # MONTH: dateTo exclusivo
    g0 = round(overlap_growth_threshold(TREND_MIN_RATIO, TREND_WINDOW_DAYS, TREND_BASELINE_DAYS), 4)

    (analytics_data, _), (trends_data, _), coverage, name = await asyncio.gather(
        execute_compatible(
            client,
            FLESCH_PTBR,
            _ANALYTICS_QUERY,
            _ANALYTICS_LEGACY_QUERY,
            {
                "agencies": [code],
                "dateFrom": date_from,
                "dateTo": date_to,
                "granularity": "MONTH",
            },
        ),
        execute_compatible(
            client,
            ARTICLE_SUMMARY_URL,
            _TRENDS_QUERY,
            _TRENDS_LEGACY_QUERY,
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
    scale = choose_scale(rows)
    lines = [
        f"# Resumo: {name} (`{code}`)\n",
        f"**Período:** {window.start:%d/%m/%Y}–{window.end:%d/%m/%Y} ({window.days} dias)",
        f"**Volume:** {total_articles} artigos publicados",
        _readability_line(rows, scale),
        _sentiment_line(rows),
    ]
    readability = readability_status(rows, scale)
    for status in (readability, coverage):
        if status.status != "ok":
            lines.append(f"> {status.message}")
    if scale.legacy and rows:
        lines.append(f"> {LEGACY_SCALE_MESSAGE}")

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
                lines.append(f"  - {article_ref(art, 70)}")
    elif coverage.status == "unavailable":
        lines.append("Temas indisponíveis: a classificação de temas não cobre a janela.")
    else:
        lines.append("Nenhum tema da agência em crescimento.")

    return "\n".join(lines)
