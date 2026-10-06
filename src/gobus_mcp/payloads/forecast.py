"""Payload de ``gobus_forecast_trends`` (app ``ui://forecast-radar``, G3) — integration.md §1.5.

- ``windows{3d,7d,21d}``: janelas móveis (UTC) com baseline que as inclui (14/28/84 dias),
  peso nominal e efetivo (renormalizado entre as janelas utilizáveis) e cobertura de
  classificação. Sem ``weekend_correction``: share-of-voice e perfil de dia útil estão
  sempre ligados;
- ``platform``: perfil semanal (chaves ``"0"``…``"6"``, segunda = 0), nível por fase
  (artigos por dia útil equivalente) e a origem do perfil;
- ``themes``: até 10 temas com razão por janela, taxa log por dia, momentum e projeção
  amortecida (φ = 0,9) com intervalo de Poisson. A série diária histórica de tema não
  existe na v1; a ``daily`` da projeção é calculada;
- ``horizon_options``: os horizontes do controle do app (o JS não os fixa).

No payload do app (``compact_forecast_payload``), a série diária da projeção fica só no
top-3 (o que o app desenha com momentum); o Markdown completo vai no ``content``.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from gobus_mcp.domains import Domain
from gobus_mcp.payloads.anomalies import MAX_PAYLOAD_BYTES, payload_size
from gobus_mcp.payloads.common import Confidence, Payload, ReportBase, Status

WindowKey = Literal["3d", "7d", "21d"]
Momentum = Literal["accelerating", "decelerating", "stable", "undetermined"]

MAX_THEMES = 10
MAX_HORIZON_DAYS = 28
HORIZON_OPTIONS = (7, 14, 21, 28)  # controle de horizonte do app (≤ MAX_HORIZON_DAYS)
MAX_SERIES_THEMES = 3  # temas com a série diária da projeção no payload do app


class ForecastWindow(Payload):
    window_days: int
    baseline_days: int  # range que inclui a janela
    weight: float
    effective_weight: float
    classified_coverage: float | None
    status: Status
    business_days: float | None  # dias úteis equivalentes da janela
    baseline_overlaps_blackout: bool


class PlatformInfo(Payload):
    weekday_profile: dict[str, float]
    level_by_phase: dict[str, float]
    profile_source: Literal["snapshot", "default"]


class WindowRatio(Payload):
    """Share-of-voice de um tema numa janela (sem sobreposição com o baseline)."""

    ratio: float
    window_count: int
    baseline_prev_count: int
    share: float
    per_day_rate: float


class ProjectionDay(Payload):
    date: dt.date
    expected: float


class Projection(Payload):
    horizon_days: int
    expected_articles: float
    low: float
    high: float
    share_now: float
    share_at_horizon: float
    daily: list[ProjectionDay] = Field(default_factory=list, max_length=MAX_HORIZON_DAYS)


class ForecastTheme(Payload):
    label: str
    domain: Domain
    windows: dict[WindowKey, WindowRatio | None]
    per_day_rate: float | None
    weekly_multiplier: float | None
    momentum: Momentum
    acceleration: float | None
    confidence: Confidence
    projection: Projection | None
    flags: list[str] = []


class ForecastReport(ReportBase):
    kind: Literal["gobus.forecast"] = "gobus.forecast"
    tool: Literal["gobus_forecast_trends"] = "gobus_forecast_trends"
    windows: dict[WindowKey, ForecastWindow]
    platform: PlatformInfo
    themes: list[ForecastTheme] = Field(max_length=MAX_THEMES)
    horizon_options: list[int] = Field(default_factory=lambda: list(HORIZON_OPTIONS))


def fit_forecast_budget(
    report: ForecastReport, max_bytes: int = MAX_PAYLOAD_BYTES
) -> ForecastReport:
    """Tira a série diária da projeção dos temas, do último para o primeiro, até caber em
    ``max_bytes``. Totais e intervalos da projeção ficam."""
    themes = list(report.themes)
    candidate = report
    for index in range(len(themes) - 1, -1, -1):
        if payload_size(candidate) <= max_bytes:
            break
        proj = themes[index].projection
        if proj is None or not proj.daily:
            continue
        themes[index] = themes[index].model_copy(
            update={"projection": proj.model_copy(update={"daily": []})}
        )
        candidate = report.model_copy(update={"themes": list(themes)})
    return candidate


def compact_forecast_payload(
    report: ForecastReport,
    *,
    series_themes: int = MAX_SERIES_THEMES,
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> ForecastReport:
    """Payload do app ``ui://forecast-radar``: a série diária da projeção só nos primeiros
    ``series_themes`` temas (o top-3 que o app desenha com momentum); os demais mantêm
    total, intervalo e fatias. ``fit_forecast_budget`` fica como rede de segurança."""
    themes = [
        t
        if index < series_themes or t.projection is None or not t.projection.daily
        else t.model_copy(update={"projection": t.projection.model_copy(update={"daily": []})})
        for index, t in enumerate(report.themes)
    ]
    return fit_forecast_budget(report.model_copy(update={"themes": themes}), max_bytes)
