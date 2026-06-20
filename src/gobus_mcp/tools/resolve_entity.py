from gobus_mcp.client import GobusGraphQLClient

_ENTITY_SEARCH_QUERY = """
query EntitySearch($query: String!, $entityType: EntityKind, $limit: Int) {
  entitySearch(query: $query, entityType: $entityType, limit: $limit) {
    entityId
    canonicalName
    type
    description
    wikidataUrl
    agencyKey
    aliases
    articleCount
    confidence
    matchType
  }
}
"""


async def resolve_entity(
    query: str,
    client: GobusGraphQLClient,
    entity_type: str | None = None,
    limit: int = 5,
) -> str:
    """Resolve o nome de uma entidade para seu entityId canônico.

    Args:
        query: Nome ou alias a buscar (ex: "MEC", "Ministério da Educação")
        entity_type: Tipo opcional — ORG, PER, LOC, EVENT, POLICY, LAW
        limit: Máximo de resultados (default 5)

    Returns:
        Markdown com os resultados de entidades encontradas.
    """
    variables: dict = {"query": query, "limit": limit}
    if entity_type:
        variables["entityType"] = entity_type.upper()

    data = await client.execute(_ENTITY_SEARCH_QUERY, variables)
    results = data.get("entitySearch") or []

    if not results:
        return f"Nenhuma entidade encontrada para: **{query}**"

    lines = [f"# Entidades encontradas para: {query}\n"]
    for r in results:
        wikidata = f" · [Wikidata]({r['wikidataUrl']})" if r.get("wikidataUrl") else ""
        aliases = ", ".join(r.get("aliases") or [])
        aliases_str = f" · Aliases: {aliases}" if aliases else ""
        lines.append(
            f"## {r['canonicalName']} ({r['type']})\n"
            f"- **ID:** `{r['entityId']}`{wikidata}\n"
            f"- **Artigos:** {r.get('articleCount', 0)} · "
            f"**Confiança:** {r.get('confidence', 0):.2f} ({r.get('matchType', '')})"
            f"{aliases_str}\n"
        )
        if r.get("description"):
            lines.append(f"- {r['description']}\n")

    return "\n".join(lines)
