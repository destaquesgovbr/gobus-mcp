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

G2 (anomalias e forecast; D7 do plano): contagens de ``topThemes`` + ``analyticsKpis`` por
range, sem o ``trendingThemes``:
- ``theme_stats``: tira a sobreposição (range maior inclui o menor) e usa como total só os
  artigos **classificados** (Σ ``topThemes``) — o buraco de classificação reduz a cobertura,
  não distorce a razão;
- ``share_of_voice_ratio``: razão da fatia do tema na janela contra a fatia no baseline,
  com Laplace. Cancela fim de semana, dia parcial e atraso do Typesense, e **atenua** (não
  cancela) a queda do defeso, porque a mistura de agências muda;
- ``per_day_log_rate``: ``ln(r)/Δt`` com ``Δt = B/2`` (distância entre os centros da
  janela e do baseline anterior), comparável entre janelas;
- ``severity`` (0–1) e ``band`` (``normal | watch | alert``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from gobus_mcp.payloads.common import Band


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


# ── G2 ──────────────────────────────────────────────────────────────────────


def laplace_ratio(
    w: float, window_days: float, b: float, baseline_days: float, *, alpha: float = 1.0
) -> float:
    """Razão de taxas diárias com Laplace: ``((w+α)/W) / ((b+α)/B)`` (janela × baseline
    **sem** sobreposição). Baseline zero não divide por zero."""
    if window_days <= 0 or baseline_days <= 0:
        raise ValueError("window_days e baseline_days devem ser positivos")
    return ((w + alpha) / window_days) / ((b + alpha) / baseline_days)


@dataclass(frozen=True)
class ThemeWindowStat:
    """Contagens de um tema: ``w`` na janela e ``b_prev`` no baseline anterior a ela;
    ``total_*`` = artigos classificados (Σ de todos os temas) nos mesmos intervalos."""

    label: str
    w: int
    b_prev: int
    total_w: int
    total_prev: int

    @property
    def share(self) -> float:
        """Fatia do tema entre os classificados da janela (0 se a janela está vazia)."""
        return self.w / self.total_w if self.total_w else 0.0


def theme_stats(
    window_counts: Mapping[str, int], including_counts: Mapping[str, int]
) -> dict[str, ThemeWindowStat]:
    """Estatísticas por tema a partir de dois ranges móveis: a janela (``W`` dias) e o
    range que a **inclui** (``B`` dias). ``b_prev = max(incl − w, 0)``; os totais são as
    somas das contagens (artigos classificados)."""
    total_w = sum(window_counts.values())
    total_prev = max(sum(including_counts.values()) - total_w, 0)
    labels = sorted(set(window_counts) | set(including_counts))
    stats = {}
    for label in labels:
        w = window_counts.get(label, 0)
        b_prev = max(including_counts.get(label, 0) - w, 0)
        stats[label] = ThemeWindowStat(label, w, b_prev, total_w, total_prev)
    return stats


def share_of_voice_ratio(s: ThemeWindowStat, *, k_themes: int, alpha: float = 1.0) -> float:
    """``((w+α)/(T_w+αK)) / ((b_prev+α)/(T_prev+αK))``: razão das fatias do tema."""
    k = max(k_themes, 1)
    share_w = (s.w + alpha) / (s.total_w + alpha * k)
    share_prev = (s.b_prev + alpha) / (s.total_prev + alpha * k)
    return share_w / share_prev


def per_day_log_rate(ratio: float, window_days: int, baseline_days: int) -> float:
    """Taxa de crescimento por dia, ``ln(ratio) / (B/2)``.

    ``B`` é o range que inclui a janela (3/14 → Δt 7; 7/28 → 14; 21/84 → 42): é a distância
    entre o centro da janela e o centro do baseline anterior a ela.
    """
    if ratio <= 0:
        raise ValueError("a razão deve ser positiva")
    if baseline_days <= window_days:
        raise ValueError("baseline_days deve ser maior que window_days")
    return math.log(ratio) / (baseline_days / 2)


def severity(score: float, threshold: float) -> float:
    """Severidade 0–1 de um escore multiplicativo contra o limiar da sensibilidade.

    ``clamp(ln(score) / (3·ln(thr)), 0, 1)``: no limiar vale 1/3 (início de ``watch``), em
    ``thr²`` vale 2/3 (``alert``) e satura em ``thr³``. Abaixo de 1× é 0.
    """
    if threshold <= 1:
        raise ValueError("o limiar deve ser maior que 1")
    if score <= 1:
        return 0.0
    return min(math.log(score) / (3 * math.log(threshold)), 1.0)


BAND_WATCH = 0.33
BAND_ALERT = 0.66
SEVERITY_WATCH_MAX = 0.65  # teto da faixa watch: sinal que a razão sozinha não sustenta


def band(sev: float) -> Band:
    """Faixa da severidade: < 0,33 ``normal``; < 0,66 ``watch``; senão ``alert``."""
    if sev < BAND_WATCH:
        return "normal"
    if sev < BAND_ALERT:
        return "watch"
    return "alert"
