"""Perfil de entidade: série mensal, totais e agências a partir do ``entityCoverage(MONTH)``.

O ``entityCoverage`` devolve uma linha por **mês × agência** (``period`` = início do mês em
UTC, ex. ``'2026-07-01 00:00:00+00'``). Cada artigo tem uma agência, então somar as linhas
dá os artigos distintos do mês. As republicadoras (``AgencyCatalog.republishers()``) ficam
numa coluna à parte. Funções puras: o cabeçalho, a série e a tabela somam as mesmas linhas
(as de ``period`` ilegível ficam fora de tudo).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from gobus_mcp.readability import period_start

MAX_TABLE_MONTHS = 24

_MONTH_ABBR = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


@dataclass(frozen=True)
class MonthCoverage:
    """Um mês da série: ``own`` = agências não republicadoras."""

    month: date  # primeiro dia do mês
    own: int = 0
    republished: int = 0
    partial: bool = False  # mês cortado pela janela ou ainda em curso

    @property
    def total(self) -> int:
        return self.own + self.republished

    @property
    def label(self) -> str:
        return self.month.strftime("%Y-%m")

    @property
    def table_label(self) -> str:
        return f"{self.label} (parcial)" if self.partial else self.label


@dataclass(frozen=True)
class CoverageTotals:
    own: int
    republished: int
    agencies: int  # agências não republicadoras com artigo
    mentions: int

    @property
    def total(self) -> int:
        return self.own + self.republished


@dataclass(frozen=True)
class AgencyShare:
    agency_key: str
    name: str
    articles: int


@dataclass(frozen=True)
class CoverageRow:
    """Linha da tabela: um mês ou um ano agregado."""

    label: str
    own: int
    republished: int


@dataclass(frozen=True)
class _Point:
    month: date
    agency: str
    articles: int
    mentions: int


def _points(rows: Iterable[Mapping]) -> Iterator[_Point]:
    for row in rows:
        try:
            month = period_start(str(row.get("period") or "")).replace(day=1)
        except ValueError:
            continue
        yield _Point(
            month,
            row.get("agencyKey") or "",
            int(row.get("articleCount") or 0),
            int(row.get("totalMentions") or 0),
        )


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _month_end(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def monthly_series(
    rows: Iterable[Mapping],
    start: date,
    end: date,
    republishers: frozenset[str],
    *,
    today: date | None = None,
) -> list[MonthCoverage]:
    """Um ponto por mês de ``start`` a ``end`` (inclusivos), com zero nos meses sem artigo.

    Linha fora da janela estende a série (o total nunca perde artigo). Mês é parcial quando
    a janela não o cobre inteiro ou quando contém ``today`` (ainda em curso)."""
    own: dict[date, int] = {}
    republished: dict[date, int] = {}
    for point in _points(rows):
        bucket = republished if point.agency in republishers else own
        bucket[point.month] = bucket.get(point.month, 0) + point.articles
    months = set(own) | set(republished)
    first = min([start.replace(day=1), *months])
    last = max([end.replace(day=1), *months])

    series = []
    month = first
    while month <= last:
        partial = month < start or _month_end(month) > end
        if today is not None and month <= today <= _month_end(month):
            partial = True
        series.append(MonthCoverage(month, own.get(month, 0), republished.get(month, 0), partial))
        month = _next_month(month)
    return series


def coverage_totals(rows: Iterable[Mapping], republishers: frozenset[str]) -> CoverageTotals:
    """Totais do cabeçalho (mesmas linhas da série)."""
    own = republished = mentions = 0
    agencies: set[str] = set()
    for point in _points(rows):
        mentions += point.mentions
        if point.agency in republishers:
            republished += point.articles
        else:
            own += point.articles
            if point.agency and point.articles:
                agencies.add(point.agency)
    return CoverageTotals(own, republished, len(agencies), mentions)


def top_agencies(
    rows: Iterable[Mapping], republishers: frozenset[str], n: int = 5
) -> list[AgencyShare]:
    """Agências não republicadoras com mais artigos (empate: código). Nome = ``agencyName``
    da linha, ou o código."""
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for row in rows:
        agency = row.get("agencyKey")
        if not agency or agency in republishers:
            continue
        counts[agency] = counts.get(agency, 0) + int(row.get("articleCount") or 0)
        if row.get("agencyName"):
            names[agency] = row["agencyName"]
    ranked = sorted((a for a in counts if counts[a] > 0), key=lambda a: (-counts[a], a))
    return [AgencyShare(a, names.get(a, a), counts[a]) for a in ranked[:n]]


def _year_label(months: Sequence[MonthCoverage]) -> str:
    year = months[0].month.year
    first, last = months[0].month.month, months[-1].month.month
    if first == 1 and last == 12 and not any(m.partial for m in months):
        return str(year)
    return f"{year} ({_MONTH_ABBR[first - 1]}–{_MONTH_ABBR[last - 1]})"


def coverage_table(
    series: Sequence[MonthCoverage], max_months: int = MAX_TABLE_MONTHS
) -> list[CoverageRow]:
    """Os últimos ``max_months`` meses um a um; os anteriores somados por ano."""
    older, recent = series[: max(len(series) - max_months, 0)], series[-max_months:]
    table: list[CoverageRow] = []
    by_year: dict[int, list[MonthCoverage]] = {}
    for point in older:
        by_year.setdefault(point.month.year, []).append(point)
    for months in by_year.values():
        table.append(
            CoverageRow(
                _year_label(months),
                sum(m.own for m in months),
                sum(m.republished for m in months),
            )
        )
    table.extend(CoverageRow(p.table_label, p.own, p.republished) for p in recent)
    return table
