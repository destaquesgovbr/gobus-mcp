"""Perfil completo de uma entidade: identidade, série mensal inteira, agências, cópias
idênticas e entidades relacionadas.

Entrada: id canônico (``Q…``/``dgb_…``) vai direto ao ``entity(id)``, sem busca fuzzy; nome
passa pelo ``entitySearch(limit: 1)``. Depois, em paralelo e cada parte degradando sozinha:

- ``entityCoverage(MONTH)``: ``dateTo`` = último dia + 1 (``calendario.utc_day_bounds``), porque
  o resolver compara ``published_at <= dateTo::timestamptz`` e a data pura vira 00:00 UTC,
  cortando o último dia. Cabeçalho, série e tabela somam as mesmas linhas
  (``analytics.profile``);
- ``relatedEntities(limit: 40)`` por associação (``entity_lookup.fetch_neighbors``: peso ×
  log2 do lift, com o peso bruto de reserva), sem as entidades genéricas da lista curada
  (pesos de todo o acervo);
- ``EntityDedupCounts``: artigos × textos distintos (o ``dedup`` do Typesense agrupa por
  ``content_hash``), só desde ``ENTITY_CANONICAL_INDEX_SINCE`` (antes, o índice não marca a
  entidade). Conteúdo idêntico é raro (republicação costuma mudar o texto), então a saída
  só ganha uma linha quando há cópia;
- ``catalog_info``: republicadoras (coluna à parte).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from gobus_mcp.agency_catalog import FALLBACK_CATALOG_INFO, AgencyCatalog, catalog_info
from gobus_mcp.analytics.generic_entities import generic_ids, split_generic
from gobus_mcp.analytics.profile import (
    CoverageTotals,
    coverage_table,
    coverage_totals,
    monthly_series,
    top_agencies,
)
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import DateRange, reference_date, utc_day_bounds
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import ENTITY_CANONICAL_INDEX_SINCE
from gobus_mcp.entity_lookup import (
    RelatedNeighbors,
    association_text,
    display_name,
    fetch_entity,
    fetch_neighbors,
    looks_like_id,
    ranking_label,
)
from gobus_mcp.formatting import error_text, fmt_date, fmt_int, md_link, plural

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

_DEDUP_COUNTS_QUERY = """
query EntityDedupCounts($all: ArticleFilter!, $dedup: ArticleFilter!) {
  all: articles(limit: 1, filter: $all) {
    found
  }
  distinct: articles(limit: 1, filter: $dedup) {
    found
  }
}
"""

RELATED_LIMIT = 40
RELATED_SHOWN = 8
SUMMARY_RELATED = 3
TOP_AGENCIES = 5
MAX_HIDDEN_SHOWN = 6


def _parse_day(value: str | None, label: str) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        raise ValueError(f"{label}={value!r}") from None


async def _none() -> None:
    return None


async def _coverage(
    client: GobusGraphQLClient, entity_id: str, start: date | None, end: date | None
) -> list[dict]:
    variables: dict = {"entityId": entity_id, "granularity": "MONTH"}
    if start is not None:
        variables["dateFrom"] = start.isoformat()
    if end is not None:
        variables["dateTo"] = utc_day_bounds(DateRange(start or end, end))[1]  # fim + 1 dia
    data = await client.execute(_ENTITY_COVERAGE_QUERY, variables)
    return (data or {}).get("entityCoverage") or []


def _dedup_window(start: date | None, end: date | None) -> tuple[date, date | None] | None:
    """``(início, fim exclusivo)`` dentro do índice; ``None`` se a janela acaba antes dele."""
    if end is not None and end < ENTITY_CANONICAL_INDEX_SINCE:
        return None
    since = max(start or ENTITY_CANONICAL_INDEX_SINCE, ENTITY_CANONICAL_INDEX_SINCE)
    return since, (end + timedelta(days=1)) if end is not None else None


async def _dedup_counts(
    client: GobusGraphQLClient, entity_id: str, window: tuple[date, date | None]
) -> tuple[int, int]:
    since, until = window
    filt: dict = {
        "entityCanonical": [entity_id],
        "startDate": f"{since.isoformat()}T00:00:00+00:00",
    }
    if until is not None:
        filt["endDate"] = f"{until.isoformat()}T00:00:00+00:00"
    data = await client.execute(
        _DEDUP_COUNTS_QUERY, {"all": filt, "dedup": {**filt, "dedup": True}}
    )
    data = data or {}
    return int((data.get("all") or {}).get("found") or 0), int(
        (data.get("distinct") or {}).get("found") or 0
    )


def _period_text(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{fmt_date(start)} a {fmt_date(end)}"
    if start:
        return f"desde {fmt_date(start)}"
    if end:
        return f"até {fmt_date(end)}"
    return "todo o acervo"


def _totals_line(totals: CoverageTotals) -> str:
    return (
        f"**{plural(totals.own, 'artigo', 'artigos')} de "
        f"{plural(totals.agencies, 'agência', 'agências')} + "
        f"{plural(totals.republished, 'republicação', 'republicações')} · "
        f"{plural(totals.mentions, 'menção', 'menções')}**"
    )


def _copies_line(
    window: tuple[date, date | None], end: date | None, counts: tuple[int, int]
) -> str | None:
    """Uma linha só quando há cópia idêntica (``distinct < all``); senão ``None``."""
    total, distinct = counts
    copies = total - distinct
    if copies <= 0:
        return None
    since, _ = window
    scope = (
        f"de {fmt_date(since)} a {fmt_date(end)}" if end is not None else f"desde {fmt_date(since)}"
    )
    label = "cópia idêntica" if copies == 1 else "cópias idênticas"
    return f"{fmt_int(copies)} {label} entre agências {scope} (índice de busca)."


def _agency_lines(rows: list[dict], republishers: frozenset[str]) -> list[str]:
    agencies = top_agencies(rows, republishers, n=TOP_AGENCIES)
    if not agencies:
        return []
    own_total = coverage_totals(rows, republishers).own
    lines = ["\n## Agências que mais publicaram"]
    for position, agency in enumerate(agencies, 1):
        share = agency.articles / own_total if own_total else 0.0
        lines.append(
            f"{position}. {agency.name} (`{agency.agency_key}`) — "
            f"{plural(agency.articles, 'artigo', 'artigos')} ({share:.0%})"
        )
    return lines


def _related_lines(kept: list[dict], hidden: list[dict], neighbors: RelatedNeighbors) -> list[str]:
    lines = [f"**Ordem:** {ranking_label(neighbors)}"]
    lines += [
        f"- **{display_name(r)}** ({r.get('type') or '?'}) · {association_text(r)} · "
        f"`{r['canonicalId']}`"
        for r in kept[:RELATED_SHOWN]
    ]
    if not kept:
        lines.append("Nenhuma entidade relacionada (fora as genéricas).")
    if hidden:
        shown = ", ".join(
            f"{display_name(r)} ({fmt_int(int(r.get('weight') or 0))})"
            for r in hidden[:MAX_HIDDEN_SHOWN]
        )
        extra = len(hidden) - MAX_HIDDEN_SHOWN
        lines.append(
            f"\nOcultas como genéricas: {shown}{f', +{extra}' if extra > 0 else ''} "
            "(veja com gobus_get_entity_network e include_generic=true)."
        )
    return lines


async def get_entity_profile(
    entity_name: str,
    client: GobusGraphQLClient,
    entity_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    summary_only: bool = False,
    *,
    catalog: AgencyCatalog | None = None,
    cache: TTLCache | None = None,
    today: date | None = None,
) -> str:
    """Perfil de uma entidade (Markdown). ``date_to`` é inclusivo; ``today`` = D em BRT
    (injetável), que marca o mês corrente como parcial."""
    query = entity_name.strip()
    try:
        start = _parse_day(date_from, "date_from")
        end = _parse_day(date_to, "date_to")
    except ValueError as exc:
        return f"Data inválida: {exc}. Use o formato AAAA-MM-DD."
    if start and end and start > end:
        return f"Data inválida: date_from ({fmt_date(start)}) depois de date_to ({fmt_date(end)})."
    today = today or reference_date()
    catalog = catalog or AgencyCatalog(client)

    by_id = looks_like_id(query)
    entity: dict | None = None
    if by_id:
        entity_id = query
    else:
        search_vars: dict = {"query": query}
        if entity_type:
            search_vars["entityType"] = entity_type.upper()
        try:
            search = await client.execute(_ENTITY_SEARCH_QUERY, search_vars)
        except Exception as exc:
            return f"Busca da entidade **{query}** indisponível ({error_text(exc)})."
        hits = (search or {}).get("entitySearch") or []
        if not hits:
            return f"Entidade não encontrada: **{query}**"
        entity = hits[0]
        entity_id = entity["entityId"]

    window = _dedup_window(start, end)
    node_r, coverage_r, related_r, dedup_r, info = await asyncio.gather(
        fetch_entity(client, entity_id, cache=cache) if by_id else _none(),
        _coverage(client, entity_id, start, end),
        fetch_neighbors(client, entity_id, RELATED_LIMIT, cache=cache),
        _dedup_counts(client, entity_id, window) if window and not summary_only else _none(),
        catalog_info(catalog),
        return_exceptions=True,
    )
    if isinstance(info, BaseException):  # defensivo: catalog_info não levanta
        info = FALLBACK_CATALOG_INFO

    notes: list[str] = []
    if by_id:
        if node_r is None:
            return f"Entidade não encontrada: `{entity_id}`"
        if isinstance(node_r, BaseException):
            notes.append(f"> Nome da entidade indisponível ({error_text(node_r)}).")
        else:
            entity = node_r
    if info.fallback:
        notes.append("> Catálogo indisponível: republicadoras por lista fixa.")

    entity = entity or {}
    name = entity.get("canonicalName") or entity_id
    kind = entity.get("type")
    wikidata = md_link("Wikidata", entity["wikidataUrl"]) if entity.get("wikidataUrl") else "—"
    lines = [f"# {name} ({kind})" if kind else f"# {name}", f"**ID:** `{entity_id}` · {wikidata}"]
    if entity.get("aliases"):
        lines.append(f"**Aliases:** {', '.join(entity['aliases'])}")
    if entity.get("description") and not summary_only:
        lines.append(f"\n{entity['description']}")
    lines.append(f"\n**Período:** {_period_text(start, end)}")

    rows: list[dict] = []
    if isinstance(coverage_r, BaseException):
        lines.append(f"> Cobertura indisponível ({error_text(coverage_r)}).")
    else:
        totals = coverage_totals(coverage_r, info.republishers)
        if totals.total:
            rows = coverage_r
            lines.append(_totals_line(totals))
            if window is not None and isinstance(dedup_r, tuple):  # só roda dentro do índice
                copies = _copies_line(window, end, dedup_r)
                if copies:
                    lines.append(copies)
        else:
            lines.append("Nenhum artigo no período (entityCoverage).")

    kept: list[dict] = []
    hidden: list[dict] = []
    if isinstance(related_r, BaseException):
        related_note = f"> Entidades relacionadas indisponíveis ({error_text(related_r)})."
    else:
        related_note = None
        kept, hidden = split_generic(related_r.rows, generic_ids())

    if summary_only:
        if related_note:
            notes.append(related_note)
        elif kept:
            top = ", ".join(
                f"{display_name(r)} ({r.get('type') or '?'})" for r in kept[:SUMMARY_RELATED]
            )
            lines.append(f"**Top relacionadas:** {top}")
        return "\n".join(lines + ([""] + notes if notes else []))

    if rows:
        series_end = min(end, today) if end is not None else today
        series = monthly_series(rows, start, series_end, info.republishers, today=today)
        lines.append("\n## Cobertura mensal")
        lines.append("| Mês | Artigos | Republicações |")
        lines.append("|-----|---------|---------------|")
        for row in coverage_table(series):
            lines.append(f"| {row.label} | {fmt_int(row.own)} | {fmt_int(row.republished)} |")
        lines.extend(_agency_lines(rows, info.republishers))

    if isinstance(dedup_r, BaseException):
        notes.append(f"> Contagem de cópias idênticas indisponível ({error_text(dedup_r)}).")

    lines.append("\n## Entidades relacionadas (co-menção, todo o acervo)")
    lines.extend([related_note] if related_note else _related_lines(kept, hidden, related_r))
    return "\n".join(lines + ([""] + notes if notes else []))
