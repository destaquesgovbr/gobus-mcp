from gobus_mcp.client import GobusGraphQLClient

_ENTITY_SEARCH_QUERY = """
query EntitySearch($query: String!, $entityType: EntityKind) {
  entitySearch(query: $query, entityType: $entityType, limit: 1) {
    entityId canonicalName type description wikidataUrl agencyKey
    aliases articleCount confidence matchType
  }
}
"""

_ENTITY_COVERAGE_QUERY = """
query EntityCoverage($entityId: String!, $granularity: Granularity, $dateFrom: String, $dateTo: String) {
  entityCoverage(entityId: $entityId, granularity: $granularity, dateFrom: $dateFrom, dateTo: $dateTo) {
    period agencyKey agencyName articleCount totalMentions avgSentimentScore
  }
}
"""

_RELATED_ENTITIES_QUERY = """
query RelatedEntities($id: String!, $limit: Int) {
  relatedEntities(id: $id, limit: $limit) {
    canonicalId
    canonicalName
    type
    weight
  }
}
"""


async def get_entity_profile(
    entity_name: str,
    client: GobusGraphQLClient,
    entity_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    summary_only: bool = False,
) -> str:
    """Perfil completo de uma entidade: cobertura temporal + entidades relacionadas.

    Args:
        entity_name: Nome ou alias da entidade
        entity_type: Tipo — ORG, PER, LOC, EVENT, POLICY, LAW (opcional)
        date_from: Data de início (ISO: "2024-01-01") — opcional
        date_to: Data de fim (ISO: "2024-12-31") — opcional

    Returns:
        Markdown com perfil completo da entidade.
    """
    search_vars: dict = {"query": entity_name}
    if entity_type:
        search_vars["entityType"] = entity_type.upper()

    search_data = await client.execute(_ENTITY_SEARCH_QUERY, search_vars)
    hits = search_data.get("entitySearch") or []
    if not hits:
        return f"Entidade não encontrada: **{entity_name}**"

    entity = hits[0]
    entity_id = entity["entityId"]

    coverage_vars: dict = {"entityId": entity_id, "granularity": "MONTH"}
    if date_from:
        coverage_vars["dateFrom"] = date_from
    if date_to:
        coverage_vars["dateTo"] = date_to
    coverage_data = await client.execute(_ENTITY_COVERAGE_QUERY, coverage_vars)
    coverage = coverage_data.get("entityCoverage") or []

    related_data = await client.execute(_RELATED_ENTITIES_QUERY, {"id": entity_id, "limit": 10})
    related = related_data.get("relatedEntities") or []

    wikidata = f"[Wikidata]({entity['wikidataUrl']})" if entity.get("wikidataUrl") else "—"
    aliases = ", ".join(entity.get("aliases") or [])

    lines = [
        f"# {entity['canonicalName']} ({entity['type']})",
        f"**ID:** `{entity_id}` · {wikidata}",
        f"**Artigos:** {entity.get('articleCount', 0):,}",
    ]
    if aliases:
        lines.append(f"**Aliases:** {aliases}")
    if entity.get("description"):
        lines.append(f"\n{entity['description']}")

    if summary_only:
        total_articles = sum(p["articleCount"] for p in coverage)
        lines.append(f"\n**Cobertura total:** {total_articles} artigos")
        if related:
            top3_str = ", ".join(
                f"{r.get('canonicalName')} ({r.get('type')})" for r in related[:3]
            )
            lines.append(f"**Top relacionadas:** {top3_str}")
        return "\n".join(lines)

    if coverage:
        total_articles = sum(p["articleCount"] for p in coverage)
        total_mentions = sum(p["totalMentions"] for p in coverage)
        lines.append(f"\n## Cobertura ({total_articles} artigos, {total_mentions} menções)")
        for point in coverage[-12:]:
            agency = point.get("agencyName") or point.get("agencyKey", "")
            sent = point.get("avgSentimentScore")
            sent_str = f" · sentimento {sent:.2f}" if sent else ""
            lines.append(f"- **{point['period']}** — {point['articleCount']} artigos ({agency}){sent_str}")

    if related:
        lines.append("\n## Entidades relacionadas (co-menção)")
        for r in related[:8]:
            lines.append(f"- **{r.get('canonicalName', r.get('canonicalId'))}** ({r.get('type', '')}) · {r.get('weight', 0)} artigos")

    return "\n".join(lines)
