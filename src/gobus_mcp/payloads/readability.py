"""Payload de ``gobus_get_readability_recommendations`` (app ``ui://readability-dashboard``, G3).

O Markdown da tool é ``render_readability_markdown(report)`` e vai em ``summary``. As faixas
de Flesch vão no payload: o JS do app não codifica limiares.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from gobus_mcp.calendario import DateRange
from gobus_mcp.payloads.common import Payload, ReportBase
from gobus_mcp.readability import (
    FLESCH_BANDS,
    FLESCH_SCALE_ID,
    TARGET_INSTITUTIONAL,
    TARGET_SERVICE,
    FleschBand,
)


class DayRange(Payload):
    """Intervalo de dias (início e fim inclusivos)."""

    start: date
    end: date
    days: int

    @classmethod
    def of(cls, r: DateRange) -> DayRange:
        return cls(start=r.start, end=r.end, days=r.days)


class FleschBandInfo(Payload):
    """Faixa de Flesch ``[lower, upper)`` com chave estável e rótulo PT."""

    key: str
    label: str
    lower: float
    upper: float

    @classmethod
    def of(cls, band: FleschBand) -> FleschBandInfo:
        return cls(key=band.key, label=band.label, lower=band.lower, upper=band.upper)


def flesch_bands() -> list[FleschBandInfo]:
    return [FleschBandInfo.of(b) for b in FLESCH_BANDS]


class ReadabilityCoverageInfo(Payload):
    """Quanto da janela pedida tem Flesch (integration.md §1.1)."""

    periods_total: int
    periods_with_data: int
    articles_total: int
    articles_in_periods_with_data: int
    last_period_with_data: str | None


class AgencyReadabilityRow(Payload):
    """Legibilidade de uma agência na janela efetiva. Sem dado: ``flesch`` é null."""

    agency_key: str
    agency_name: str
    is_republisher: bool
    article_count: int
    articles_with_data: int
    flesch: float | None  # média dos valores limitados a [0, 100]
    flesch_raw: float | None  # média bruta (escala inglesa, pode ser negativa)
    band: str | None
    band_label: str | None
    gap_to_target: float | None  # flesch − meta de serviço (50)
    avg_word_count: float | None


class ArticleReadability(Payload):
    """Artigo da amostra (pior ou melhor Flesch da janela)."""

    unique_id: str
    title: str
    url: str | None
    published_at: str | None
    flesch: float | None
    flesch_raw: float | None
    band: str | None
    band_label: str | None
    word_count: int | None


class ReadabilityReport(ReportBase):
    """Ranking (``mode="ranking"``) ou diagnóstico de uma agência (``mode="agency"``)."""

    kind: Literal["gobus.readability"] = "gobus.readability"
    tool: Literal["gobus_get_readability_recommendations"] = "gobus_get_readability_recommendations"
    mode: Literal["ranking", "agency"]
    error: str | None = None  # parâmetro inválido (agência fora do catálogo, data)
    scale: str = FLESCH_SCALE_ID
    bands: list[FleschBandInfo]
    target_service: float = TARGET_SERVICE
    target_institutional: float = TARGET_INSTITUTIONAL
    requested_window: DayRange | None
    effective_window: DayRange | None
    window_shifted: bool = False
    window_note: str | None = None
    coverage: ReadabilityCoverageInfo | None
    agencies: list[AgencyReadabilityRow] = []  # com dado, em ordem de Flesch
    agencies_without_data: list[AgencyReadabilityRow] = []
    benchmark: AgencyReadabilityRow | None = None  # Agência Brasil na mesma janela
    agency: AgencyReadabilityRow | None = None  # modo agência
    sample_size: int | None = None  # artigos da amostra com Flesch (modo agência)
    sample_found: int | None = None  # artigos na janela segundo a busca
    worst_article: ArticleReadability | None = None
    best_article: ArticleReadability | None = None
    recommendations: list[str] = []
