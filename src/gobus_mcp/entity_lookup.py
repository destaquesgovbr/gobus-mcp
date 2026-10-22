"""Consulta compartilhada de entidades: id canônico, nó (``entity``) e vizinhos diretos.

``relatedEntities(id, limit)`` é **centrado na entidade**: as arestas que tocam ``id``,
ordenadas por ``weight`` (artigos em co-menção em todo o acervo, sem deduplicar
republicações) e cortadas em ``limit``. A rede e o perfil de entidades usam só ela (o
``entityNetwork`` devolve todos os nós alcançáveis sem ordem e corta as arestas entre
quaisquer pares, então os pares de hubs expulsam as arestas do foco).
"""

from __future__ import annotations

import re

from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient

RELATED_TTL = 1_800.0  # 30 min (a rede de co-menção é materializada em lote)

_ID_RE = re.compile(r"^(Q\d+|dgb_\S+)$")

ENTITY_NODE_QUERY = """
query EntityNode($id: String!) {
  entity(id: $id) {
    entityId
    canonicalName
    type
    aliases
    wikidataId
    wikidataUrl
    description
    agencyKey
  }
}
"""

RELATED_ENTITIES_QUERY = """
query RelatedEntities($id: String!, $limit: Int!) {
  relatedEntities(id: $id, limit: $limit) {
    canonicalId
    canonicalName
    type
    wikidataId
    weight
    kind
  }
}
"""


def looks_like_id(value: str) -> bool:
    """``Q123`` (Wikidata) ou ``dgb_…`` (id interno)."""
    return bool(_ID_RE.match(value))


def display_name(row: dict) -> str:
    """Nome canônico da linha; o id quando a API não traz nome."""
    return row.get("canonicalName") or row.get("canonicalId") or row.get("entityId") or ""


async def fetch_entity(
    client: GobusGraphQLClient, entity_id: str, *, cache: TTLCache | None = None
) -> dict | None:
    """Nó canônico de ``entity_id``; ``None`` quando não existe. Com ``cache``, 30 min."""

    async def load() -> dict | None:
        data = await client.execute(ENTITY_NODE_QUERY, {"id": entity_id})
        return (data or {}).get("entity")

    if cache is None:
        return await load()
    return await cache.get_or_load(("entity", "node", entity_id), load, RELATED_TTL)


async def fetch_related(
    client: GobusGraphQLClient,
    entity_id: str,
    limit: int,
    *,
    cache: TTLCache | None = None,
) -> list[dict]:
    """Vizinhos diretos de ``entity_id`` por peso decrescente (empate: nome, depois id).

    A ordenação é defensiva (o resolver já ordena por peso); a própria entidade e linhas
    sem id ficam de fora. Com ``cache``, guarda por ``(id, limit)`` durante 30 min (falha
    não é cacheada)."""

    async def load() -> list[dict]:
        data = await client.execute(RELATED_ENTITIES_QUERY, {"id": entity_id, "limit": limit})
        rows = [
            r
            for r in (data or {}).get("relatedEntities") or []
            if r.get("canonicalId") and r["canonicalId"] != entity_id
        ]
        return sorted(
            rows,
            key=lambda r: (-(r.get("weight") or 0), display_name(r).casefold(), r["canonicalId"]),
        )

    if cache is None:
        return await load()
    return await cache.get_or_load(("entity", "related", entity_id, limit), load, RELATED_TTL)
