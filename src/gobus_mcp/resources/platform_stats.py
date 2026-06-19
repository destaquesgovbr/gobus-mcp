from gobus_mcp.client import GobusGraphQLClient

_STATS_QUERY = """
{
  analyticsKpis(range: { days: 30 }) {
    total
    activeThemes
    activeAgencies
    dailyAverage
  }
}
"""


async def fetch_platform_stats(client: GobusGraphQLClient) -> str:
    data = await client.execute(_STATS_QUERY)
    kpis = data.get("analyticsKpis") or {}
    return (
        f"# Plataforma Destaques Gov.BR — Últimos 30 dias\n\n"
        f"- **Total de artigos:** {kpis.get('total', 0):,}\n"
        f"- **Temas ativos:** {kpis.get('activeThemes', 0)}\n"
        f"- **Agências ativas:** {kpis.get('activeAgencies', 0)}\n"
        f"- **Média diária:** {kpis.get('dailyAverage', 0):.1f} artigos/dia\n"
    )
