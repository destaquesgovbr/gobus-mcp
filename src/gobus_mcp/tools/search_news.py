from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.formatting import agency_label, fmt_int, md_link

_SEARCH_QUERY = """
query SearchNews($query: String!, $filter: ArticleFilter, $page: Int) {
  search(query: $query, filter: $filter, page: $page) {
    articles {
      uniqueId title agencyName agency publishedAt summary url
      features { trendingScore viewCount }
    }
    found page
  }
}
"""


async def search_news(
    query: str,
    client: GobusGraphQLClient,
    agency_key: str | None = None,
    page: int = 1,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    effective_limit = min(limit, 50)
    variables: dict = {"query": query, "page": page}

    filter_dict: dict = {}
    if agency_key:
        filter_dict["agencies"] = [agency_key]
    if date_from:
        filter_dict["startDate"] = date_from
    if date_to:
        filter_dict["endDate"] = date_to
    if filter_dict:
        variables["filter"] = filter_dict

    data = await client.execute(_SEARCH_QUERY, variables)
    result = data.get("search") or {}
    articles = (result.get("articles") or [])[:effective_limit]
    found = result.get("found") or 0

    if not articles:
        msg = f"Nenhum resultado encontrado para: **{query}**"
        if agency_key:
            msg += f"\n\n> Chave `{agency_key}` não encontrou artigos. Consulte `gobus://agencies` para códigos válidos."
        return msg

    lines = [f"# Resultados: {query}\n\n**{fmt_int(found)} artigos encontrados** (página {page})\n"]
    for art in articles:
        pub_at = art.get("publishedAt", "")[:10] if art.get("publishedAt") else ""
        agency_str = agency_label(art.get("agency"), art.get("agencyName"))
        features = art.get("features") or {}
        trending = features.get("trendingScore")
        trending_str = f" 🔥 trending={trending:.1f}" if trending and trending > 1.0 else ""
        lines.append(
            f"## {md_link(art['title'], art.get('url'))}\n"
            f"**{agency_str}** · {pub_at}{trending_str}\n"
            f"{art.get('summary') or ''}\n"
            f"ID: `{art.get('uniqueId', '')}`\n"
        )

    return "\n".join(lines)
