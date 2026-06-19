from gobus_mcp.client import GobusGraphQLClient

_AGENCIES_QUERY = """
{
  agencies {
    key
    name
  }
}
"""


async def fetch_agencies(client: GobusGraphQLClient) -> str:
    data = await client.execute(_AGENCIES_QUERY)
    agencies = data.get("agencies") or []
    if not agencies:
        return "Nenhuma agência encontrada."
    lines = ["# Agências Governamentais\n"]
    for ag in sorted(agencies, key=lambda x: x.get("name", "")):
        key = ag.get("key", "")
        name = ag.get("name", key)
        lines.append(f"- **{name}** (`{key}`)")
    return "\n".join(lines)
