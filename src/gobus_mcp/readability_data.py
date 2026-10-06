"""Legibilidade por agência a partir do ``agencyAnalytics``: janela pedida, janela efetiva
e agregação null-aware.

Compartilhado pela tool ``gobus_get_readability_recommendations`` e pelos resources
``gobus://readability-report`` e ``ui://readability-dashboard`` (integration.md §1.7).

**Janela efetiva:** o Flesch pode parar de ser calculado (F0b). Quando a janela pedida
não tem dado até o fim, a análise usa uma janela do mesmo tamanho terminando no último
período (mês) com dado, com a nota "dados até MM/AAAA" — em vez de mostrar 0.0.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import DateRange
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import metric_coverage_status
from gobus_mcp.payloads.common import DataStatus
from gobus_mcp.readability import (
    EffectiveWindow,
    FleschValue,
    ReadabilityCoverage,
    effective_window,
    last_period_with_data,
    period_start,
    readability_coverage,
    weighted_metric,
)

FLESCH_KEY = "avgReadabilityFlesch"
LOOKBACK_DAYS = 365  # histórico consultado para achar o último mês com dado
# O Flesch é calculado por um pipeline único: se parou, parou para todos. Basta sondar o
# histórico com as agências mais ativas (365 dias × 41 agências levava ~2 s; × 5, ~0,9 s).
PROBE_AGENCIES = 5

_WINDOW_QUERY = """
query ReadabilityWindow($agencies: [String!]!, $dateFrom: String!, $dateTo: String!) {
  agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: MONTH) {
    period
    agencyKey
    agencyName
    articleCount
    avgReadabilityFlesch
    avgWordCount
  }
}
"""


@dataclass(frozen=True)
class ReadabilityWindow:
    """Linhas de legibilidade de uma janela pedida e da janela efetivamente analisada.

    - ``rows``: linhas da janela efetiva (vazio se não há dado no histórico);
    - ``requested_rows``: linhas da janela pedida (base de ``coverage`` e ``data_status``);
    - ``coverage.last_period_with_data`` olha o histórico inteiro consultado.
    """

    requested: DateRange
    effective: EffectiveWindow
    rows: list[dict]
    requested_rows: list[dict]
    coverage: ReadabilityCoverage
    data_status: DataStatus


async def _fetch(client: GobusGraphQLClient, agencies: list[str], r: DateRange) -> list[dict]:
    # agencyAnalytics: dateTo inclusivo (dias UTC da API)
    data = await client.execute(
        _WINDOW_QUERY,
        {"agencies": agencies, "dateFrom": r.start.isoformat(), "dateTo": r.end.isoformat()},
    )
    return data.get("agencyAnalytics") or []


def _latest(*periods: str | None) -> str | None:
    found = [p for p in periods if p]
    return max(found, key=period_start) if found else None


async def load_readability_window(
    client: GobusGraphQLClient,
    agencies: list[str],
    requested: DateRange,
    *,
    lookback_days: int = LOOKBACK_DAYS,
) -> ReadabilityWindow:
    """Busca a janela pedida e o histórico (em paralelo); se o dado parou antes do fim
    da janela, busca a janela efetiva (mesmo tamanho, terminando no último mês com dado).

    O histórico só serve para achar o último mês com dado e é sondado com as
    ``PROBE_AGENCIES`` primeiras agências (as mais ativas, na ordem do catálogo).
    """
    lookback = DateRange(requested.end - timedelta(days=lookback_days), requested.end)
    requested_rows, history = await asyncio.gather(
        _fetch(client, agencies, requested),
        _fetch(client, agencies[:PROBE_AGENCIES], lookback),
    )
    last = _latest(
        last_period_with_data(requested_rows, FLESCH_KEY),
        last_period_with_data(history, FLESCH_KEY),
    )
    window = effective_window(requested, last, granularity="MONTH")
    if window.effective is None:
        rows: list[dict] = []
    elif window.shifted:
        rows = await _fetch(client, agencies, window.effective)
    else:
        rows = requested_rows

    coverage = dataclasses.replace(
        readability_coverage(requested_rows, FLESCH_KEY), last_period_with_data=last
    )
    status = metric_coverage_status("readability", requested_rows, FLESCH_KEY)
    return ReadabilityWindow(requested, window, rows, requested_rows, coverage, status)


# ── agregação por agência ───────────────────────────────────────────────────


@dataclass(frozen=True)
class AgencyReadability:
    """Legibilidade agregada de uma agência na janela (médias ponderadas por artigos).

    ``flesch.value`` é a média dos valores limitados a [0, 100]; ``flesch.raw``, a média
    bruta. Sem nenhuma linha com valor, ambos são ``None`` (nunca 0.0).
    """

    code: str
    name: str
    is_republisher: bool
    article_count: int
    articles_with_data: int
    flesch: FleschValue
    avg_word_count: float | None

    @property
    def has_data(self) -> bool:
        return self.flesch.value is not None


def aggregate_agencies(
    rows: Iterable[Mapping],
    *,
    names: Mapping[str, str] | None = None,
    republishers: frozenset[str] = frozenset(),
    codes: Iterable[str] = (),
) -> list[AgencyReadability]:
    """Agrega as linhas por agência, ignorando nulos.

    ``codes`` garante uma entrada (sem dado) para agências pedidas que não vieram nas
    linhas. O nome vem de ``names`` (catálogo); sem ele, fica o código.
    """
    names = names or {}
    by_code: dict[str, list[Mapping]] = {code: [] for code in codes}
    for row in rows:
        key = row.get("agencyKey")
        if key:
            by_code.setdefault(key, []).append(row)

    result = []
    for code, agency_rows in by_code.items():
        clamped = weighted_metric(agency_rows, FLESCH_KEY, clamp=True)
        raw = weighted_metric(agency_rows, FLESCH_KEY)
        word_count = weighted_metric(agency_rows, "avgWordCount")
        flesch = FleschValue(
            raw=raw.value,
            value=clamped.value,
            clamped=clamped.clamped_rows > 0,
        )
        result.append(
            AgencyReadability(
                code=code,
                name=names.get(code) or code,
                is_republisher=code in republishers,
                article_count=clamped.total_articles,
                articles_with_data=clamped.covered_articles,
                flesch=flesch,
                avg_word_count=word_count.value,
            )
        )
    return result


def rank_agencies(
    items: Iterable[AgencyReadability],
) -> tuple[list[AgencyReadability], list[AgencyReadability]]:
    """``(com dado, sem dado)``: com dado em ordem decrescente de Flesch (limitado; o bruto
    desempata), sem dado em ordem decrescente de artigos."""
    items = list(items)
    with_data = sorted(
        (a for a in items if a.has_data),
        key=lambda a: (a.flesch.value, a.flesch.raw),
        reverse=True,
    )
    without = sorted((a for a in items if not a.has_data), key=lambda a: (-a.article_count, a.code))
    return with_data, without


async def load_agency_readability(
    client: GobusGraphQLClient,
    catalog: AgencyCatalog,
    agencies: list[str],
    requested: DateRange,
) -> tuple[ReadabilityWindow, list[AgencyReadability]]:
    """Janela (pedida/efetiva) e a agregação por agência com nomes do catálogo.

    Sem janela efetiva (Flesch nulo em todo o histórico), as contagens de artigos vêm
    da janela pedida e todo Flesch fica ``None``.
    """
    window, all_agencies, republishers = await asyncio.gather(
        load_readability_window(client, agencies, requested),
        catalog.all(),
        catalog.republishers(),
    )
    names = {a.code: a.name for a in all_agencies}
    rows = window.rows if window.effective.effective else window.requested_rows
    items = aggregate_agencies(rows, names=names, republishers=republishers, codes=agencies)
    return window, items
