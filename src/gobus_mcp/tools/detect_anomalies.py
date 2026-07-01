import asyncio

from gobus_mcp.client import GobusGraphQLClient

_THEMES_QUERY = """
query DetectAnomalyThemes($windowDays: Int!, $baselineDays: Int!, $growthThreshold: Float!, $limit: Int!) {
    trendingThemes(windowDays: $windowDays, baselineDays: $baselineDays, growthThreshold: $growthThreshold, limit: $limit) {
        themeLabel
        themeCode
        growthScore
        windowCount
        baselineDailyAvg
    }
}
"""

_ENTITIES_QUERY = """
query DetectAnomalyEntities($limit: Int!) {
    trendingEntities(limit: $limit) {
        entityId
        canonicalName
        type
        trendingScore
        volumeRatio
        windowCount
        windowAgencies
    }
}
"""

# Limiares de "silêncio concentrado": alto volumeRatio + poucas agências cobrindo.
_SENSITIVITY = {
    "high": {"volume_ratio": 2.0, "window_agencies": 8},
    "medium": {"volume_ratio": 3.0, "window_agencies": 5},
    "low": {"volume_ratio": 5.0, "window_agencies": 3},
}


async def detect_anomalies(client: GobusGraphQLClient, sensitivity: str = "medium") -> str:
    """Detecta anomalias comunicacionais: picos sustentados e cobertura concentrada.

    Cruza duas janelas de trendingThemes (3d/21d e 7d/28d) para achar temas com
    pico sustentado (presentes em ambas), e inspeciona trendingEntities para achar
    "silêncio concentrado" — entidades com alto volume relativo cobertas por poucas
    agências (sinal de assunto empurrado por poucos emissores).

    Args:
        client: Cliente GraphQL.
        sensitivity: "high" | "medium" | "low" — controla o limiar de concentração.

    Returns:
        Markdown com seções de picos sustentados, cobertura concentrada e tendências normais.
    """
    thresholds = _SENSITIVITY.get(sensitivity, _SENSITIVITY["medium"])

    themes_3d_data, themes_7d_data = await asyncio.gather(
        client.execute(_THEMES_QUERY, {
            "windowDays": 3, "baselineDays": 21, "growthThreshold": 0.5, "limit": 15,
        }),
        client.execute(_THEMES_QUERY, {
            "windowDays": 7, "baselineDays": 28, "growthThreshold": 0.5, "limit": 15,
        }),
    )
    entities_data = await client.execute(_ENTITIES_QUERY, {"limit": 20})

    themes_3d = themes_3d_data.get("trendingThemes") or []
    themes_7d = themes_7d_data.get("trendingThemes") or []
    entities = entities_data.get("trendingEntities") or []

    by_code_3d = {t.get("themeCode") or t.get("themeLabel"): t for t in themes_3d}
    by_code_7d = {t.get("themeCode") or t.get("themeLabel"): t for t in themes_7d}
    sustained_codes = [c for c in by_code_3d if c in by_code_7d]

    concentrated = []
    normal = []
    for e in entities:
        vr = e.get("volumeRatio") or 0.0
        wa = e.get("windowAgencies")
        wa = wa if wa is not None else 999
        if vr > thresholds["volume_ratio"] and wa < thresholds["window_agencies"]:
            concentrated.append(e)
        else:
            normal.append(e)

    lines = [
        "## Detector de Anomalias Comunicacionais",
        f"**Sensibilidade:** {sensitivity}\n",
    ]

    lines.append("### Picos Sustentados")
    if sustained_codes:
        for code in sustained_codes:
            t3 = by_code_3d[code]
            t7 = by_code_7d[code]
            label = t3.get("themeLabel") or t7.get("themeLabel") or code
            lines.append(
                f"- **{label}** · growth 3d {t3.get('growthScore', 0):.1f}× / "
                f"7d {t7.get('growthScore', 0):.1f}× · "
                f"{t3.get('windowCount', 0)} artigos (janela 3d)"
            )
    else:
        lines.append("Nenhum pico sustentado detectado.")

    lines.append("\n### Cobertura Concentrada")
    if concentrated:
        for e in concentrated:
            lines.append(
                f"- **{e.get('canonicalName')}** ({e.get('type')}) · "
                f"volumeRatio {e.get('volumeRatio', 0):.1f}× · "
                f"apenas {e.get('windowAgencies')} agências"
            )
    else:
        lines.append("Nenhuma cobertura concentrada suspeita.")

    lines.append("\n### Tendências Normais")
    if normal:
        for e in normal:
            lines.append(
                f"- **{e.get('canonicalName')}** ({e.get('type')}) · "
                f"volumeRatio {e.get('volumeRatio', 0):.1f}× · "
                f"{e.get('windowAgencies')} agências"
            )
    else:
        lines.append("Nenhuma tendência normal restante.")

    return "\n".join(lines)
