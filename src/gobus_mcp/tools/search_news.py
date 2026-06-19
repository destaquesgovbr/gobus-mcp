from gobus_mcp.client import GobusGraphQLClient

_SEARCH_QUERY = """
query SearchNews($query: String!, $filter: ArticleFilter, $page: Int) {
  search(query: $query, filter: $filter, page: $page) {
    articles {
      uniqueId
      title
      agencyName
      publishedAt
      summary
      url
      features {
        trendingScore
        viewCount
      }
    }
    found
    page
  }
}
"""


async def search_news(
    query: str,
    client: GobusGraphQLClient,
    agency_key: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> str:
    """Busca notícias no portal Gov.BR por texto e/ou agência.

    Args:
        query: Texto livre para busca semântica/full-text
        agency_key: Chave da agência (ex: "mec", "ms") para filtrar
        page: Página de resultados (default 1)
        limit: Resultados por página (default 10, máx 50)

    Returns:
        Markdown com artigos encontrados e metadados de paginação.
    """
    variables: dict = {"query": query, "page": page}
    if agency_key:
        variables["filter"] = {"agencies": [agency_key]}

    data = await client.execute(_SEARCH_QUERY, variables)
    result = data.get("search") or {}
    articles = result.get("articles") or []
    found = result.get("found", 0)

    if not articles:
        return f"Nenhum resultado encontrado para: **{query}**"

    lines = [f"# Resultados: {query}\n\n**{found:,} artigos encontrados** (página {page})\n"]
    for art in articles:
        pub_at = art.get("publishedAt", "")[:10] if art.get("publishedAt") else ""
        agency = art.get("agencyName", "")
        features = art.get("features") or {}
        trending = features.get("trendingScore")
        trending_str = f" 🔥 trending={trending:.1f}" if trending and trending > 1.0 else ""
        lines.append(
            f"## {art['title']}\n"
            f"**{agency}** · {pub_at}{trending_str}\n"
            f"{art.get('summary') or ''}\n"
            f"🔗 {art.get('url', '')}  ID: `{art.get('uniqueId', '')}`\n"
        )

    return "\n".join(lines)
