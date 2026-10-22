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
from datetime import date

from gobus_mcp.agency_catalog import AgencyCatalog, catalog_display_names
from gobus_mcp.analytics.ratios import overlap_growth_threshold, ratio_from_trending_row
from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import theme_coverage
from gobus_mcp.formatting import (
    FollowUp,
    agency_label,
    article_agency,
    article_ref,
    tool_call,
    with_follow_ups,
)
from gobus_mcp.schema_compat import ARTICLE_SUMMARY_URL, execute_compatible

MIN_GROWTH_THRESHOLD = 1.0  # abaixo disso entram temas em queda (e o N+1 de topArticles)

_TRENDING_TEMPLATE = """
query TrendingThemes__SUFFIX__(
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
            uniqueId title agencyName publishedAt__URL__
        }
    }
}
"""

# ``ArticleSummary.url`` e ``agencyKey`` vieram com o GQL-1; sem eles, a antiga responde
# (schema_compat), e o ``agencyName`` (que carrega a key) vira o código do órgão.
_TRENDING_QUERY = _TRENDING_TEMPLATE.replace("__SUFFIX__", "").replace("__URL__", " url agencyKey")
_TRENDING_LEGACY_QUERY = _TRENDING_TEMPLATE.replace("__SUFFIX__", "Legacy").replace("__URL__", "")


def _follow_ups(
    themes: list[dict],
    *,
    window_days: int,
    baseline_days: int,
    threshold: float,
    agency_key: str | None,
    today: date,
) -> list[FollowUp]:
    """Com temas: ler o artigo mais representativo, buscar o 1º tema na janela (dias
    fechados) e projetar. Sem temas: anomalias e um limiar menor."""
    if not themes:
        items: list[FollowUp] = [(tool_call("gobus_detect_anomalies"), "sinais fora do comum")]
        if threshold > 1.2:
            lower = tool_call(
                "gobus_detect_trends",
                window_days=window_days,
                baseline_days=baseline_days,
                growth_threshold=1.2,
                agency_key=agency_key,
            )
            items.append((lower, "limiar menor"))
        return items
    items = []
    top = next((a for t in themes for a in (t.get("topArticles") or []) if a.get("uniqueId")), None)
    if top is not None:
        items.append((tool_call("gobus_get_article", unique_id=top["uniqueId"]), "artigo-chave"))
    window = closed_window(window_days, today)
    search = tool_call(
        "gobus_search_news",
        query=themes[0]["themeLabel"],
        agency_key=agency_key,
        date_from=window.start.isoformat(),
        date_to=window.end.isoformat(),
    )
    items.append((search, "artigos do tema na janela"))
    items.append((tool_call("gobus_forecast_trends"), "o tema segue em alta?"))
    return items


def _agencies_line(articles: list[dict], names: dict[str, str]) -> str:
    """``[saude] Ministério da Saúde (2) · [mec] Ministério da Educação (1)``: os 3 órgãos
    mais frequentes nos top artigos, pelo código (gobus-mcp#17)."""
    labels: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for art in articles:
        code, name = article_agency(art, names)
        if code:
            counts[code] += 1
            labels.setdefault(code, agency_label(code, name))
    return " · ".join(f"{labels[code]} ({cnt})" for code, cnt in counts.most_common(3))


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
    today: date | None = None,
) -> str:
    """Detecta temas em crescimento comparando janela recente com baseline histórico.

    Args:
        window_days: Janela recente em dias (default 7)
        baseline_days: Baseline histórico em dias (default 28, inclui a janela na API)
        min_articles: Mínimo de artigos na janela recente (default 3)
        growth_threshold: Razão mínima sem sobreposição (default 1.5×; mínimo 1.0)
        agency_key: Filtrar por agência (opcional; validada no catálogo)
        limit: Máximo de temas (default 10)
        today: D em BRT (injetável), base das datas sugeridas no rodapé

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

    (data, _), coverage, names = await asyncio.gather(
        execute_compatible(
            client, ARTICLE_SUMMARY_URL, _TRENDING_QUERY, _TRENDING_LEGACY_QUERY, variables
        ),
        theme_coverage(client, window_days),
        catalog_display_names(catalog),  # gobus-mcp#17: nome do órgão, uma vez por resposta
    )
    themes = data.get("trendingThemes") or []
    follow = _follow_ups(
        themes,
        window_days=window_days,
        baseline_days=baseline_days,
        threshold=r0,
        agency_key=variables.get("agencyKey"),
        today=today or reference_date(),
    )

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
            return with_follow_ups(
                "\n".join(
                    [
                        *header,
                        "\nSem temas para comparar: a classificação de temas não cobre a "
                        "janela, então a ausência de tendências não significa estabilidade.",
                    ]
                ),
                follow,
            )
        return with_follow_ups(
            "\n".join(
                [
                    *header,
                    f"\nNenhum tema em crescimento detectado (últimos {window_days}d vs "
                    f"{baseline_days}d, razão ≥ {r0:.1f}×).",
                ]
            ),
            follow,
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
            lines.append(f"   Agências: {_agencies_line(top_arts, names)}")
            for art in top_arts[:3]:
                lines.append(f"   - {article_ref(art, 80)}")

    lines.append(
        "\n_Razão = artigos/dia na janela ÷ artigos/dia nos dias anteriores do baseline "
        "(suavização de Laplace). growthScore = cálculo da API, com o baseline incluindo a "
        "janela._"
    )
    return with_follow_ups("\n".join(lines), follow)
