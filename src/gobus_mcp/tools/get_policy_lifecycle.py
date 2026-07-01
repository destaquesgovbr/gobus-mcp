from collections import defaultdict

from gobus_mcp.client import GobusGraphQLClient, GobusGraphQLError

_ENTITY_SEARCH_QUERY = """
query EntitySearch($query: String!, $entityType: EntityKind, $limit: Int) {
  entitySearch(query: $query, entityType: $entityType, limit: $limit) {
    entityId canonicalName type description wikidataUrl agencyKey aliases articleCount confidence matchType
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

_SEARCH_QUERY = """
query SearchNews($query: String!, $filter: ArticleFilter, $page: Int) {
  search(query: $query, filter: $filter, page: $page) {
    articles { uniqueId title agencyName agency publishedAt summary url features { trendingScore viewCount } }
    found page
  }
}
"""

_POLICY_DETAILS_QUERY = """
query PolicyDetails($entityId: String!) {
  policyDetails(entityId: $entityId) {
    domain lifecyclePhase enablingLaws responsibleAgencies targetPopulation firstMentionedDate
  }
}
"""

# Limiar de volume relativo ao pico para classificação de fases:
# acima de 40% do pico → IMPLEMENTATION; abaixo → ROUTINE.
_IMPLEMENTATION_RATIO_THRESHOLD = 0.40


def _analyze_coverage(coverage: list[dict]) -> list[dict]:
    """Classifica cada período da série temporal em uma fase do ciclo de vida.

    Fases:
    - ANNOUNCED: período de pico máximo (lançamento/anúncio).
    - IMPLEMENTATION: volume > 40% do pico (sustentação pós-lançamento).
    - ROUTINE: volume <= 40% do pico (queda/manutenção).

    Args:
        coverage: Lista de pontos da série temporal (entityCoverage).

    Returns:
        Lista de pontos com campo adicional "phase".
    """
    if not coverage:
        return []

    sorted_cov = sorted(coverage, key=lambda x: x["period"])
    peak_count = max(c["articleCount"] for c in sorted_cov)
    peak_idx = max(range(len(sorted_cov)), key=lambda i: sorted_cov[i]["articleCount"])

    result = []
    for i, point in enumerate(sorted_cov):
        count = point["articleCount"]
        ratio = count / peak_count if peak_count > 0 else 0.0
        if i == peak_idx:
            phase = "ANNOUNCED"
        elif ratio >= _IMPLEMENTATION_RATIO_THRESHOLD:
            phase = "IMPLEMENTATION"
        else:
            phase = "ROUTINE"
        result.append({**point, "phase": phase, "ratio": ratio})

    return result


def _narrative_anchors(phases_data: list[dict]) -> dict[str, str]:
    """Retorna a agência dominante (por volume) em cada fase — âncora narrativo.

    Args:
        phases_data: Saída de _analyze_coverage (já com campo "phase").

    Returns:
        Dict {fase: agência_dominante}.
    """
    phase_agency_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for point in phases_data:
        phase = point["phase"]
        agency = point.get("agencyName") or point.get("agencyKey") or "Desconhecida"
        phase_agency_count[phase][agency] += point["articleCount"]

    return {
        phase: max(agencies, key=lambda a: agencies[a])
        for phase, agencies in phase_agency_count.items()
    }


async def get_policy_lifecycle(
    policy_name: str,
    client: GobusGraphQLClient,
    date_from: str = "2024-01-01",
) -> str:
    """Ciclo de vida comunicacional de uma política pública no portal Gov.BR.

    Resolve o nome da política, obtém a série temporal de cobertura mensal e
    classifica cada período em uma fase: ANNOUNCED (pico de lançamento),
    IMPLEMENTATION (sustentação), ROUTINE (queda/manutenção). Identifica as
    agências dominantes por fase (âncoras narrativos) e apresenta artigos
    representativos do pico.

    Opcionalmente enriquece com metadados de policyDetails (graceful fallback
    caso a query não exista na graphql-api).

    Args:
        policy_name: Nome ou alias da política (ex: "Pé-de-Meia").
        client: Cliente GraphQL.
        date_from: Data de início da série temporal (ISO). Padrão: "2024-01-01".

    Returns:
        Markdown com fases, âncoras narrativos e perspectiva da fase atual.
    """
    # 1. Resolver nome → entityId
    search_data = await client.execute(_ENTITY_SEARCH_QUERY, {
        "query": policy_name,
        "entityType": "POLICY",
        "limit": 1,
    })
    hits = search_data.get("entitySearch") or []
    if not hits:
        return f"Política não encontrada: **{policy_name}**"

    entity = hits[0]
    entity_id = entity["entityId"]
    canonical_name = entity["canonicalName"]

    # 2. Série temporal de cobertura mensal
    coverage_data = await client.execute(_ENTITY_COVERAGE_QUERY, {
        "entityId": entity_id,
        "granularity": "MONTH",
        "dateFrom": date_from,
    })
    coverage = coverage_data.get("entityCoverage") or []

    if not coverage:
        return (
            f"**{canonical_name}**: dados insuficientes de cobertura para análise do "
            "ciclo de vida. Tente ampliar o período com um date_from anterior."
        )

    # 3. Metadados de política (opcional — graceful fallback)
    try:
        policy_data = await client.execute(_POLICY_DETAILS_QUERY, {"entityId": entity_id})
        pd = policy_data.get("policyDetails")
    except (GobusGraphQLError, Exception):
        pd = None

    # 4. Análise de fases
    phases_data = _analyze_coverage(coverage)
    anchors = _narrative_anchors(phases_data)
    current_phase = phases_data[-1]["phase"] if phases_data else "DESCONHECIDA"
    peak_point = next((p for p in phases_data if p["phase"] == "ANNOUNCED"), None)

    # 5. Artigos representativos da fase de pico
    articles: list[dict] = []
    if peak_point:
        try:
            search_result = await client.execute(_SEARCH_QUERY, {
                "query": policy_name,
                "page": 1,
            })
            articles = (search_result.get("search") or {}).get("articles") or []
        except Exception:
            articles = []

    # 6. Montar Markdown
    lines = [f"# Ciclo de Vida: {canonical_name}"]
    lines.append(f"\n**ID:** `{entity_id}` · **Fase atual:** {current_phase}")

    if pd:
        if pd.get("domain"):
            lines.append(f"**Domínio:** {pd['domain']}")
        if pd.get("targetPopulation"):
            pop = ", ".join(pd["targetPopulation"])
            lines.append(f"**População-alvo:** {pop}")
        if pd.get("responsibleAgencies"):
            agencies_str = ", ".join(pd["responsibleAgencies"])
            lines.append(f"**Agências responsáveis:** {agencies_str}")

    lines.append("\n## Fases Identificadas\n")
    lines.append("| Período | Artigos | Fase | Agência Dominante |")
    lines.append("|---------|---------|------|-------------------|")
    for point in phases_data:
        agency_display = point.get("agencyName") or point.get("agencyKey") or "—"
        lines.append(
            f"| {point['period']} | {point['articleCount']} | {point['phase']} | {agency_display} |"
        )

    lines.append("\n## Âncoras Narrativos por Fase\n")
    for phase, agency in sorted(anchors.items()):
        lines.append(f"- **{phase}:** {agency}")

    lines.append("\n## Perspectiva Atual\n")
    lines.append(f"A política **{canonical_name}** está na fase **{current_phase}**.")

    phase_descriptions = {
        "ANNOUNCED": "Fase de lançamento/anúncio — volume máximo de cobertura.",
        "IMPLEMENTATION": "Fase de implementação — cobertura sustentada acima de 40% do pico.",
        "ROUTINE": "Fase de rotina — volume de cobertura abaixo de 40% do pico; política consolidada ou em desaceleração comunicacional.",
    }
    desc = phase_descriptions.get(current_phase, "")
    if desc:
        lines.append(desc)

    if articles:
        lines.append("\n## Artigos Representativos (Fase de Pico)\n")
        for art in articles[:3]:
            title = art.get("title", "Sem título")
            date = (art.get("publishedAt") or "")[:10]
            url = art.get("url", "")
            lines.append(f"- [{title}]({url}) — {date}")

    return "\n".join(lines)
