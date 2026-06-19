from gobus_mcp.client import GobusGraphQLClient

_THEMES_QUERY = """
{
  themes {
    code
    label
  }
}
"""


async def fetch_themes(client: GobusGraphQLClient) -> str:
    data = await client.execute(_THEMES_QUERY)
    themes = data.get("themes") or []
    if not themes:
        return "Nenhum tema encontrado."
    lines = ["# Taxonomia de Temas\n"]
    for t in themes:
        lines.append(f"- **{t.get('label', '')}** (`{t.get('code', '')}`)")
    return "\n".join(lines)
