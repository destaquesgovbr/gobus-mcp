"""Base comum dos payloads (contrato único: ``_plan/fase2_5/desenho/integration.md`` §1.2–1.3).

Regras do contrato:
- campos em snake_case no Python, serializados em camelCase (``serialize_by_alias``);
  a validação aceita os dois (``validate_by_name`` + ``validate_by_alias``);
- enums em inglês ASCII; rótulos em português só em texto (``label``, ``message``);
- ``null`` sai como ``null`` (não usar ``exclude_none``);
- ``schema_version`` = 1: campo opcional novo mantém a versão; remover ou renomear sobe.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Estado de um dado/bloco (fonte de dados ou seção de um relatório).
Status = Literal["ok", "degraded", "unavailable"]

# Estado do relatório como um todo.
ReportStatus = Literal["ok", "partial", "empty", "unavailable"]

# Fontes de dados com saúde avaliada (ver ``gobus_mcp.data_status``).
DataKey = Literal[
    "themes",
    "summaries",
    "sentiment_labels",
    "sentiment_analytics",
    "entities_ner",
    "readability",
    "word_count",
    "article_trending",
    "entity_ranking",
    "indexing_lag",
    "agency_activity",
]

# Avisos exibidos ao usuário. Detecção sempre dinâmica; data fixa só como dica de ``since``.
NoticeCode = Literal[
    "THEMES_UNCLASSIFIED",
    "SENTIMENT_UNAVAILABLE",
    "READABILITY_UNAVAILABLE",
    "TRENDING_ENTITIES_STALE",
    "BASELINE_ZERO_SUPPRESSED",
    "CLASSIFIER_CHANGED",
    "ELECTORAL_BLACKOUT",
    "POST_BLACKOUT_RECOVERY",
    "INDEXING_LAG",
    "SAMPLE_TRUNCATED",
]

NoticeSeverity = Literal["info", "warn", "error"]

Phase = Literal["normal", "blackout", "recovery"]


class Payload(BaseModel):
    """Base de todo modelo de payload: snake_case no Python, camelCase no JSON."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class DataStatus(Payload):
    """Saúde de uma fonte de dados. ``since`` = início provável do problema (dica)."""

    key: DataKey
    status: Status
    since: date | None = None
    message: str
    metric: dict[str, float | int | None] = {}


class Notice(Payload):
    """Aviso ao usuário; ``affects`` lista os blocos do relatório afetados."""

    code: NoticeCode
    severity: NoticeSeverity
    message: str
    since: date | None = None
    affects: list[str] = []


class CalendarContext(Payload):
    """Fase do calendário (defeso eleitoral e recuperação) na data de referência."""

    phase: Phase
    label: str | None
    blackout_start: date | None
    blackout_end: date | None
    recovery_until: date | None
    days_to_end: int | None
    silenced_agencies: int | None = None
    resumed_agencies: int | None = None


class Window(Payload):
    """Janela temporal de uma análise. ``end`` é exclusivo.

    ``closed``: dias fechados (termina em D 00:00 BRT); ``rolling``: móvel até agora (UTC).
    """

    kind: Literal["closed", "rolling"]
    start: datetime
    end: datetime
    days: int
    bucket_tz: Literal["America/Sao_Paulo", "UTC"]
    baseline_overlaps_blackout: bool = False


class ReportBase(Payload):
    """Campos comuns a todo relatório estruturado (``structuredContent``).

    ``summary`` é o Markdown entregue como ``content`` (o que o Claude Code mostra).
    """

    schema_version: Literal[1] = 1
    kind: str
    tool: str
    summary: str
    status: ReportStatus
    generated_at: datetime
    reference_date: date
    params: dict
    calendar: CalendarContext
    data_status: list[DataStatus]
    notices: list[Notice]
