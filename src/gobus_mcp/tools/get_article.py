from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.analytics.generic_entities import generic_ids
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.formatting import (
    FollowUp,
    agency_label,
    brt_day,
    fmt_int,
    md_link,
    tool_call,
    with_follow_ups,
)
from gobus_mcp.readability import article_flesch, describe_flesch
from gobus_mcp.schema_compat import FLESCH_PTBR, execute_compatible

_ARTICLE_TEMPLATE = """
query GetArticle__SUFFIX__($uniqueId: String!) {
  article(uniqueId: $uniqueId) {
    uniqueId
    title
    content
    summary
    agencyName
    agency
    publishedAt
    url
    tags
    features {
      viewCount
      uniqueSessions
      trendingScore
      wordCount
      readabilityFlesch__PTBR__
      entities {
        text
        type
        count
        canonicalId
      }
    }
  }
}
"""

# Flesch pt-BR (GQL-1); sem ele na API, a antiga responde (schema_compat).
_ARTICLE_QUERY = _ARTICLE_TEMPLATE.replace("__SUFFIX__", "").replace(
    "__PTBR__", "\n      readabilityFleschPtbr"
)
_ARTICLE_LEGACY_QUERY = _ARTICLE_TEMPLATE.replace("__SUFFIX__", "Legacy").replace("__PTBR__", "")


def _follow_ups(unique_id: str, agency: str, entities: list[dict]) -> list[FollowUp]:
    """Nota editorial do artigo, perfil da 1ª entidade com id (fora as genéricas) e o
    resumo do órgão."""
    items: list[FollowUp] = [
        (tool_call("gobus_score_article", unique_id=unique_id), "nota editorial e benchmark")
    ]
    hide = generic_ids()
    entity = next(
        (e for e in entities if e.get("canonicalId") and e["canonicalId"] not in hide), None
    )
    if entity is not None:
        call = tool_call("gobus_get_entity_profile", entity_name=entity["canonicalId"])
        items.append((call, f"perfil de {entity.get('text') or entity['canonicalId']}"))
    if agency:
        items.append((tool_call("gobus_get_agency_summary", agency_key=agency), "resumo do órgão"))
    return items


async def get_article(
    unique_id: str,
    client: GobusGraphQLClient,
    *,
    catalog: AgencyCatalog | None = None,
) -> str:
    """Retorna conteúdo completo de um artigo pelo ID único.

    Args:
        unique_id: ID único do artigo (ex: obtido via search_news)
        catalog: catálogo de agências (nome humano da agência)

    Returns:
        Markdown com artigo completo incluindo features e entidades mencionadas.
        Métricas nulas aparecem como "indisponível" (nunca 0); Flesch pt-BR (o inglês,
        legado, só quando o pt-BR falta) nas faixas de Martins.
    """
    catalog = catalog or AgencyCatalog(client)
    data, _ = await execute_compatible(
        client, FLESCH_PTBR, _ARTICLE_QUERY, _ARTICLE_LEGACY_QUERY, {"uniqueId": unique_id}
    )
    art = data.get("article")
    if not art:
        return f"Artigo não encontrado: `{unique_id}`"

    pub_at = brt_day(art.get("publishedAt"))
    tags = ", ".join(art.get("tags") or [])
    agency_code = art.get("agency") or ""
    agency_name = await catalog.display_name(agency_code, art.get("agencyName"))
    lines = [
        f"# {md_link(art['title'], art.get('url'))}\n",
        f"**{agency_label(agency_code, agency_name)}** · {pub_at}",
    ]
    if tags:
        lines.append(f"Tags: {tags}")

    features = art.get("features") or {}
    if features:
        wc = features.get("wordCount")
        flesch, scale = article_flesch(features)
        vc = features.get("viewCount")
        ts = features.get("trendingScore")
        meta_parts = []
        if wc is not None:
            read_min = max(1, round(wc / 200))
            meta_parts.append(f"⏱ {read_min} min leitura ({wc} palavras)")
        else:
            meta_parts.append("⏱ Tamanho: indisponível")
        scale_txt = f" ({scale.short})" if flesch is not None else ""
        meta_parts.append(f"📖 Legibilidade{scale_txt}: {describe_flesch(flesch)}")
        if vc:
            meta_parts.append(f"👁 {fmt_int(vc)} visualizações")
        if ts and ts > 1.0:
            meta_parts.append(f"🔥 Em alta (score {ts:.1f})")
        if meta_parts:
            lines.append("\n" + " · ".join(meta_parts))

        entities = features.get("entities") or []
        if entities:
            lines.append("\n## Entidades mencionadas")
            by_type: dict[str, list] = {}
            for e in entities:
                by_type.setdefault(e.get("type", "MISC"), []).append(e)
            type_labels = {
                "ORG": "Instituições",
                "PER": "Pessoas",
                "LOC": "Locais",
                "EVENT": "Eventos",
                "POLICY": "Políticas",
                "LAW": "Leis",
            }
            for etype, items in by_type.items():
                label = type_labels.get(etype, etype)
                names = [f"{e['text']} ({e.get('count', 0)}x)" for e in items[:8]]
                lines.append(f"**{label}:** {', '.join(names)}")

    lines.append("\n## Conteúdo")
    lines.append(art.get("content") or art.get("summary") or "")

    entities = (art.get("features") or {}).get("entities") or []
    uid = art.get("uniqueId") or unique_id
    return with_follow_ups("\n".join(lines), _follow_ups(uid, agency_code, entities))
