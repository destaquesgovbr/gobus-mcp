"""Consulta compartilhada de entidades: id canônico, nó (``entity``) e vizinhos diretos.

``relatedEntities(id, limit)`` é **centrado na entidade**: as arestas que tocam ``id``,
cortadas em ``limit``; ``weight`` = artigos em co-menção em todo o acervo, sem deduplicar
republicações. A rede e o perfil de entidades usam só ela (o ``entityNetwork`` devolve
todos os nós alcançáveis sem ordem e corta as arestas entre quaisquer pares, então os
pares de hubs expulsam as arestas do foco).

**Ranking por associação** (``fetch_neighbors``, GQL-1): cada vizinho vale
``weight · max(0, log2 lift)``, com ``lift`` = co-menção observada ÷ esperada pela
frequência das duas entidades, e só com ``weight ≥ 3`` (abaixo, 0). O peso bruto premia
quem aparece em tudo (Brasil, Brasília); o lift sozinho premia co-menções raras (o MEC é
só o 65º vizinho do Pé-de-Meia por lift e o 1º por associação, em 21/10/2026). Por isso a
lista de candidatos é a **união** de dois pools: os ``limit`` de maior peso
(``orderBy: WEIGHT, minWeight: 2``) e os ``limit`` de maior lift com ``minWeight: 3``.

Sem lift — API sem o GQL-1 (``schema_compat``: query antiga por 1 h) ou estatísticas do
grafo ainda não calculadas (``lift`` nulo em todas as linhas) —, a ordem é o peso bruto,
com nota.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Literal

from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.formatting import fmt_decimal, fmt_int
from gobus_mcp.schema_compat import COMPAT, RELATED_LIFT, SchemaCompat, is_schema_mismatch

logger = logging.getLogger(__name__)

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

MIN_WEIGHT = 2  # relatedEntities(minWeight:): co-menção única fica de fora
LIFT_MIN_WEIGHT = 3  # w ≥ 3 para pontuar por associação (e piso do pool por lift)

Ranking = Literal["lift", "weight"]

RELATED_ENTITIES_QUERY = """
query RelatedEntities(
  $id: String!, $limit: Int!, $orderBy: RelatedEntityOrder!, $minWeight: Int!
) {
  relatedEntities(id: $id, limit: $limit, orderBy: $orderBy, minWeight: $minWeight) {
    canonicalId
    canonicalName
    type
    wikidataId
    weight
    kind
    articleCount
    lift
  }
}
"""

# Antes do GQL-1: sem orderBy/minWeight/lift (ordem por peso no resolver).
RELATED_ENTITIES_LEGACY_QUERY = """
query RelatedEntitiesLegacy($id: String!, $limit: Int!) {
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

NOTE_NO_API = "a API ainda não expõe o lift"
NOTE_NO_STATS = "sem lift: as estatísticas do grafo ainda não foram calculadas"


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


def weight(row: dict) -> int:
    return int(row.get("weight") or 0)


def association_score(row: dict) -> float | None:
    """``weight · max(0, log2 lift)`` com ``weight ≥ 3`` (abaixo, 0); ``None`` sem lift."""
    lift = row.get("lift")
    if lift is None:
        return None
    if weight(row) < LIFT_MIN_WEIGHT or lift <= 1:
        return 0.0
    return weight(row) * math.log2(lift)


def association_text(row: dict) -> str:
    """``"650 artigos · 4,1× o esperado"``; sem lift, ``"650 artigos em co-menção"``."""
    lift = row.get("lift")
    if lift is None:
        return f"{fmt_int(weight(row))} artigos em co-menção"
    return f"{fmt_int(weight(row))} artigos · {fmt_decimal(lift)}× o esperado"


@dataclass(frozen=True)
class RelatedNeighbors:
    """Vizinhos diretos já ordenados.

    - ``ranking``: ``"lift"`` (associação) ou ``"weight"`` (peso bruto, reserva);
    - ``truncated``: o pool por peso bateu no ``limit`` (há mais vizinhos, todos com
      peso ≤ ``floor_weight``);
    - ``note``: por que a ordem é o peso bruto (``None`` com lift).
    """

    rows: list[dict]
    ranking: Ranking
    truncated: bool
    floor_weight: int | None
    note: str | None = None


def ranking_label(neighbors: RelatedNeighbors) -> str:
    """Texto do cabeçalho com o ranking usado."""
    if neighbors.ranking == "lift":
        return (
            f"associação (artigos em co-menção × log2 do lift, com ≥ {LIFT_MIN_WEIGHT} artigos; "
            "lift = co-menção observada ÷ esperada ao acaso)"
        )
    reason = f" — {neighbors.note}" if neighbors.note else ""
    return f"peso bruto (artigos em co-menção){reason}"


def _clean(entity_id: str, data: dict | None) -> list[dict]:
    return [
        r
        for r in (data or {}).get("relatedEntities") or []
        if r.get("canonicalId") and r["canonicalId"] != entity_id
    ]


def _by_weight(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (-weight(r), display_name(r).casefold(), r["canonicalId"]))


def _rank(
    entity_id: str, limit: int, weight_pool: list[dict], lift_pool: list[dict]
) -> RelatedNeighbors:
    truncated = len(weight_pool) >= limit
    floor = min((weight(r) for r in weight_pool), default=None) if truncated else None
    merged: dict[str, dict] = {}
    for row in [*weight_pool, *lift_pool]:
        merged.setdefault(row["canonicalId"], row)
    rows = list(merged.values())
    if not any(r.get("lift") is not None for r in rows):
        return RelatedNeighbors(_by_weight(rows), "weight", truncated, floor, NOTE_NO_STATS)
    rows.sort(
        key=lambda r: (
            -(association_score(r) or 0.0),
            -weight(r),
            display_name(r).casefold(),
            r["canonicalId"],
        )
    )
    return RelatedNeighbors(rows, "lift", truncated, floor)


async def _ranked_pool(
    client: GobusGraphQLClient, entity_id: str, limit: int, order_by: str, min_weight: int
) -> list[dict]:
    data = await client.execute(
        RELATED_ENTITIES_QUERY,
        {"id": entity_id, "limit": limit, "orderBy": order_by, "minWeight": min_weight},
    )
    return _clean(entity_id, data)


async def _legacy(client: GobusGraphQLClient, entity_id: str, limit: int) -> RelatedNeighbors:
    data = await client.execute(RELATED_ENTITIES_LEGACY_QUERY, {"id": entity_id, "limit": limit})
    rows = _by_weight(_clean(entity_id, data))
    truncated = len(rows) >= limit
    floor = weight(rows[-1]) if truncated and rows else None
    return RelatedNeighbors(rows, "weight", truncated, floor, NOTE_NO_API)


async def fetch_neighbors(
    client: GobusGraphQLClient,
    entity_id: str,
    limit: int,
    *,
    lift_pool: bool = True,
    cache: TTLCache | None = None,
    compat: SchemaCompat | None = None,
) -> RelatedNeighbors:
    """Vizinhos diretos de ``entity_id`` por associação (peso bruto sem lift).

    ``lift_pool=False`` (segundo grau da rede) faz só a consulta por peso, reordenada pela
    associação. A falha só do pool por lift é tolerada (fica o pool por peso); a do pool
    por peso propaga. Com ``cache``, guarda por ``(id, limit, lift_pool)`` durante 30 min
    (falha não é cacheada). A própria entidade e linhas sem id ficam de fora.
    """
    compat = compat or COMPAT

    async def load() -> RelatedNeighbors:
        if compat.available(RELATED_LIFT):
            pools = [_ranked_pool(client, entity_id, limit, "WEIGHT", MIN_WEIGHT)]
            if lift_pool:
                pools.append(_ranked_pool(client, entity_id, limit, "LIFT", LIFT_MIN_WEIGHT))
            results = await asyncio.gather(*pools, return_exceptions=True)
            errors = [r for r in results if isinstance(r, BaseException)]
            if any(is_schema_mismatch(e) for e in errors):
                compat.mark_absent(RELATED_LIFT)
                logger.warning("relatedEntities sem lift na API: peso bruto por 1 h")
            else:
                weight_pool = results[0]
                if isinstance(weight_pool, BaseException):
                    raise weight_pool
                lift_rows = results[1] if len(results) > 1 else []
                if isinstance(lift_rows, BaseException):
                    logger.warning("pool por lift de %s falhou: %s", entity_id, lift_rows)
                    lift_rows = []
                return _rank(entity_id, limit, weight_pool, lift_rows)
        return await _legacy(client, entity_id, limit)

    if cache is None:
        return await load()
    key = ("entity", "neighbors", entity_id, limit, lift_pool)
    return await cache.get_or_load(key, load, RELATED_TTL)
