"""Payload de ``gobus_detect_anomalies`` (app ``ui://anomaly-radar``, G3) — integration.md §1.4.

Blocos:
- ``themes``: share-of-voice de ``topThemes`` + ``analyticsKpis`` em duas janelas móveis
  (UTC); ``sustained_spike``/``sustained_drop`` exigem as duas além do limiar. A série
  diária de tema (``daily``) fica ``null`` na v1;
- ``entities``: candidatos do ``trendingEntities`` recalculados via ``entityCoverage``
  (janela fechada em D−1, nominal em BRT, contagens em dias UTC). O ``volumeRatio`` do
  upstream só aparece aqui (``upstream_volume_ratio``), nunca no Markdown;
- ``domains``: 8 gauges em ordem fixa (``DOMAIN_ORDER``).

``severity`` (0–1) e ``band`` são calculados no gobus; o app não reimplementa limiares
(``severity_bands`` traz as marcas dos gauges e ``sensitivity_options`` as opções).
O ``summary`` (Markdown, ≤ 6 KB) entra no orçamento de 20 KB do ``structuredContent``; o
Markdown completo vai no ``content`` da tool. ``compact_anomaly_payload`` deixa no payload
só o que o app desenha (séries nos sinais anômalos, teto de tendências normais) e conta o
resto em ``entities.omitted``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from gobus_mcp.analytics.ratios import BAND_ALERT, BAND_WATCH, band
from gobus_mcp.domains import DOMAIN_LABELS, DOMAIN_ORDER, Domain
from gobus_mcp.payloads.common import (
    MAX_PAYLOAD_BYTES,
    Band,
    Confidence,
    Payload,
    ReportBase,
    Status,
    Window,
    payload_size,
)

ThemeSignalKind = Literal["sustained_spike", "sustained_drop"]
EntitySignalKind = Literal[
    "coordinated_silence",
    "concentrated_coverage",
    "burst",
    "new_entity",
    "calendar_explained",
    "normal",
]
OwnerMethod = Literal["agency_key", "coverage"]

MAX_DAILY_POINTS = 28
# Payload do app: sinais de entidade anômalos (com séries) e tendências normais (sem série).
MAX_PAYLOAD_SIGNALS = 6
MAX_PAYLOAD_NORMALS = 3
# Opções de sensibilidade, na ordem do controle do app (= ``analytics.themes.SENSITIVITY``).
SENSITIVITY_OPTIONS = ("high", "medium", "low")
# Classes que alimentam os gauges de cada domínio.
SPIKE_ENTITY_KINDS = frozenset({"concentrated_coverage"})
SILENCE_ENTITY_KINDS = frozenset({"coordinated_silence"})


class Thresholds(Payload):
    """Limiares da sensibilidade escolhida."""

    ratio: float
    window_agencies: int
    silence_ratio: float
    min_count: int


class ThemeSignal(Payload):
    label: str
    domain: Domain
    kind: ThemeSignalKind
    ratio_short: float
    ratio_long: float
    count_short: int
    count_long: int
    share_long: float
    severity: float = Field(ge=0, le=1)
    band: Band
    confidence: Confidence
    flags: list[str] = []
    daily: list[int] | None = None  # null na v1


class ThemeWindows(Payload):
    short: Window
    long: Window


class ClassifiedCoverage(Payload):
    """Fração dos artigos de cada janela com tema (Σ ``topThemes`` / ``analyticsKpis``)."""

    short: float | None
    long: float | None


class ThemesBlock(Payload):
    status: Status
    note: str | None
    windows: ThemeWindows
    classified_coverage: ClassifiedCoverage
    signals: list[ThemeSignal]


class OwnerInfo(Payload):
    """Agência dona: ``entity.agencyKey`` (``agency_key``) ou a dominante em [D−90, D−8]
    sem republicadoras (``coverage``); ``share`` = fatia dela nesse período."""

    agency_key: str
    agency_name: str | None = None
    method: OwnerMethod
    share: float | None = None


class EntitySample(Payload):
    """Artigo de exemplo (vazio na v1; o G3 pode preencher)."""

    unique_id: str
    title: str
    agency_key: str | None = None
    published_at: str | None = None


class EntitySignal(Payload):
    entity_id: str
    name: str
    type: str
    domain: Domain
    kind: EntitySignalKind
    window_count: int
    baseline_count: int
    window_agencies: int
    distinct_days: int
    max_day_share: float
    ratio: float
    upstream_volume_ratio: float | None
    upstream_computed_at: datetime | None
    owner: OwnerInfo | None
    owner_window_count: int | None
    owner_activity_ratio: float | None
    silence_score: float | None
    severity: float = Field(ge=0, le=1)
    band: Band
    confidence: Confidence
    explanation: str | None
    flags: list[str] = []
    daily: list[int] = Field(default_factory=list, max_length=MAX_DAILY_POINTS)
    owner_daily: list[int] | None = Field(default=None, max_length=MAX_DAILY_POINTS)
    samples: list[EntitySample] = []


class UpstreamInfo(Payload):
    """Estado do ranking ``trendingEntities`` (candidatos)."""

    last_run_at: datetime | None
    rows_total: int
    rows_last_run: int
    rows_legacy_floor: int


class EntitiesBlock(Payload):
    status: Status
    note: str | None
    window: Window
    baseline: Window
    candidates: int
    upstream: UpstreamInfo
    signals: list[EntitySignal]
    # sinais fora do payload, por classe (estão no Markdown do ``content``)
    omitted: dict[EntitySignalKind, int] = {}


class DomainSummary(Payload):
    """Gauges de um domínio: picos (tema em alta e cobertura concentrada) e silêncios
    (silêncio coordenado e queda sustentada de tema)."""

    domain: Domain
    label: str
    spikes: int
    silences: int
    concentrated: int
    max_severity: float
    spike_level: float
    silence_level: float
    spike_band: Band
    silence_band: Band


class SeverityBands(Payload):
    """Início das faixas ``watch`` e ``alert`` da severidade (marcas dos gauges)."""

    watch: float = BAND_WATCH
    alert: float = BAND_ALERT


class AnomalyReport(ReportBase):
    kind: Literal["gobus.anomalies"] = "gobus.anomalies"
    tool: Literal["gobus_detect_anomalies"] = "gobus_detect_anomalies"
    thresholds: Thresholds
    themes: ThemesBlock
    entities: EntitiesBlock
    domains: list[DomainSummary]
    severity_bands: SeverityBands = Field(default_factory=SeverityBands)
    sensitivity_options: list[str] = Field(default_factory=lambda: list(SENSITIVITY_OPTIONS))

    @field_validator("domains")
    @classmethod
    def _fixed_order(cls, value: list[DomainSummary]) -> list[DomainSummary]:
        if [d.domain for d in value] != list(DOMAIN_ORDER):
            raise ValueError(
                "domains precisa ter os 8 domínios em ordem fixa: "
                + ", ".join(d.value for d in DOMAIN_ORDER)
            )
        return value


def summarize_domains(
    themes: Iterable[ThemeSignal], entities: Iterable[EntitySignal]
) -> list[DomainSummary]:
    """Gauges por domínio, em ``DOMAIN_ORDER``.

    - ``spikes``: temas ``sustained_spike``; ``concentrated``: entidades
      ``concentrated_coverage``; ``silences``: entidades ``coordinated_silence`` mais temas
      ``sustained_drop``;
    - ``spike_level``/``silence_level``: maior severidade de cada grupo (picos incluem a
      cobertura concentrada); ``max_severity`` = o maior dos dois.

    ``normal``, ``burst``, ``new_entity`` e ``calendar_explained`` não entram nos gauges.
    """
    acc = {d: {"spikes": 0, "silences": 0, "concentrated": 0, "up": 0.0, "down": 0.0}
           for d in DOMAIN_ORDER}  # fmt: skip
    for t in themes:
        slot = acc[t.domain]
        if t.kind == "sustained_spike":
            slot["spikes"] += 1
            slot["up"] = max(slot["up"], t.severity)
        else:
            slot["silences"] += 1
            slot["down"] = max(slot["down"], t.severity)
    for e in entities:
        slot = acc[e.domain]
        if e.kind in SPIKE_ENTITY_KINDS:
            slot["concentrated"] += 1
            slot["up"] = max(slot["up"], e.severity)
        elif e.kind in SILENCE_ENTITY_KINDS:
            slot["silences"] += 1
            slot["down"] = max(slot["down"], e.severity)
    return [
        DomainSummary(
            domain=d,
            label=DOMAIN_LABELS[d],
            spikes=s["spikes"],
            silences=s["silences"],
            concentrated=s["concentrated"],
            max_severity=max(s["up"], s["down"]),
            spike_level=s["up"],
            silence_level=s["down"],
            spike_band=band(s["up"]),
            silence_band=band(s["down"]),
        )
        for d, s in acc.items()
    ]


_TRIM_NOTE = "lista de entidades reduzida para caber no orçamento do payload"


def _with_signals(report: AnomalyReport, kept: list[EntitySignal], *, note: str | None = None):
    """``report`` com ``kept`` como sinais de entidade e os de fora somados em ``omitted``."""
    entities = report.entities
    dropped = Counter(s.kind for s in entities.signals) - Counter(s.kind for s in kept)
    omitted = Counter(entities.omitted) + dropped
    update = {"signals": list(kept), "omitted": dict(sorted(omitted.items()))}
    if note is not None:
        update["note"] = note
    return report.model_copy(update={"entities": entities.model_copy(update=update)})


def _strip_series(s: EntitySignal) -> EntitySignal:
    return s.model_copy(update={"daily": [], "owner_daily": None})


def fit_anomaly_budget(report: AnomalyReport, max_bytes: int = MAX_PAYLOAD_BYTES) -> AnomalyReport:
    """Reduz o relatório até caber em ``max_bytes``, cortando primeiro o que é ``normal``:

    1. séries diárias dos sinais ``normal``;
    2. sinais ``normal`` de menor severidade;
    3. séries diárias dos demais sinais;
    4. demais sinais de entidade, da menor severidade para a maior.

    Os sinais de tema e o ``summary`` ficam intactos; os sinais cortados entram em
    ``entities.omitted``.
    """
    if payload_size(report) <= max_bytes:
        return report

    note = report.entities.note
    note = f"{note}; {_TRIM_NOTE}" if note else _TRIM_NOTE

    def build(items: list[EntitySignal]) -> AnomalyReport:
        return _with_signals(report, items, note=note)

    def drop_weakest(items: list[EntitySignal], removable) -> tuple[list, AnomalyReport]:
        candidate = build(items)
        for weakest in sorted((s for s in items if removable(s)), key=lambda s: s.severity):
            if payload_size(candidate) <= max_bytes:
                break
            items = [s for s in items if s is not weakest]
            candidate = build(items)
        return items, candidate

    signals = [_strip_series(s) if s.kind == "normal" else s for s in report.entities.signals]
    signals, candidate = drop_weakest(signals, lambda s: s.kind == "normal")
    if payload_size(candidate) <= max_bytes:
        return candidate
    signals = [_strip_series(s) for s in signals]
    _, candidate = drop_weakest(signals, lambda s: True)
    return candidate


def compact_anomaly_payload(
    report: AnomalyReport,
    *,
    max_signals: int = MAX_PAYLOAD_SIGNALS,
    max_normals: int = MAX_PAYLOAD_NORMALS,
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> AnomalyReport:
    """Payload do app ``ui://anomaly-radar``: só o que ele desenha.

    - sinais de entidade anômalos (não ``normal``): os ``max_signals`` de maior severidade,
      com as séries diárias (a sparkline da lista);
    - tendências ``normal``: as ``max_normals`` de maior severidade, sem série;
    - o resto vai para ``entities.omitted`` (por classe); o Markdown do ``content`` tem tudo;
    - temas, gauges e ``summary`` intactos; ``fit_anomaly_budget`` fica como rede de
      segurança do orçamento.

    A ordem relativa dos sinais (severidade decrescente) é mantida.
    """
    signals = report.entities.signals
    anomalous = [s for s in signals if s.kind != "normal"][:max_signals]
    normals = [s for s in signals if s.kind == "normal"][:max_normals]
    chosen = {id(s) for s in anomalous + normals}
    kept = [s if s.kind != "normal" else _strip_series(s) for s in signals if id(s) in chosen]
    return fit_anomaly_budget(_with_signals(report, kept), max_bytes)
