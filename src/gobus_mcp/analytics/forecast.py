"""Forecast de temas: share-of-voice em três janelas móveis e projeção amortecida.

Janelas (``WINDOWS``): 3 dias dentro de 14, 7 dentro de 28 e 21 dentro de 84
(``topThemes`` + ``analyticsKpis`` por range, D7 do plano). Para cada tema e janela:
razão de share-of-voice sem sobreposição e taxa log por dia (``ratios.per_day_log_rate``),
comparáveis entre janelas. A razão só conta com ``MIN_WINDOW_ARTICLES`` artigos do tema
na janela e no baseline anterior (``w + b_prev ≥ 5``); tema sem nenhuma janela assim fica
fora da lista.

- ``composite``: média ponderada das taxas (0,5/0,3/0,2), **renormalizada** nas janelas
  presentes (janela sem cobertura ou sem o tema fica de fora);
- ``momentum``: ``k3 − k7`` (sem a de 3 dias, ``k7 − k21``) contra ±ln(1,10)/7;
  ``undetermined`` sem duas taxas;
- ``confidence``: janelas ok e volume na de 7 dias; cobertura degradada limita a ``low``;
  a recuperação pós-defeso tira um nível;
- ``project``: ``s(t) = s0·exp(k·φ(1−φᵗ)/(1−φ))`` com φ = 0,9 (multiplicador em
  [0,2; 5]); esperado(t) = s(t) × volume esperado da plataforma no dia (nível da fase ×
  perfil de dia útil, feriados como domingo; a partir de 26/10 o nível ``normal``);
  intervalo de Poisson ``E ± 1,96·√E`` (v1, sem cenários k±σ).

A correção de dia útil está sempre ligada (sem toggle de fim de semana).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from gobus_mcp.analytics.ratios import per_day_log_rate, share_of_voice_ratio
from gobus_mcp.analytics.themes import WindowPair, pair_status
from gobus_mcp.analytics.weekday import effective_days, expected_platform_volume
from gobus_mcp.calendario import (
    BLACKOUTS,
    CLASSIFIER_CUTOFF,
    NON_WORKING_DAYS,
    BlackoutPeriod,
    DateRange,
    classifier_changed_within,
    overlaps_blackout,
    phase,
    rolling_range,
)
from gobus_mcp.domains import theme_domain
from gobus_mcp.payloads.common import Confidence, Status
from gobus_mcp.payloads.forecast import (
    MAX_HORIZON_DAYS,
    ForecastTheme,
    ForecastWindow,
    Momentum,
    Projection,
    ProjectionDay,
    WindowKey,
    WindowRatio,
)

WINDOWS: Mapping[WindowKey, tuple[int, int]] = {"3d": (3, 14), "7d": (7, 28), "21d": (21, 84)}
WEIGHTS: Mapping[WindowKey, float] = {"3d": 0.5, "7d": 0.3, "21d": 0.2}
FORECAST_RANGE_DAYS: tuple[int, ...] = (3, 14, 7, 28, 21, 84)

PHI = 0.9
MIN_MULTIPLIER, MAX_MULTIPLIER = 0.2, 5.0
MIN_HORIZON, MAX_HORIZON = 1, MAX_HORIZON_DAYS
DEFAULT_HORIZON = 21
MOMENTUM_DELTA = math.log(1.10) / 7  # ±10% por semana
Z = 1.96
HIGH_COUNT7, MEDIUM_COUNT7 = 20, 5
# Artigos do tema na janela mais o baseline anterior (w + b_prev) para a razão contar:
# abaixo disso o share-of-voice de 1 contra 0 é ruído (como o minArticles do trendingThemes).
MIN_WINDOW_ARTICLES = 5

_CONFIDENCE = ("low", "medium", "high")


def effective_weights(
    present: Iterable[str], weights: Mapping[str, float] = WEIGHTS
) -> dict[str, float]:
    """Pesos renormalizados entre as janelas presentes."""
    keys = [k for k in weights if k in set(present)]
    total = sum(weights[k] for k in keys)
    return {k: weights[k] / total for k in keys} if total else {}


def composite(
    rates: Mapping[str, float | None], weights: Mapping[str, float] = WEIGHTS
) -> float | None:
    """Taxa composta (log por dia): média ponderada nas janelas com taxa."""
    present = [k for k, v in rates.items() if v is not None and k in weights]
    eff = effective_weights(present, weights)
    if not eff:
        return None
    return sum(eff[k] * rates[k] for k in eff)


def momentum(
    rates: Mapping[str, float | None], *, delta: float = MOMENTUM_DELTA
) -> tuple[Momentum, float | None]:
    """Aceleração = ``k3 − k7`` (fallback ``k7 − k21``); ``undetermined`` sem dados."""
    k3, k7, k21 = rates.get("3d"), rates.get("7d"), rates.get("21d")
    if k3 is not None and k7 is not None:
        acc = k3 - k7
    elif k7 is not None and k21 is not None:
        acc = k7 - k21
    else:
        return "undetermined", None
    if acc > delta:
        return "accelerating", acc
    if acc < -delta:
        return "decelerating", acc
    return "stable", acc


def confidence(windows_ok: int, count7: int, *, phase: str, degraded: bool = False) -> Confidence:
    """``high``: 3 janelas ok e ≥ 20 artigos em 7 dias; ``medium``: ≥ 2 janelas e ≥ 5;
    senão ``low``. Cobertura degradada limita a ``low``; ``recovery`` tira um nível."""
    if windows_ok >= 3 and count7 >= HIGH_COUNT7:
        level = 2
    elif windows_ok >= 2 and count7 >= MEDIUM_COUNT7:
        level = 1
    else:
        level = 0
    if degraded:
        level = 0
    if phase == "recovery":
        level -= 1
    return _CONFIDENCE[max(level, 0)]


def clamp_horizon(h: int) -> tuple[int, str | None]:
    """``horizon_days`` efetivo (1–28) e o aviso quando foi ajustado."""
    value = min(max(int(h), MIN_HORIZON), MAX_HORIZON)
    if value == h:
        return value, None
    return value, (
        f"Horizonte de {h} dias fora do intervalo aceito ({MIN_HORIZON}–{MAX_HORIZON}); "
        f"usando {value} dias."
    )


def damped_multiplier(k: float, t: int, phi: float = PHI) -> float:
    """``exp(k·φ(1−φᵗ)/(1−φ))`` limitado a [0,2; 5]."""
    raw = math.exp(k * phi * (1 - phi**t) / (1 - phi))
    return min(max(raw, MIN_MULTIPLIER), MAX_MULTIPLIER)


def project(
    share_now: float,
    k: float,
    *,
    start: date,
    horizon_days: int,
    weights: Mapping[int, float],
    levels: Mapping[str, float],
    phi: float = PHI,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    holidays: frozenset[date] = NON_WORKING_DAYS,
) -> Projection:
    """Projeção de artigos do tema de ``start`` (D) a ``start + H − 1``."""
    daily: list[ProjectionDay] = []
    total = 0.0
    for i in range(horizon_days):
        day = start + timedelta(days=i)
        share = share_now * damped_multiplier(k, i + 1, phi)
        volume = expected_platform_volume(day, weights, levels, periods=periods, holidays=holidays)
        expected = share * volume
        total += expected
        daily.append(ProjectionDay(date=day, expected=round(expected, 2)))
    margin = Z * math.sqrt(total)
    return Projection(
        horizon_days=horizon_days,
        expected_articles=round(total, 1),
        low=round(max(total - margin, 0.0), 1),
        high=round(total + margin, 1),
        share_now=round(share_now, 4),
        share_at_horizon=round(share_now * damped_multiplier(k, horizon_days, phi), 4),
        daily=daily,
    )


def _window_ratio(pair: WindowPair, label: str, k_themes: int) -> WindowRatio | None:
    stat = pair.stats().get(label)
    if stat is None or stat.w + stat.b_prev < MIN_WINDOW_ARTICLES:
        return None
    ratio = share_of_voice_ratio(stat, k_themes=k_themes)
    return WindowRatio(
        ratio=round(ratio, 3),
        window_count=stat.w,
        baseline_prev_count=stat.b_prev,
        share=round(stat.share, 4),
        per_day_rate=round(per_day_log_rate(ratio, pair.window_days, pair.baseline_days), 5),
    )


def forecast_themes(
    pairs: Mapping[str, WindowPair],
    *,
    today: date,
    horizon_days: int,
    limit: int,
    weights: Mapping[int, float],
    levels: Mapping[str, float],
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    cutoff: date | None = CLASSIFIER_CUTOFF,
    holidays: frozenset[date] = NON_WORKING_DAYS,
) -> tuple[dict[WindowKey, ForecastWindow], list[ForecastTheme]]:
    """Janelas do payload e os ``limit`` temas de maior taxa composta, com projeção.

    Janela ausente (query falhou) ou com cobertura < 50% fica ``unavailable`` e fora do
    composto; entre 50% e 80% é ``degraded`` (confiança ``low``).
    """
    horizon_days, _ = clamp_horizon(horizon_days)
    statuses: dict[WindowKey, Status] = {
        key: pair_status(pairs[key]) if key in pairs else "unavailable" for key in WINDOWS
    }
    usable = [key for key in WINDOWS if statuses[key] != "unavailable"]
    eff = effective_weights(usable)

    windows: dict[WindowKey, ForecastWindow] = {}
    for key, (W, B) in WINDOWS.items():
        pair = pairs.get(key)
        coverage = pair.coverage if pair is not None else None
        windows[key] = ForecastWindow(
            window_days=W,
            baseline_days=B,
            weight=WEIGHTS[key],
            effective_weight=round(eff.get(key, 0.0), 4),
            classified_coverage=None if coverage is None else round(coverage, 4),
            status=statuses[key],
            business_days=round(
                effective_days(
                    DateRange(today - timedelta(days=W), today - timedelta(days=1)),
                    weights,
                    holidays=holidays,
                ),
                2,
            ),
            baseline_overlaps_blackout=overlaps_blackout(rolling_range(B, today), periods),
        )
    if not usable:
        return windows, []

    current_phase = phase(today, periods)
    degraded = any(statuses[key] == "degraded" for key in usable)
    last_day = today + timedelta(days=horizon_days - 1)
    flags = [
        flag
        for flag, on in (
            ("degraded_coverage", degraded),
            (
                "classifier_changed",
                any(
                    classifier_changed_within(rolling_range(WINDOWS[k][1], today), cutoff)
                    for k in usable
                ),
            ),
            ("blackout_baseline", any(windows[k].baseline_overlaps_blackout for k in usable)),
            ("recovery", current_phase == "recovery"),
            (
                "horizon_crosses_blackout_end",
                any(today <= p.end <= last_day for p in periods),
            ),
        )
        if on
    ]

    labels = sorted({label for key in usable for label in pairs[key].including.counts})
    k_themes = max(len(labels), 1)
    themes: list[ForecastTheme] = []
    for label in labels:
        ratios: dict[WindowKey, WindowRatio | None] = {
            key: _window_ratio(pairs[key], label, k_themes) if key in usable else None
            for key in WINDOWS
        }
        rates = {key: (wr.per_day_rate if wr else None) for key, wr in ratios.items()}
        k = composite(rates)
        if k is None:
            continue
        state, acc = momentum(rates)
        reference = ratios["7d"] or ratios["3d"] or ratios["21d"]
        windows_ok = sum(1 for key in usable if ratios[key] and statuses[key] == "ok")
        count7 = ratios["7d"].window_count if ratios["7d"] else 0
        themes.append(
            ForecastTheme(
                label=label,
                domain=theme_domain(label),
                windows=ratios,
                per_day_rate=round(k, 5),
                weekly_multiplier=round(math.exp(7 * k), 3),
                momentum=state,
                acceleration=None if acc is None else round(acc, 5),
                confidence=confidence(windows_ok, count7, phase=current_phase, degraded=degraded),
                projection=project(
                    reference.share,
                    k,
                    start=today,
                    horizon_days=horizon_days,
                    weights=weights,
                    levels=levels,
                    periods=periods,
                    holidays=holidays,
                ),
                flags=list(flags),
            )
        )
    themes.sort(key=lambda t: (-(t.per_day_rate or 0.0), t.label))
    return windows, themes[:limit]
