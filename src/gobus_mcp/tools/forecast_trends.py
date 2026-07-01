import asyncio

from gobus_mcp.client import GobusGraphQLClient

_THEMES_QUERY = """
query ForecastThemes($windowDays: Int!, $baselineDays: Int!, $growthThreshold: Float!, $limit: Int!) {
    trendingThemes(windowDays: $windowDays, baselineDays: $baselineDays, growthThreshold: $growthThreshold, limit: $limit) {
        themeLabel
        themeCode
        growthScore
        windowCount
        baselineDailyAvg
    }
}
"""

# Pesos por janela na composição do score (janelas curtas pesam mais).
_WEIGHTS = {"3": 0.5, "7": 0.3, "21": 0.2}

_CONFIDENCE = {3: "alta", 2: "media", 1: "baixa"}


async def forecast_trends(
    client: GobusGraphQLClient,
    horizon_days: int = 21,
    limit: int = 5,
) -> str:
    """Projeta tendências combinando três janelas de detecção de temas.

    Cruza trendingThemes em janelas de 3, 7 e 21 dias. Cada tema recebe um score
    composto (média ponderada dos growthScores por janela), uma leitura de momentum
    (acelerando/desacelerando/estável comparando 3d vs 7d) e uma confiança segundo
    o número de janelas em que aparece.

    Args:
        client: Cliente GraphQL.
        horizon_days: Horizonte da projeção em dias (apenas informativo no título).
        limit: Máximo de temas retornados, ordenados por score composto.

    Returns:
        Markdown com tabela Tema | Score Composto | Momentum | Confiança.
    """
    r3_data, r7_data, r21_data = await asyncio.gather(
        client.execute(_THEMES_QUERY, {
            "windowDays": 3, "baselineDays": 14, "growthThreshold": 0.3, "limit": 20,
        }),
        client.execute(_THEMES_QUERY, {
            "windowDays": 7, "baselineDays": 28, "growthThreshold": 0.3, "limit": 20,
        }),
        client.execute(_THEMES_QUERY, {
            "windowDays": 21, "baselineDays": 84, "growthThreshold": 0.2, "limit": 20,
        }),
    )

    windows = {
        "3": r3_data.get("trendingThemes") or [],
        "7": r7_data.get("trendingThemes") or [],
        "21": r21_data.get("trendingThemes") or [],
    }

    themes: dict[str, dict] = {}
    for window_key, theme_list in windows.items():
        for t in theme_list:
            code = t.get("themeCode") or t.get("themeLabel")
            entry = themes.setdefault(code, {
                "label": t.get("themeLabel") or code,
                "scores": {},
            })
            entry["scores"][window_key] = t.get("growthScore") or 0.0

    ranked = []
    for entry in themes.values():
        scores = entry["scores"]
        composite = sum(_WEIGHTS[w] * scores.get(w, 0.0) for w in _WEIGHTS)
        s3 = scores.get("3", 0.0)
        s7 = scores.get("7", 0.0)
        if s3 > s7:
            momentum = "acelerando"
        elif s3 < s7:
            momentum = "desacelerando"
        else:
            momentum = "estavel"
        confidence = _CONFIDENCE.get(len(scores), "baixa")
        ranked.append({
            "label": entry["label"],
            "composite": composite,
            "momentum": momentum,
            "confidence": confidence,
        })

    ranked.sort(key=lambda r: r["composite"], reverse=True)
    top = ranked[:limit]

    lines = [
        f"## Forecast de Tendências — Horizonte {horizon_days} dias\n",
        "| Tema | Score Composto | Momentum | Confiança |",
        "|------|----------------|----------|-----------|",
    ]
    if top:
        for r in top:
            lines.append(
                f"| {r['label']} | {r['composite']:.2f} | {r['momentum']} | {r['confidence']} |"
            )
    else:
        lines.append("| — | — | — | — |")

    lines.append(
        "\n> Nota: a janela de 3 dias sofre viés de borda de fim de semana — picos "
        "podem refletir queda de publicação no sábado/domingo, não tendência real. "
        "Trate momentum \"acelerando\" com cautela quando a janela cruza um fim de semana."
    )

    return "\n".join(lines)
