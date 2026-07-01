import datetime

from gobus_mcp.client import GobusGraphQLClient

_ARTICLE_QUERY = """
query ScoreArticle($uniqueId: String!) {
    article(uniqueId: $uniqueId) {
        uniqueId
        title
        agency
        agencyName
        publishedAt
        features {
            readabilityFlesch
            wordCount
            entities { type }
        }
    }
}
"""

_ANALYTICS_QUERY = """
query ScoreArticleBenchmark($agencies: [String!]!, $dateFrom: String!, $dateTo: String!, $granularity: Granularity!) {
    agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: $granularity) {
        articleCount
        avgReadabilityFlesch
        avgWordCount
    }
}
"""


def _readability_score(flesch: float | None) -> float | None:
    """Nota 0-10 de legibilidade a partir do índice Flesch."""
    if flesch is None:
        return None
    if flesch >= 50:
        return 10.0
    if flesch >= 30:
        return 7.0
    if flesch >= 10:
        return 5.0
    if flesch >= 0:
        return 3.0
    return 1.0


def _conciseness_score(word_count: int | None, avg_word_count: float) -> float:
    """Nota 0-10 de concisão comparando o artigo ao benchmark da agência."""
    if not word_count or avg_word_count <= 0:
        return 5.0  # sem base de comparação → neutro, sem penalidade
    ratio = word_count / avg_word_count
    if ratio <= 0.8:
        return 10.0
    if ratio <= 1.0:
        return 8.0
    if ratio <= 1.3:
        return 6.0
    if ratio <= 1.6:
        return 4.0
    return 2.0


def _entity_density_score(entity_count: int, word_count: int | None) -> float:
    """Nota 0-10 de densidade de entidades por 100 palavras."""
    denom = max((word_count or 0) / 100, 1)
    density = entity_count / denom
    if density >= 2:
        return 8.0
    if density >= 1:
        return 6.0
    if density >= 0.5:
        return 4.0
    return 2.0


def _weighted_benchmark(rows: list[dict]) -> tuple[float, float]:
    """Média ponderada por articleCount de Flesch e wordCount do benchmark."""
    total = sum(r.get("articleCount") or 0 for r in rows)
    if total <= 0:
        return 0.0, 0.0
    flesch = sum((r.get("avgReadabilityFlesch") or 0.0) * (r.get("articleCount") or 0) for r in rows) / total
    wc = sum((r.get("avgWordCount") or 0.0) * (r.get("articleCount") or 0) for r in rows) / total
    return flesch, wc


async def score_article(unique_id: str, client: GobusGraphQLClient) -> str:
    """Atribui uma nota editorial a um artigo comparando-o ao benchmark da agência.

    Combina três dimensões — legibilidade (Flesch), concisão (tamanho vs. média da
    agência) e densidade de entidades — numa nota geral 0-10 ponderada
    (50% legibilidade, 30% concisão, 20% densidade).

    Args:
        unique_id: ID único do artigo (obtido via search_news).
        client: Cliente GraphQL.

    Returns:
        Markdown com nota geral, notas por dimensão e benchmark da agência.
    """
    article_data = await client.execute(_ARTICLE_QUERY, {"uniqueId": unique_id})
    art = article_data.get("article")
    if not art:
        return f"Artigo não encontrado: `{unique_id}`"

    features = art.get("features")
    if not features:
        return (
            f"# {art.get('title', unique_id)}\n\n"
            "features não disponíveis para este artigo — sem legibilidade, contagem "
            "de palavras ou entidades para pontuar."
        )

    flesch = features.get("readabilityFlesch")
    word_count = features.get("wordCount")
    entities = features.get("entities") or []
    entity_count = len(entities)

    agency = art.get("agency") or ""
    agency_name = art.get("agencyName") or agency

    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=90)).isoformat()
    date_to = today.isoformat()
    analytics_data = await client.execute(_ANALYTICS_QUERY, {
        "agencies": [agency],
        "dateFrom": date_from,
        "dateTo": date_to,
        "granularity": "MONTH",
    })
    rows = analytics_data.get("agencyAnalytics") or []
    bench_flesch, bench_wc = _weighted_benchmark(rows)

    readability = _readability_score(flesch)
    conciseness = _conciseness_score(word_count, bench_wc)
    entity_density = _entity_density_score(entity_count, word_count)

    readability_for_overall = readability if readability is not None else 5.0
    overall = readability_for_overall * 0.5 + conciseness * 0.3 + entity_density * 0.2

    pub_at = (art.get("publishedAt") or "")[:10]
    flesch_display = f"{flesch:.1f}" if flesch is not None else "N/A"
    readability_display = f"{readability:.0f}/10" if readability is not None else "N/A"

    lines = [
        f"# Score Editorial: {art.get('title', unique_id)}",
        f"**[{agency}] {agency_name}** · {pub_at}\n",
        f"## Nota Geral: {overall:.1f}/10\n",
        "## Notas por Dimensão",
        f"- **Legibilidade:** {readability_display} — Flesch {flesch_display}",
        f"- **Concisão:** {conciseness:.0f}/10 — {word_count or 0} palavras "
        f"(benchmark {bench_wc:.0f})",
        f"- **Densidade de Entidades:** {entity_density:.0f}/10 — "
        f"{entity_count} entidades em {word_count or 0} palavras",
        f"\n## Benchmark da Agência ({agency})",
        f"- Flesch médio (90 dias): {bench_flesch:.1f}",
        f"- Palavras médias por artigo: {bench_wc:.0f}",
    ]

    return "\n".join(lines)
