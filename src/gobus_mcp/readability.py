"""Legibilidade (Flesch): escala, faixas, médias null-aware e janela efetiva.

Módulo único para tools, resources e apps (integration.md §1.7). O JS dos apps não
codifica limiares: as faixas saem daqui no payload.

**Escala:** o pipeline calcula o Flesch com ``textstat`` sem idioma, ou seja, a fórmula
**inglesa** (F0g). Os valores vão de negativos a >100 em texto em português; aqui o valor
exibido é sempre limitado a [0, 100] e o bruto aparece quando houve clamp. Uma futura
chave ``readability_flesch_ptbr`` (Martins/1996) trocaria ``FLESCH_SCALE_ID``.

**Nulo nunca é zero:** sem dado, as funções devolvem ``None`` e o texto "indisponível".
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal

from gobus_mcp.calendario import DateRange

FLESCH_SCALE_ID: Final = "flesch_en_textstat"
FLESCH_MIN: Final = 0.0
FLESCH_MAX: Final = 100.0
TARGET_SERVICE: Final = 50.0  # meta para textos de serviço ao cidadão
TARGET_INSTITUTIONAL: Final = 30.0  # meta para textos institucionais

Granularity = Literal["DAY", "WEEK", "MONTH"]


@dataclass(frozen=True)
class FleschBand:
    """Faixa de Flesch: ``[lower, upper)`` (a última inclui 100)."""

    key: str
    label: str
    lower: float
    upper: float


FLESCH_BANDS: tuple[FleschBand, ...] = (
    FleschBand("very_hard", "muito difícil", 0.0, 25.0),
    FleschBand("hard", "difícil", 25.0, 50.0),
    FleschBand("medium", "médio", 50.0, 75.0),
    FleschBand("easy", "fácil", 75.0, 100.0),
)


@dataclass(frozen=True)
class FleschValue:
    """Flesch bruto (``raw``) e exibido (``value``, em [0, 100])."""

    raw: float | None
    value: float | None
    clamped: bool


def clamp_flesch(raw: float | None) -> FleschValue:
    """Limita o Flesch a [0, 100], guardando o bruto."""
    if raw is None:
        return FleschValue(None, None, False)
    value = min(max(float(raw), FLESCH_MIN), FLESCH_MAX)
    return FleschValue(raw, value, value != raw)


def _value(v: float | FleschValue | None) -> FleschValue:
    return v if isinstance(v, FleschValue) else clamp_flesch(v)


def flesch_band(v: float | FleschValue | None) -> FleschBand | None:
    """Faixa do valor (já limitado a [0, 100]); ``None`` sem dado."""
    value = _value(v).value
    if value is None:
        return None
    for band in FLESCH_BANDS:
        if value < band.upper:
            return band
    return FLESCH_BANDS[-1]


def describe_flesch(v: float | FleschValue | None) -> str:
    """``"33.5 (difícil)"``; com clamp, ``"0.0 (muito difícil; valor bruto -22.9)"``."""
    fv = _value(v)
    band = flesch_band(fv)
    if fv.value is None or band is None:
        return "indisponível"
    text = f"{fv.value:.1f} ({band.label}"
    if fv.clamped:
        text += f"; valor bruto {fv.raw:.1f}"
    return text + ")"


def readability_score(v: float | FleschValue | None) -> float | None:
    """Nota 0–10 de legibilidade: linear até a meta de serviço (Flesch 50 = 10)."""
    value = _value(v).value
    if value is None:
        return None
    return round(10.0 * min(value, TARGET_SERVICE) / TARGET_SERVICE, 1)


# ── médias ponderadas (agencyAnalytics) ─────────────────────────────────────


@dataclass(frozen=True)
class Coverage:
    """Média ponderada por artigos e quanto dela tem dado."""

    value: float | None
    covered_articles: int
    total_articles: int
    covered_rows: int
    total_rows: int
    clamped_rows: int = 0

    @property
    def ratio(self) -> float | None:
        """Fração de artigos em linhas com valor (``None`` sem artigos)."""
        return self.covered_articles / self.total_articles if self.total_articles else None


def weighted_metric(
    rows: Iterable[Mapping],
    key: str,
    *,
    weight_key: str = "articleCount",
    clamp: bool = False,
) -> Coverage:
    """Média de ``key`` ponderada por ``weight_key``, **ignorando nulos**.

    Sem nenhuma linha com valor, ``value`` é ``None`` (nunca 0.0). Com ``clamp=True``,
    cada valor é limitado à escala de Flesch antes da média.
    """
    total_articles = covered_articles = total_rows = covered_rows = clamped_rows = 0
    weighted_sum = 0.0
    for row in rows:
        total_rows += 1
        weight = row.get(weight_key) or 0
        total_articles += weight
        raw = row.get(key)
        if raw is None or weight <= 0:
            continue
        value = raw
        if clamp:
            fv = clamp_flesch(raw)
            value = fv.value
            clamped_rows += fv.clamped
        weighted_sum += value * weight
        covered_articles += weight
        covered_rows += 1
    value = weighted_sum / covered_articles if covered_articles else None
    return Coverage(value, covered_articles, total_articles, covered_rows, total_rows, clamped_rows)


# ── períodos e janela efetiva ───────────────────────────────────────────────


def period_start(period: str) -> date:
    """Início do período do ``agencyAnalytics`` (``'2026-05-01 00:00:00+00'``,
    ``'2026-10-04'`` ou ``'2026-05'``)."""
    text = period.strip()
    if len(text) == 7:  # "AAAA-MM"
        text += "-01"
    return date.fromisoformat(text[:10])


def period_range(period: str, granularity: Granularity) -> DateRange:
    """Dias (inclusivos) cobertos por um período da API."""
    start = period_start(period)
    if granularity == "DAY":
        return DateRange(start, start)
    if granularity == "WEEK":
        return DateRange(start, start + timedelta(days=6))
    last_day = calendar.monthrange(start.year, start.month)[1]
    return DateRange(start, start.replace(day=last_day))


def _has_value(row: Mapping, key: str, weight_key: str) -> bool:
    return row.get(key) is not None and (row.get(weight_key) or 0) > 0


def last_period_with_data(
    rows: Iterable[Mapping], key: str, *, weight_key: str = "articleCount"
) -> str | None:
    """Período mais recente com valor não nulo (e artigos) — ``None`` se nenhum."""
    periods = [r["period"] for r in rows if _has_value(r, key, weight_key)]
    return max(periods, key=period_start) if periods else None


@dataclass(frozen=True)
class ReadabilityCoverage:
    """Cobertura de legibilidade por período (campos do payload, integration.md §1.1)."""

    periods_total: int
    periods_with_data: int
    articles_total: int
    articles_in_periods_with_data: int
    last_period_with_data: str | None


def readability_coverage(
    rows: Iterable[Mapping],
    key: str = "avgReadabilityFlesch",
    *,
    weight_key: str = "articleCount",
) -> ReadabilityCoverage:
    """Quantos períodos (e artigos neles) têm Flesch — um período conta se qualquer
    agência tiver valor nele."""
    rows = list(rows)
    periods = {r["period"] for r in rows}
    with_data = {r["period"] for r in rows if _has_value(r, key, weight_key)}
    return ReadabilityCoverage(
        periods_total=len(periods),
        periods_with_data=len(with_data),
        articles_total=sum(r.get(weight_key) or 0 for r in rows),
        articles_in_periods_with_data=sum(
            r.get(weight_key) or 0 for r in rows if r["period"] in with_data
        ),
        last_period_with_data=last_period_with_data(rows, key, weight_key=weight_key),
    )


@dataclass(frozen=True)
class EffectiveWindow:
    """Janela pedida e a efetivamente analisada.

    Se o dado parou antes do fim da janela pedida, a efetiva tem o mesmo tamanho e
    termina no último período com dado (``shifted``), com a nota "dados até MM/AAAA".
    """

    requested: DateRange
    effective: DateRange | None
    shifted: bool
    last_period_with_data: str | None
    note: str | None


def effective_window(
    requested: DateRange,
    last_period: str | None,
    *,
    granularity: Granularity = "MONTH",
) -> EffectiveWindow:
    """Janela efetiva a partir do último período com dado (ver ``last_period_with_data``)."""
    if last_period is None:
        return EffectiveWindow(
            requested, None, False, None, "sem dados de legibilidade no histórico consultado"
        )
    last_end = period_range(last_period, granularity).end
    if last_end >= requested.end:
        return EffectiveWindow(requested, requested, False, last_period, None)
    effective = DateRange(last_end - timedelta(days=requested.days - 1), last_end)
    shown = last_end.strftime("%m/%Y" if granularity == "MONTH" else "%d/%m/%Y")
    return EffectiveWindow(requested, effective, True, last_period, f"dados até {shown}")
