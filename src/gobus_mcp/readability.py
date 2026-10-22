"""Legibilidade (Flesch): escalas, faixas, médias null-aware e janela efetiva.

Módulo único para tools, resources e apps (integration.md §1.7). O JS dos apps não
codifica limiares: as faixas saem daqui no payload.

**Escala:** o Flesch adaptado ao português (Martins et al., 1996; chave
``readability_flesch_ptbr`` do feature-worker, exposta pelo GQL-1 como
``readabilityFleschPtbr``/``avgReadabilityFleschPtbr`` + ``readabilityFleschPtbrCount``).
Faixas de Martins: 75–100 muito fácil, 50–75 fácil, 25–50 difícil, 0–25 muito difícil; a
meta de serviço continua 50. Notícia de governo fica tipicamente em "muito difícil"
(mediana ≈ 15).

**Reserva:** sem o pt-BR (API sem o campo ou valor nulo), vale o Flesch antigo, a fórmula
**inglesa** do ``textstat`` (``EN_SCALE``), com aviso (``READABILITY_LEGACY_SCALE``). As
duas escalas nunca se misturam numa média: ``choose_scale`` escolhe uma por resposta.
Os valores vão de negativos a >100; o exibido é sempre limitado a [0, 100] e o bruto
aparece quando houve clamp.

**Nulo nunca é zero:** sem dado, as funções devolvem ``None`` e o texto "indisponível".
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal

from gobus_mcp.calendario import DateRange
from gobus_mcp.data_status import metric_coverage_status
from gobus_mcp.payloads.common import DataStatus, Notice

FLESCH_SCALE_PTBR: Final = "flesch_ptbr_martins1996"
FLESCH_SCALE_EN: Final = "flesch_en_textstat"
FLESCH_SCALE_ID: Final = FLESCH_SCALE_PTBR  # escala padrão
FLESCH_MIN: Final = 0.0
FLESCH_MAX: Final = 100.0
TARGET_SERVICE: Final = 50.0  # meta para textos de serviço ao cidadão
TARGET_INSTITUTIONAL: Final = 30.0  # meta para textos institucionais
PTBR_MIN_SHARE: Final = 0.1  # abaixo disso o pt-BR está "morto" e o inglês, se houver, vale

Granularity = Literal["DAY", "WEEK", "MONTH"]


@dataclass(frozen=True)
class FleschScale:
    """Uma escala de Flesch e os campos dela na graphql-api.

    ``count_field``: nº de artigos com valor no grupo (base da média); sem ele, a média é
    ponderada pelo ``articleCount`` das linhas com valor.
    """

    id: str
    label: str  # texto completo (rodapé, legenda do painel)
    short: str  # texto curto ("Flesch pt-BR")
    article_field: str  # ArticleFeatures
    avg_field: str  # AgencyPeriodMetrics
    count_field: str | None
    legacy: bool


PTBR_SCALE: Final = FleschScale(
    id=FLESCH_SCALE_PTBR,
    label="Flesch pt-BR (Martins et al., 1996), limitado a 0–100",
    short="Flesch pt-BR",
    article_field="readabilityFleschPtbr",
    avg_field="avgReadabilityFleschPtbr",
    count_field="readabilityFleschPtbrCount",
    legacy=False,
)
EN_SCALE: Final = FleschScale(
    id=FLESCH_SCALE_EN,
    label="Flesch pela fórmula inglesa do textstat (legado), limitado a 0–100",
    short="Flesch inglês, legado",
    article_field="readabilityFlesch",
    avg_field="avgReadabilityFlesch",
    count_field=None,
    legacy=True,
)

LEGACY_SCALE_MESSAGE: Final = (
    "Flesch pt-BR indisponível: valores pela fórmula inglesa do textstat (legado, escala "
    "distorcida para o português); as faixas e a meta são as mesmas."
)


def legacy_scale_notice(scale: FleschScale, affects: list[str] | None = None) -> Notice | None:
    """Aviso de reserva (``READABILITY_LEGACY_SCALE``) quando a escala é a inglesa."""
    if not scale.legacy:
        return None
    return Notice(
        code="READABILITY_LEGACY_SCALE",
        severity="warn",
        message=LEGACY_SCALE_MESSAGE,
        affects=affects or ["readability"],
    )


def article_flesch(features: Mapping | None) -> tuple[float | None, FleschScale]:
    """Flesch de um artigo: o pt-BR; sem ele, o inglês (legado); sem nenhum, ``None``."""
    features = features or {}
    for scale in (PTBR_SCALE, EN_SCALE):
        value = features.get(scale.article_field)
        if value is not None:
            return value, scale
    return None, PTBR_SCALE


@dataclass(frozen=True)
class FleschBand:
    """Faixa de Flesch: ``[lower, upper)`` (a última inclui 100)."""

    key: str
    label: str
    lower: float
    upper: float


# Faixas de Martins et al. (1996) para o Flesch em português.
FLESCH_BANDS: tuple[FleschBand, ...] = (
    FleschBand("very_hard", "muito difícil", 0.0, 25.0),
    FleschBand("hard", "difícil", 25.0, 50.0),
    FleschBand("easy", "fácil", 50.0, 75.0),
    FleschBand("very_easy", "muito fácil", 75.0, 100.0),
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
    count_key: str | None = None,
    clamp: bool = False,
) -> Coverage:
    """Média de ``key`` ponderada por ``weight_key``, **ignorando nulos**.

    Com ``count_key`` (ex.: ``readabilityFleschPtbrCount``), o peso de uma linha com valor
    é o nº de artigos que têm o valor (quando a API o traz), e a cobertura conta esses
    artigos; o total continua sendo ``weight_key``. Sem nenhuma linha com valor, ``value``
    é ``None`` (nunca 0.0). Com ``clamp=True``, cada valor é limitado à escala de Flesch
    antes da média.
    """
    total_articles = covered_articles = total_rows = covered_rows = clamped_rows = 0
    weighted_sum = 0.0
    for row in rows:
        total_rows += 1
        weight = row.get(weight_key) or 0
        total_articles += weight
        raw = row.get(key)
        if count_key is not None and row.get(count_key) is not None:
            weight = min(row[count_key], weight) if weight else row[count_key]
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


def scale_metric(rows: Iterable[Mapping], scale: FleschScale, *, clamp: bool = False) -> Coverage:
    """``weighted_metric`` do campo médio de ``scale`` (com a contagem, se houver)."""
    return weighted_metric(rows, scale.avg_field, count_key=scale.count_field, clamp=clamp)


def readability_status(rows: Iterable[Mapping], scale: FleschScale) -> DataStatus:
    """``DataStatus`` de ``readability`` na escala dada (o detalhe diz qual). A data
    "desde 30/06" (parada do Flesch inglês) só vale para a escala inglesa."""
    return metric_coverage_status(
        "readability",
        rows,
        scale.avg_field,
        count_key=scale.count_field,
        label=scale.short,
        hint=scale.legacy,
    )


def choose_scale(rows: Iterable[Mapping]) -> FleschScale:
    """Escala de uma resposta do ``agencyAnalytics`` (as duas nunca se misturam).

    O pt-BR quando cobre ao menos ``PTBR_MIN_SHARE`` dos artigos ou quando o inglês não
    tem dado; senão, o inglês (reserva, com aviso). Sem dado nenhum, o pt-BR (o texto diz
    "indisponível").
    """
    rows = list(rows)
    ptbr = scale_metric(rows, PTBR_SCALE)
    english = scale_metric(rows, EN_SCALE)
    if ptbr.covered_articles and (ptbr.ratio or 0.0) >= PTBR_MIN_SHARE:
        return PTBR_SCALE
    if english.covered_articles:
        return EN_SCALE
    return PTBR_SCALE


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
