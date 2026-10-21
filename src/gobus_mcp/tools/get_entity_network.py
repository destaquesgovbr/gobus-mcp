"""Rede de co-menções centrada numa entidade (``relatedEntities``).

Não usa o ``entityNetwork``: ele devolve todos os nós alcançáveis, sem ordem, e corta em
``limit`` as arestas entre **quaisquer** pares por peso, então pares de hubs (Brasil ↔
Brasília) expulsam as arestas do foco. O ``relatedEntities`` traz só as arestas que tocam o
foco, por peso decrescente.

- **depth=1:** vizinhos diretos por peso (artigos em co-menção em todo o acervo, sem
  deduplicar republicações), sem as entidades genéricas da lista curada
  (``include_generic`` as traz de volta; as entidades das agências, ``dgb_{code}``, ficam
  visíveis) e filtrados por ``node_types``; os lugares (LOC) vão para uma linha à parte, com
  teto de 5, salvo quando ``node_types`` pede LOC.
- **depth=2:** além disso, expande em paralelo os 5 vizinhos mais fortes da lista (top 25
  de cada) e mostra, por vizinho, até 5 entidades novas (sem o foco, as genéricas e os
  vizinhos diretos), mais as "pontes": entidades alcançadas por 2+ vizinhos. Um vizinho
  que falha vira nota; os demais seguem.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from gobus_mcp.analytics.generic_entities import generic_ids, split_generic
from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.entity_lookup import display_name, fetch_entity, fetch_related

MAX_LIMIT = 200
MAX_PLACES = 5
FAN_OUT = 5
SECOND_HOP_LIMIT = 25  # medido ao vivo em 21/10/2026: depth=2 ≤ 0,75 s
SECOND_HOP_SHOWN = 5
MAX_HIDDEN_SHOWN = 8
MAX_BRIDGES = 8
PLACE = "LOC"

WEIGHT_NOTE = "pesos = artigos em co-menção em todo o acervo, inclui republicações"


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _error_text(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


def _type(row: dict) -> str:
    return (row.get("type") or "").upper()


def _weight(row: dict) -> int:
    return int(row.get("weight") or 0)


def _parse_types(node_types: str) -> frozenset[str] | None:
    allowed = frozenset(t.strip().upper() for t in (node_types or "").split(",") if t.strip())
    return allowed or None


def _item(row: dict) -> str:
    return f"{display_name(row)} ({_n(_weight(row))}, `{row['canonicalId']}`)"


def _hidden_line(hidden: Sequence[dict]) -> str:
    shown = ", ".join(f"{display_name(r)} ({_n(_weight(r))})" for r in hidden[:MAX_HIDDEN_SHOWN])
    extra = len(hidden) - MAX_HIDDEN_SHOWN
    more = f", +{extra}" if extra > 0 else ""
    return (
        f"Ocultas como genéricas: {shown}{more} — use include_generic=true para incluí-las "
        "(país, dateline, o próprio emissor e boilerplate)."
    )


async def _second_hop(
    client: GobusGraphQLClient,
    seeds: Sequence[dict],
    exclude: frozenset[str],
    allowed: frozenset[str] | None,
    cache: TTLCache | None,
) -> list[str]:
    results = await asyncio.gather(
        *(fetch_related(client, s["canonicalId"], SECOND_HOP_LIMIT, cache=cache) for s in seeds),
        return_exceptions=True,
    )
    lines = [
        f"\n## Segundo grau (via os {len(seeds)} vizinhos mais fortes)",
        f"Até {SECOND_HOP_SHOWN} entidades novas por vizinho, entre os {SECOND_HOP_LIMIT} "
        "vizinhos mais fortes dele (sem o foco, as genéricas e os vizinhos diretos); peso = "
        "artigos em co-menção com o vizinho.\n",
    ]
    notes: list[str] = []
    reached: dict[str, tuple[dict, list[str], int]] = {}  # id → (linha, via, Σ pesos)
    for seed, result in zip(seeds, results, strict=True):
        seed_name = display_name(seed)
        if isinstance(result, BaseException):
            notes.append(f"> Não foi possível expandir **{seed_name}** ({_error_text(result)}).")
            continue
        fresh = [
            r
            for r in result
            if r["canonicalId"] not in exclude and (allowed is None or _type(r) in allowed)
        ]
        for row in fresh:
            first, via, total = reached.get(row["canonicalId"], (row, [], 0))
            reached[row["canonicalId"]] = (first, [*via, seed_name], total + _weight(row))
        items = ", ".join(_item(r) for r in fresh[:SECOND_HOP_SHOWN])
        lines.append(
            f"- via **{seed_name}** ({_n(_weight(seed))}): "
            + (items or f"nada novo entre os {SECOND_HOP_LIMIT} vizinhos mais fortes")
        )

    bridges = sorted(
        (v for v in reached.values() if len(v[1]) >= 2),
        key=lambda v: (-len(v[1]), -v[2], display_name(v[0]).casefold()),
    )
    if bridges:
        shown = ", ".join(
            f"{display_name(row)} (via {', '.join(via)})" for row, via, _ in bridges[:MAX_BRIDGES]
        )
        extra = len(bridges) - MAX_BRIDGES
        lines.append(
            f"\n**Pontes** (alcançadas por 2+ vizinhos): {shown}"
            + (f", +{extra}" if extra > 0 else "")
        )
    if notes:
        lines.append("")
        lines.extend(notes)
    return lines


async def get_entity_network(
    entity_id: str,
    client: GobusGraphQLClient,
    depth: int = 1,
    limit: int = 50,
    max_nodes: int = 20,
    node_types: str = "",
    include_generic: bool = False,
    *,
    cache: TTLCache | None = None,
) -> str:
    """Rede de co-menções centrada em ``entity_id`` (Markdown).

    ``limit`` = vizinhos considerados (máx 200, os de maior peso); ``max_nodes`` = itens da
    lista ranqueada; ``cache`` (do ``Deps``) guarda o nó e cada ``relatedEntities`` por 30 min.
    """
    entity_id = entity_id.strip()
    depth = 2 if depth >= 2 else 1
    limit = max(1, min(limit, MAX_LIMIT))
    max_nodes = max(1, max_nodes)
    allowed = _parse_types(node_types)

    node_r, related_r = await asyncio.gather(
        fetch_entity(client, entity_id, cache=cache),
        fetch_related(client, entity_id, limit, cache=cache),
        return_exceptions=True,
    )
    if isinstance(related_r, BaseException):
        return (
            f"Rede de `{entity_id}` indisponível: falha ao buscar os vizinhos "
            f"({_error_text(related_r)})."
        )
    node = None if isinstance(node_r, BaseException) else node_r
    if not related_r:
        return f"Nenhuma rede encontrada para: `{entity_id}`"
    hide = frozenset() if include_generic else generic_ids()
    typed = [r for r in related_r if allowed is None or _type(r) in allowed]
    visible, hidden = split_generic(typed, hide)
    if allowed is None or PLACE not in allowed:
        ranked_all = [r for r in visible if _type(r) != PLACE]
        places_all = [r for r in visible if _type(r) == PLACE]
    else:
        ranked_all, places_all = visible, []
    ranked = ranked_all[:max_nodes]
    places = places_all[:MAX_PLACES]
    truncated = len(related_r) >= limit

    title = display_name(node) if node else entity_id
    kind = (node or {}).get("type")
    lines = [f"# Rede de entidades: {title}" + (f" ({kind})" if kind else "")]
    total = f"{len(visible)}{'+' if truncated else ''}"
    lines.append(
        f"\n`{entity_id}` · Mostrando {len(ranked) + len(places)} de {total} vizinhos "
        f"diretos ({WEIGHT_NOTE})"
    )
    if allowed is not None:
        lines.append(f"Tipos: {', '.join(sorted(allowed))}")

    notes: list[str] = []
    if isinstance(node_r, BaseException):
        notes.append(f"> Nome da entidade indisponível ({_error_text(node_r)}).")
    if truncated:
        cap = " (o máximo)" if limit == MAX_LIMIT else ""
        hint = "" if limit == MAX_LIMIT else f" Aumente `limit` (máx {MAX_LIMIT})."
        notes.append(
            f"> O limite de {limit} vizinhos{cap} foi atingido: há mais vizinhos, todos com "
            f"peso ≤ {_n(_weight(related_r[-1]))}.{hint}"
        )

    lines.append("\n## Vizinhos diretos")
    for position, row in enumerate(ranked, 1):
        lines.append(
            f"{position}. **{display_name(row)}** ({_type(row) or '?'}) · "
            f"{_n(_weight(row))} artigos em co-menção · `{row['canonicalId']}`"
        )
    if len(ranked_all) > len(ranked):
        lines.append(f"… +{len(ranked_all) - len(ranked)} vizinhos (aumente `max_nodes`)")
    if not ranked and not places:
        lines.append("Nenhum vizinho com os filtros atuais.")
    if places:
        extra = len(places_all) - len(places)
        lines.append(
            "\n**Lugares:** "
            + ", ".join(_item(r) for r in places)
            + (f" … +{extra} lugares" if extra > 0 else "")
        )
    if hidden:
        lines.append("\n" + _hidden_line(hidden))
    if notes:
        lines.append("")
        lines.extend(notes)

    seeds = ranked[:FAN_OUT]
    if depth == 2 and seeds:
        exclude = frozenset(r["canonicalId"] for r in related_r) | hide | {entity_id}
        lines.extend(await _second_hop(client, seeds, exclude, allowed, cache))
    return "\n".join(lines)
