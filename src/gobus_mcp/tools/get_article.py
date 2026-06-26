from gobus_mcp.client import GobusGraphQLClient

_ARTICLE_QUERY = """
query GetArticle($uniqueId: String!) {
  article(uniqueId: $uniqueId) {
    uniqueId
    title
    content
    summary
    agencyName
    agency
    publishedAt
    url
    tags
    features {
      viewCount
      uniqueSessions
      trendingScore
      wordCount
      readabilityFlesch
      entities {
        text
        type
        count
        canonicalId
      }
    }
  }
}
"""


async def get_article(unique_id: str, client: GobusGraphQLClient) -> str:
    """Retorna conteúdo completo de um artigo pelo ID único.

    Args:
        unique_id: ID único do artigo (ex: obtido via search_news)

    Returns:
        Markdown com artigo completo incluindo features e entidades mencionadas.
    """
    data = await client.execute(_ARTICLE_QUERY, {"uniqueId": unique_id})
    art = data.get("article")
    if not art:
        return f"Artigo não encontrado: `{unique_id}`"

    pub_at = (art.get("publishedAt") or "")[:10]
    tags = ", ".join(art.get("tags") or [])
    agency_code = art.get("agency") or ""
    agency_name = art.get("agencyName") or ""
    if agency_code and agency_name:
        agency_str = f"[{agency_code}] {agency_name}"
    elif agency_code:
        agency_str = f"[{agency_code}]"
    else:
        agency_str = agency_name
    lines = [
        f"# {art['title']}\n",
        f"**{agency_str}** · {pub_at}",
        f"🔗 {art.get('url', '')}",
    ]
    if tags:
        lines.append(f"Tags: {tags}")

    features = art.get("features") or {}
    if features:
        wc = features.get("wordCount")
        flesch = features.get("readabilityFlesch")
        vc = features.get("viewCount")
        ts = features.get("trendingScore")
        meta_parts = []
        if wc:
            read_min = round(wc / 200)
            meta_parts.append(f"⏱ {read_min} min leitura ({wc} palavras)")
        if flesch:
            nivel = "fácil" if flesch > 70 else ("médio" if flesch > 50 else "difícil")
            meta_parts.append(f"📖 Legibilidade: {nivel} ({flesch:.0f})")
        if vc:
            meta_parts.append(f"👁 {vc:,} visualizações")
        if ts and ts > 1.0:
            meta_parts.append(f"🔥 Em alta (score {ts:.1f})")
        if meta_parts:
            lines.append("\n" + " · ".join(meta_parts))

        entities = features.get("entities") or []
        if entities:
            lines.append("\n## Entidades mencionadas")
            by_type: dict[str, list] = {}
            for e in entities:
                by_type.setdefault(e.get("type", "MISC"), []).append(e)
            type_labels = {"ORG": "Instituições", "PER": "Pessoas", "LOC": "Locais",
                           "EVENT": "Eventos", "POLICY": "Políticas", "LAW": "Leis"}
            for etype, items in by_type.items():
                label = type_labels.get(etype, etype)
                names = [f"{e['text']} ({e.get('count', 0)}x)" for e in items[:8]]
                lines.append(f"**{label}:** {', '.join(names)}")

    lines.append("\n## Conteúdo")
    lines.append(art.get("content") or art.get("summary") or "")

    return "\n".join(lines)
