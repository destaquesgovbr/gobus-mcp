"""Perfil de dia útil, feriados e nível de volume da plataforma por fase.

O volume do acervo varia muito na semana (set/2026: ~189 artigos por dia útil, ~50 no
sábado e ~23 no domingo) e cai no defeso. Para projetar contagens (forecast) e comparar
janelas de tamanhos diferentes:

- ``weekday_profile``: peso de cada dia da semana relativo à média dos dias úteis,
  estimado do ``platform_daily`` do snapshot de atividade (dias UTC da API), sem feriados
  e sem o dia corrente; com menos de ``min_days`` dias, usa ``DEFAULT_WEEKDAY_PROFILE``;
- ``effective_days``: quantos "dias úteis equivalentes" um intervalo tem (feriado conta
  como domingo; integration.md §1.8);
- ``level_by_phase``: artigos por dia útil equivalente em cada fase de nível (``normal`` e
  ``blackout``; a recuperação usa o nível ``normal``, como o D2 usa o baseline pré-defeso);
- ``expected_platform_volume``: nível da fase do dia × peso do dia da semana.

Funções puras; ``today`` sempre injetado.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import fmean
from typing import Literal

from gobus_mcp.calendario import (
    BLACKOUTS,
    NON_WORKING_DAYS,
    BlackoutPeriod,
    DateRange,
    effective_weekday,
    phase,
)

LevelPhase = Literal["normal", "blackout"]

# Set/2026 (defeso): 189 artigos/dia útil, sábado ~50 (0,26) e domingo ~23 (0,12).
DEFAULT_WEEKDAY_PROFILE: Mapping[int, float] = {
    0: 1.0,
    1: 1.0,
    2: 1.0,
    3: 1.0,
    4: 1.0,
    5: 0.26,
    6: 0.12,
}

# Artigos por dia útil equivalente: jun/2026 (205/dia) e defeso (136/dia), divididos pelo
# peso médio da semana padrão (5,38/7).
DEFAULT_LEVEL_BY_PHASE: Mapping[str, float] = {"normal": 267.0, "blackout": 177.0}

MIN_WEIGHT = 0.01  # piso: nenhum dia da semana com peso zero (evita divisão por zero)


@dataclass(frozen=True)
class WeekdayProfile:
    """Pesos por dia da semana (0 = segunda) e a origem da estimativa."""

    weights: Mapping[int, float]
    source: Literal["snapshot", "default"]
    days_used: int


def weekday_profile(
    platform_daily: Mapping[date, int],
    today: date,
    *,
    lookback_days: int = 56,
    min_days: int = 28,
    holidays: frozenset[date] = NON_WORKING_DAYS,
) -> WeekdayProfile:
    """Perfil semanal dos últimos ``lookback_days`` dias fechados (``[D−lookback, D−1]``).

    Peso de cada dia = média do dia ÷ média das médias de segunda a sexta. Feriados ficam
    fora; dia da semana sem amostra herda o padrão.
    """
    start = today - timedelta(days=lookback_days)
    samples: dict[int, list[int]] = {wd: [] for wd in range(7)}
    used = 0
    for day, count in platform_daily.items():
        if not (start <= day < today) or day in holidays:
            continue
        samples[day.weekday()].append(count)
        used += 1
    business = [fmean(samples[wd]) for wd in range(5) if samples[wd]]
    base = fmean(business) if business else 0.0
    if used < min_days or base <= 0:
        return WeekdayProfile(dict(DEFAULT_WEEKDAY_PROFILE), "default", used)
    weights = {
        wd: max(round(fmean(samples[wd]) / base, 3), MIN_WEIGHT)
        if samples[wd]
        else DEFAULT_WEEKDAY_PROFILE[wd]
        for wd in range(7)
    }
    return WeekdayProfile(weights, "snapshot", used)


def _weight(day: date, weights: Mapping[int, float], holidays: frozenset[date]) -> float:
    wd = effective_weekday(day, holidays)
    return max(weights.get(wd, DEFAULT_WEEKDAY_PROFILE[wd]), MIN_WEIGHT)


def effective_days(
    r: DateRange, weights: Mapping[int, float], *, holidays: frozenset[date] = NON_WORKING_DAYS
) -> float:
    """Dias úteis equivalentes do intervalo (feriado conta como domingo)."""
    return sum(_weight(day, weights, holidays) for day in r)


def weekday_normalize(
    count: float,
    r: DateRange,
    weights: Mapping[int, float],
    *,
    holidays: frozenset[date] = NON_WORKING_DAYS,
) -> float:
    """Contagem por dia útil equivalente no intervalo."""
    return count / effective_days(r, weights, holidays=holidays)


def level_phase(day: date, periods: tuple[BlackoutPeriod, ...] = BLACKOUTS) -> LevelPhase:
    """Fase de nível do dia: ``blackout`` no defeso; ``normal`` fora dele (inclusive na
    recuperação, quando as agências voltam a publicar)."""
    return "blackout" if phase(day, periods) == "blackout" else "normal"


def _complete_levels(measured: Mapping[str, float]) -> dict[str, float]:
    if not measured:
        return dict(DEFAULT_LEVEL_BY_PHASE)
    levels = dict(measured)
    ref_key, ref_value = next(iter(measured.items()))
    for key, default in DEFAULT_LEVEL_BY_PHASE.items():
        if key not in levels:
            levels[key] = round(ref_value * default / DEFAULT_LEVEL_BY_PHASE[ref_key], 1)
    return levels


def level_by_phase(
    platform_daily: Mapping[date, int],
    weights: Mapping[int, float],
    *,
    today: date,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    holidays: frozenset[date] = NON_WORKING_DAYS,
    min_days: int = 7,
) -> dict[str, float]:
    """Artigos por dia útil equivalente em cada fase de nível, medidos no snapshot.

    Fase com menos de ``min_days`` dias (sem feriados, antes de D) é completada pela
    proporção de ``DEFAULT_LEVEL_BY_PHASE`` em relação à fase medida; sem nenhuma, o padrão.
    """
    totals: dict[str, list[float]] = {}  # fase → [artigos, pesos, dias]
    for day, count in platform_daily.items():
        if day >= today or day in holidays:
            continue
        acc = totals.setdefault(level_phase(day, periods), [0.0, 0.0, 0])
        acc[0] += count
        acc[1] += _weight(day, weights, holidays)
        acc[2] += 1
    measured = {
        key: round(articles / weight_sum, 1)
        for key, (articles, weight_sum, days) in totals.items()
        if days >= min_days and weight_sum > 0
    }
    return _complete_levels(measured)


def expected_platform_volume(
    day: date,
    weights: Mapping[int, float],
    levels: Mapping[str, float],
    *,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    holidays: frozenset[date] = NON_WORKING_DAYS,
) -> float:
    """Artigos esperados na plataforma em ``day``: nível da fase × peso do dia."""
    key = level_phase(day, periods)
    level = levels.get(key, DEFAULT_LEVEL_BY_PHASE[key])
    return level * _weight(day, weights, holidays)
