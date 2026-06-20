from gobus_mcp.client import GobusGraphQLClient

_AGENCIES_QUERY = """
{
  agencies {
    code
    label
  }
}
"""


async def fetch_agencies(client: GobusGraphQLClient) -> str:
    data = await client.execute(_AGENCIES_QUERY)
    agencies = data.get("agencies") or []
    if not agencies:
        return "Nenhuma agência encontrada."
    lines = ["# Agências Governamentais\n"]
    for ag in sorted(agencies, key=lambda x: x.get("label", "")):
        code = ag.get("code", "")
        label = ag.get("label", code)
        lines.append(f"- **{label}** (`{code}`)")
    return "\n".join(lines)
