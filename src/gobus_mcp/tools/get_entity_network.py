from gobus_mcp.client import GobusGraphQLClient

_NETWORK_QUERY = """
query EntityNetwork($id: String!, $depth: Int, $limit: Int) {
  entityNetwork(id: $id, depth: $depth, limit: $limit) {
    nodes { entityId canonicalName type wikidataId }
    edges { src dst weight kind }
  }
}
"""

_MAX_OUTPUT_EDGES = 50


async def get_entity_network(
    entity_id: str,
    client: GobusGraphQLClient,
    depth: int = 1,
    limit: int = 50,
    max_nodes: int = 20,
    node_types: str = "",
) -> str:
    data = await client.execute(
        _NETWORK_QUERY,
        {"id": entity_id, "depth": min(depth, 2), "limit": min(limit, 200)},
    )
    network = data.get("entityNetwork") or {}
    nodes = network.get("nodes") or []
    edges = network.get("edges") or []

    if not nodes:
        return f"Nenhuma rede encontrada para: `{entity_id}`"

    warnings = []
    if depth >= 2:
        warnings.append(
            "⚠️ **depth=2** pode retornar centenas de nós. "
            "Use `node_types` (ex: `\"PER,ORG\"`) para filtrar."
        )

    if node_types:
        allowed = {t.strip().upper() for t in node_types.split(",") if t.strip()}
        nodes = [
            n for n in nodes
            if n.get("type", "").upper() in allowed or n["entityId"] == entity_id
        ]

    total_nodes = len(nodes)
    nodes_shown = nodes[:max_nodes]

    node_map = {n["entityId"]: n["canonicalName"] or n["entityId"] for n in nodes_shown}

    lines = [f"# Rede de entidades: {node_map.get(entity_id, entity_id)}\n"]
    if warnings:
        for w in warnings:
            lines.append(f"> {w}\n")

    lines.append(f"**{total_nodes} nós · {len(edges)} conexões**\n")
    lines.append("## Nós")

    for node in nodes_shown:
        marker = " ← **[CENTRO]**" if node["entityId"] == entity_id else ""
        wikidata = (
            f" ([W](https://www.wikidata.org/wiki/{node.get('wikidataId')}))"
            if node.get("wikidataId") else ""
        )
        lines.append(
            f"- `{node['entityId']}` **{node.get('canonicalName', '')}** "
            f"({node.get('type', '')}){wikidata}{marker}"
        )

    if total_nodes > max_nodes:
        lines.append(
            f"\n> … **{total_nodes - max_nodes} nós adicionais omitidos**. "
            f"Use `node_types` para filtrar ou aumente `max_nodes`."
        )

    if edges:
        lines.append("\n## Conexões mais fortes")
        top_edges = sorted(edges, key=lambda e: e.get("weight", 0), reverse=True)[:_MAX_OUTPUT_EDGES]
        for edge in top_edges:
            src_name = node_map.get(edge["src"], edge["src"])
            dst_name = node_map.get(edge["dst"], edge["dst"])
            kind = edge.get("kind") or ""
            kind_str = f" [{kind}]" if kind else ""
            lines.append(
                f"- **{src_name}** ↔ **{dst_name}**{kind_str} ({edge.get('weight', 0)} artigos)"
            )

    return "\n".join(lines)
