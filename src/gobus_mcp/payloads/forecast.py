"""Payload de ``gobus_forecast_trends`` (app ``ui://forecast-radar``, G3) — integration.md §1.5.

- ``windows{3d,7d,21d}``: janelas móveis (UTC) com baseline que as inclui (14/28/84 dias),
  peso nominal e efetivo (renormalizado entre as janelas utilizáveis) e cobertura de
  classificação. Sem ``weekend_correction``: share-of-voice e perfil de dia útil estão
  sempre ligados;
- ``platform``: perfil semanal (chaves ``"0"``…``"6"``, segunda = 0), nível por fase
  (artigos por dia útil equivalente) e a origem do perfil;
- ``themes``: até 10 temas com razão por janela, taxa log por dia, momentum e projeção
  amortecida (φ = 0,9) com intervalo de Poisson. A série diária histórica de tema não
  existe na v1; a ``daily`` da projeção é calculada.
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
