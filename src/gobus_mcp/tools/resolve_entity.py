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

API_MAX_LIMIT = 20  # o resolver do entitySearch limita a 20
OVERFETCH = 3  # o entitySearch une alias_exact e trgm_fuzzy e repete o mesmo entityId


def dedup_by_entity_id(results: list[dict]) -> list[dict]:
    """Um resultado por ``entityId``, na ordem da 1ª aparição, com a linha de maior
    confiança (o ``alias_exact`` de 1.00 vence o ``trgm_fuzzy`` do mesmo id)."""
    best: dict[str, dict] = {}
    for r in results:
        key = r.get("entityId")
        current = best.get(key)
        if current is None or (r.get("confidence") or 0) > (current.get("confidence") or 0):
            best[key] = r  # dict mantém a ordem da 1ª inserção da chave
    return list(best.values())


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
        Markdown com os resultados de entidades encontradas, um por ``entityId`` (a API
        repete o id quando ele casa por mais de um alias ou por alias e trigrama; a tool
        pede folga, até o teto de 20, e corta em ``limit`` depois do dedup).
    """
    limit = max(1, limit)
    variables: dict = {"query": query, "limit": min(limit * OVERFETCH, API_MAX_LIMIT)}
    if entity_type:
        variables["entityType"] = entity_type.upper()

    data = await client.execute(_ENTITY_SEARCH_QUERY, variables)
    results = dedup_by_entity_id(data.get("entitySearch") or [])[:limit]

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
