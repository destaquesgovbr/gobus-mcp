from gobus_mcp.client import GobusGraphQLClient

_NETWORK_QUERY = """
query EntityNetwork($id: String!, $depth: Int, $limit: Int) {
  entityNetwork(id: $id, depth: $depth, limit: $limit) {
    nodes {
      entityId canonicalName type wikidataId
    }
    edges {
      src dst weight kind
    }
  }
}
"""


async def get_entity_network(
    entity_id: str,
    client: GobusGraphQLClient,
    depth: int = 1,
    limit: int = 50,
) -> str:
    """Retorna a rede de co-menções ao redor de uma entidade.

    Args:
        entity_id: ID canônico da entidade (ex: "Q4294522")
        depth: Profundidade da busca (1 ou 2)
        limit: Máximo de arestas a retornar

    Returns:
        Markdown com nós e arestas da rede de entidades.
    """
    data = await client.execute(_NETWORK_QUERY, {"id": entity_id, "depth": min(depth, 2), "limit": min(limit, 200)})
    network = data.get("entityNetwork") or {}
    nodes = network.get("nodes") or []
    edges = network.get("edges") or []

    if not nodes:
        return f"Nenhuma rede encontrada para: `{entity_id}`"

    node_map = {n["entityId"]: n["canonicalName"] or n["entityId"] for n in nodes}

    lines = [
        f"# Rede de entidades: {node_map.get(entity_id, entity_id)}\n",
        f"**{len(nodes)} nós · {len(edges)} conexões**\n",
        "## Nós",
    ]
    for node in nodes:
        marker = " ← **[CENTRO]**" if node["entityId"] == entity_id else ""
        wikidata = f" ([W](https://www.wikidata.org/wiki/{node.get('wikidataId')}))" if node.get("wikidataId") else ""
        lines.append(f"- `{node['entityId']}` **{node.get('canonicalName', '')}** ({node.get('type', '')}){wikidata}{marker}")

    if edges:
        lines.append("\n## Conexões mais fortes")
        top_edges = sorted(edges, key=lambda e: e.get("weight", 0), reverse=True)[:20]
        for edge in top_edges:
            src_name = node_map.get(edge["src"], edge["src"])
            dst_name = node_map.get(edge["dst"], edge["dst"])
            lines.append(f"- **{src_name}** ↔ **{dst_name}** ({edge.get('weight', 0)} artigos)")

    return "\n".join(lines)
