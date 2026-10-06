"""Payload de ``gobus_score_article`` (app ``ui://article-scorecard``, G3).

``score_status``: ``scored`` (3 dimensões), ``partial`` (Flesch + wordCount, sem benchmark
de concisão; nota renormalizada) ou ``refused`` (sem Flesch ou sem wordCount: nunca uma
nota inventada). O ``status`` do relatório segue o vocabulário comum (ok/partial/unavailable).
"""

from __future__ import annotations

from typing import Literal

from gobus_mcp.payloads.common import Payload, ReportBase
from gobus_mcp.payloads.readability import DayRange, FleschBandInfo
from gobus_mcp.readability import FLESCH_SCALE_ID

ScoreStatus = Literal["scored", "partial", "refused"]
DimensionKey = Literal["readability", "conciseness", "entity_density"]


class ScoreDimension(Payload):
    """Uma dimensão da nota. ``score`` null = dimensão indisponível (fora da média)."""

    key: DimensionKey
    label: str
    weight: float  # peso nominal (0,5 / 0,3 / 0,2)
    effective_weight: float | None  # peso renormalizado entre as dimensões disponíveis
    score: float | None  # 0–10
    value: float | None  # Flesch limitado · palavras · entidades por 100 palavras
    reference: float | None  # mediana do benchmark da agência (concisão)
    detail: str


class ScoreBenchmark(Payload):
    """Amostra de artigos de uma agência nos 90 dias antes da publicação do artigo.

    Medianas calculadas no cliente; null com menos de ``MIN_SAMPLE`` artigos com o campo.
    ``window`` = primeiro e último dia (reais) da amostra.
    """

    agency_key: str
    agency_name: str
    found: int | None
    sample_size: int  # artigos com wordCount
    flesch_sample_size: int  # artigos com Flesch
    median_word_count: float | None
    median_flesch: float | None  # mediana dos valores limitados a [0, 100]
    window: DayRange | None


class ScoredArticle(Payload):
    unique_id: str
    title: str
    url: str | None
    agency_key: str
    agency_name: str
    published_at: str | None
    flesch: float | None  # limitado a [0, 100]
    flesch_raw: float | None
    word_count: int | None
    entity_count: int


class ScoreReport(ReportBase):
    kind: Literal["gobus.scorecard"] = "gobus.scorecard"
    tool: Literal["gobus_score_article"] = "gobus_score_article"
    score_status: ScoreStatus
    overall: float | None
    refusal_reason: str | None = None
    scale: str = FLESCH_SCALE_ID
    bands: list[FleschBandInfo]
    article: ScoredArticle
    dimensions: list[ScoreDimension]
    benchmark: ScoreBenchmark | None  # agência do artigo
    reference_benchmark: ScoreBenchmark | None  # Agência Brasil, mesma janela
    flags: list[str] = []
