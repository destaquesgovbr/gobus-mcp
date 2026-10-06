"""Payload de ``gobus_get_message_coherence`` (F5, G3): ``CoherenceReport``, schema_version 1.

Sem app nesta fase: a tool devolve o Markdown (``summary``) e o builder entrega este modelo,
que já serve de payload para o futuro ``ui://coherence-matrix`` (só falta o binding e o JS).

Índice 1–5 = média **renormalizada** das dimensões disponíveis (pesos nominais em
``DIMENSION_WEIGHTS``), com cortes provisórios ``INDEX_CUTS`` (calibração como sanity check
em ``_experiments/coherence-calibration-2026-10/``):

- ``entities`` (E, 0,35): cosseno dos vetores salience × idf por agência;
- ``timing`` (T, 0,25): 1º artigo em até 48 h (BRT) + Jaccard dos dias de publicação;
- ``framing`` (F, 0,25): 1 − JSD das distribuições de enquadramento lexical;
- ``tone`` (S, 0,15): 1 − JSD das distribuições de sentimento (só com cobertura ≥ 50%).

Republicadoras ficam sempre fora do índice, num bloco à parte. Enums em inglês ASCII;
rótulos PT só em texto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from gobus_mcp.payloads.common import Payload, ReportBase, Window

DimensionKey = Literal["entities", "timing", "framing", "tone"]
Frame = Literal["announcement", "result", "challenge", "service", "agenda"]
SubjectKind = Literal["entity", "theme"]
ResolvedBy = Literal["id", "search", "taxonomy", "literal"]
IndexStatus = Literal["scored", "insufficient", "no_articles"]
DimensionStatus = Literal["ok", "unavailable"]

DIMENSION_ORDER: tuple[DimensionKey, ...] = ("entities", "timing", "framing", "tone")
DIMENSION_WEIGHTS: dict[DimensionKey, float] = {
    "entities": 0.35,
    "timing": 0.25,
    "framing": 0.25,
    "tone": 0.15,
}
# Cortes do índice 1–5 sobre o score 0–1 (provisórios até a calibração).
INDEX_CUTS: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8)

MAX_AGENCIES = 12  # emissores no payload e no Markdown (por volume)
MAX_SHARED_ANCHORS = 8
MAX_EXCLUSIVE_ANCHORS = 3
MAX_DIVERGENCES = 5
MAX_ALTERNATIVES = 2


class EntityAlternative(Payload):
    """Outra entidade devolvida pelo ``entitySearch`` (resolução por nome)."""

    entity_id: str
    name: str
    type: str | None
    article_count: int | None


class CoherenceSubject(Payload):
    """O que está sendo comparado: uma entidade canônica ou uma label L1 de tema."""

    kind: SubjectKind
    id: str | None  # entityId (entidade) ou None (tema)
    label: str
    type: str | None  # tipo da entidade (POLICY, ORG, …); None para tema
    resolved_by: ResolvedBy
    query: str | None = None  # o texto pedido, quando a resolução não foi literal
    alternatives: list[EntityAlternative] = []


class SampleInfo(Payload):
    """Amostra de artigos da janela (``articles``, até 4 páginas de 250)."""

    found: int
    fetched: int
    truncated: bool
    emitters: int
    emitter_articles: int
    single_article_agencies: int  # não republicadoras com 1 artigo (fora do índice)
    republisher_articles: int
    mock_summaries_ignored: int


class CoherenceDimension(Payload):
    """Uma dimensão do índice. ``effective_weight`` = peso renormalizado (None se fora)."""

    key: DimensionKey
    weight: float
    effective_weight: float | None
    value: float | None
    status: DimensionStatus
    detail: str
    metric: dict[str, float | int | None] = {}


class CoherenceIndex(Payload):
    score: float | None
    level: int | None = Field(default=None, ge=1, le=5)
    cuts: list[float] = Field(default_factory=lambda: list(INDEX_CUTS))


class Anchor(Payload):
    """Entidade-âncora (``label`` = o texto mais frequente nas menções)."""

    entity_id: str
    label: str
    type: str | None
    agencies: int
    weight: float


class ToneCounts(Payload):
    positive: int
    negative: int
    neutral: int


class AgencyCoherence(Payload):
    """Um emissor (agência não republicadora com ≥ 2 artigos)."""

    agency_key: str
    agency_name: str
    articles: int
    first_published_at: datetime  # BRT
    delay_hours: float  # desde o 1º artigo do primeiro emissor
    active_days: int
    dominant_frame: Frame | None
    frames: dict[str, int]
    tone: ToneCounts | None
    exclusive_anchors: list[Anchor]


class PairDivergence(Payload):
    """Par de emissores com a menor similaridade combinada."""

    agencies: list[str] = Field(min_length=2, max_length=2)
    similarity: float
    weakest: DimensionKey | None
    by_dimension: dict[str, float | None]


class RepublisherAgency(Payload):
    agency_key: str
    agency_name: str
    articles: int
    first_published_at: datetime  # BRT
    delay_hours: float | None  # desde o 1º artigo dos emissores (None sem emissor)


class RepublishersBlock(Payload):
    articles: int
    share: float | None  # fração dos artigos da amostra
    agencies: list[RepublisherAgency]


class PriorInfo(Payload):
    """Cobertura da entidade nos 30 dias antes da janela (``entityCoverage`` DAY, UTC)."""

    window: Window
    articles: int
    daily_rate: float
    window_daily_rate: float
    truncated_start: bool


class CoherenceReport(ReportBase):
    kind: Literal["gobus.coherence"] = "gobus.coherence"
    tool: Literal["gobus_get_message_coherence"] = "gobus_get_message_coherence"
    subject: CoherenceSubject
    window: Window
    index_status: IndexStatus
    insufficient_reason: str | None = None
    index: CoherenceIndex
    dimensions: list[CoherenceDimension]
    sample: SampleInfo
    agencies: list[AgencyCoherence] = Field(max_length=MAX_AGENCIES)
    agencies_omitted: int = 0
    shared_anchors: list[Anchor] = Field(max_length=MAX_SHARED_ANCHORS)
    divergences: list[PairDivergence] = Field(max_length=MAX_DIVERGENCES)
    republishers: RepublishersBlock
    prior: PriorInfo | None = None
    hhi: float | None = None  # concentração do volume entre emissores (contexto)

    @field_validator("dimensions")
    @classmethod
    def _fixed_order(cls, value: list[CoherenceDimension]) -> list[CoherenceDimension]:
        if [d.key for d in value] != list(DIMENSION_ORDER):
            raise ValueError(
                "dimensions precisa ter as 4 dimensões em ordem fixa: " + ", ".join(DIMENSION_ORDER)
            )
        return value
