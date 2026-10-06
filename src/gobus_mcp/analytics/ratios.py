"""Razões de crescimento janela × baseline.

O ``trendingThemes`` da graphql-api calcula ``growthScore = (w/W) / (b_incl/B)`` com um
baseline de ``B`` dias que **inclui** a janela de ``W`` dias. Para o usuário, o limiar e a
razão fazem sentido sem sobreposição: ``r = (w/W) / (b_prev/(B−W))``, com
``b_prev = b_incl − w``.

- ``overlap_growth_threshold``: converte o limiar do usuário ``r0`` no limiar da API
  ``g0 = B·r0 / (r0·W + B − W)``. A conversão é monotônica, então a ordem e o ``limit``
  do resolver continuam corretos. Nunca usar ``growthThreshold: 0`` (dispara o N+1 de
  ``topArticles`` no resolver).
- ``true_growth_ratio`` / ``ratio_from_trending_row``: a razão sem sobreposição, com
  suavização de Laplace (``alpha``) para baseline zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


def overlap_growth_threshold(r0: float, window_days: int, baseline_days: int) -> float:
    """Limiar do ``growthThreshold`` (baseline sobreposto) equivalente à razão ``r0``."""
    if r0 <= 0:
        raise ValueError("o limiar de crescimento deve ser positivo")
    if baseline_days <= window_days:
        raise ValueError("baseline_days deve ser maior que window_days")
    W, B = window_days, baseline_days  # notação da fórmula
    return B * r0 / (r0 * W + B - W)


@dataclass(frozen=True)
class GrowthRatio:
    """Razão sem sobreposição. ``is_new``: nenhum artigo antes da janela."""

    ratio: float
    window_count: int
    baseline_prev_count: int
    is_new: bool


def true_growth_ratio(
    window_count: int,
    baseline_count_incl: float,
    window_days: int,
    baseline_days: int,
    *,
    alpha: float = 1.0,
) -> GrowthRatio:
    """``((w+α)/W) / ((b_prev+α)/(B−W))`` com ``b_prev = max(round(b_incl) − w, 0)``."""
    if baseline_days <= window_days:
        raise ValueError("baseline_days deve ser maior que window_days")
    b_prev = max(round(baseline_count_incl) - window_count, 0)
    prev_days = baseline_days - window_days
    ratio = ((window_count + alpha) / window_days) / ((b_prev + alpha) / prev_days)
    return GrowthRatio(ratio, window_count, b_prev, b_prev == 0)


def ratio_from_trending_row(
    row: Mapping, window_days: int, baseline_days: int, *, alpha: float = 1.0
) -> GrowthRatio:
    """Razão sem sobreposição de uma linha do ``trendingThemes``
    (``b_incl = baselineDailyAvg · B``)."""
    window_count = int(row.get("windowCount") or 0)
    baseline_incl = float(row.get("baselineDailyAvg") or 0.0) * baseline_days
    return true_growth_ratio(window_count, baseline_incl, window_days, baseline_days, alpha=alpha)
