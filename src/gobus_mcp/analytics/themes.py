"""Anomalias de tema: share-of-voice em duas janelas móveis (D7 do plano).

Entrada: ``topThemes(range:{days}, limit:100)`` + ``analyticsKpis(range:{days}){total}`` em
quatro ranges — janela curta 3 dias dentro de 21, janela longa 7 dentro de 28. Janelas
móveis em UTC (o ``range:{days}`` do Typesense), não fechadas.

- **Gate de cobertura** (detecção dinâmica, nunca por data): a fração de artigos com tema
  é medida na janela **e** no baseline anterior a ela; abaixo de 50% o bloco fica
  ``unavailable`` (aviso ``THEMES_UNCLASSIFIED``), abaixo de 80% ``degraded`` (confiança
  ``low``). Só a janela não basta: logo depois do conserto do F0a a janela está
  classificada e o baseline não.
- **``sustained_spike``**: SoV ≥ limiar nas duas janelas e ``w_short ≥ min_count``.
- **``sustained_drop``**: SoV ≤ 1/limiar nas duas janelas e ``b_prev ≥ min_count`` nas duas.
- **Severidade**: do sinal mais fraco das duas janelas (o que sustenta o "sustentado").
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from gobus_mcp.analytics.ratios import (
    ThemeWindowStat,
    band,
    severity,
    share_of_voice_ratio,
    theme_stats,
)
from gobus_mcp.calendario import (
    BLACKOUTS,
    CLASSIFIER_CUTOFF,
    BlackoutPeriod,
    classifier_changed_within,
    overlaps_blackout,
    phase,
    reference_date,
    rolling_range,
    rolling_window,
)
from gobus_mcp.data_status import theme_coverage_status
from gobus_mcp.domains import theme_domain
from gobus_mcp.payloads.anomalies import (
    ClassifiedCoverage,
    ThemesBlock,
    ThemeSignal,
    ThemeWindows,
    Thresholds,
)
from gobus_mcp.payloads.common import Confidence, DataStatus, Status

SHORT_WINDOW: tuple[int, int] = (3, 21)  # (janela, range que a inclui)
LONG_WINDOW: tuple[int, int] = (7, 28)
THEME_RANGE_DAYS: tuple[int, ...] = (3, 21, 7, 28)

COVERAGE_DEAD = 0.5
COVERAGE_DEGRADED = 0.8

_STATUS_RANK = {"ok": 0, "degraded": 1, "unavailable": 2}
_CONFIDENCE = ("low", "medium", "high")


@dataclass(frozen=True)
class Sensitivity:
    """Limiares de uma sensibilidade.

    - ``ratio``: razão mínima (SoV de tema; razão da entidade na cobertura concentrada);
    - ``window_agencies``: abaixo disso a cobertura é "concentrada";
    - ``silence_ratio``: razão mínima das outras agências no silêncio coordenado;
    - ``min_count``: volume mínimo para um sinal.
    """

    ratio: float
    window_agencies: int
    silence_ratio: float
    min_count: int

    def thresholds(self) -> Thresholds:
        return Thresholds(
            ratio=self.ratio,
            window_agencies=self.window_agencies,
            silence_ratio=self.silence_ratio,
            min_count=self.min_count,
        )


SENSITIVITY: Mapping[str, Sensitivity] = {
    "high": Sensitivity(ratio=1.3, window_agencies=8, silence_ratio=1.5, min_count=3),
    "medium": Sensitivity(ratio=1.5, window_agencies=5, silence_ratio=2.0, min_count=5),
    "low": Sensitivity(ratio=2.0, window_agencies=3, silence_ratio=3.0, min_count=8),
}


def parse_sensitivity(value: str | None) -> tuple[str, Sensitivity]:
    """``sensitivity`` da tool → (nome, limiares); vazio = ``medium``. Inválido levanta
    ``ValueError`` com as opções."""
    name = (value or "").strip().lower() or "medium"
    if name not in SENSITIVITY:
        raise ValueError(
            f"Sensibilidade '{value}' inválida. Opções: high (mais sinais), medium (padrão), "
            "low (só sinais fortes)."
        )
    return name, SENSITIVITY[name]


@dataclass(frozen=True)
class ThemeRange:
    """Contagens de um ``range:{days}``: artigos por tema e o total de artigos."""

    days: int
    counts: Mapping[str, int]
    total: int

    @property
    def classified(self) -> int:
        return sum(self.counts.values())

    @classmethod
    def from_response(cls, days: int, data: Mapping) -> ThemeRange:
        """De ``{"topThemes": [{label, count}], "analyticsKpis": {total}}``."""
        counts = {
            t["label"]: int(t.get("count") or 0)
            for t in data.get("topThemes") or []
            if t.get("label")
        }
        total = int((data.get("analyticsKpis") or {}).get("total") or 0)
        return cls(days, counts, total)


def classified_coverage(total: int, classified: int) -> float | None:
    """Fração classificada (``None`` sem artigos; nunca acima de 1)."""
    if total <= 0:
        return None
    return min(classified / total, 1.0)


@dataclass(frozen=True)
class WindowPair:
    """Uma janela e o range que a inclui (ex.: 3 dias dentro de 21)."""

    window: ThemeRange
    including: ThemeRange

    @property
    def window_days(self) -> int:
        return self.window.days

    @property
    def baseline_days(self) -> int:
        return self.including.days

    @property
    def prev_total(self) -> int:
        return max(self.including.total - self.window.total, 0)

    @property
    def prev_classified(self) -> int:
        return max(self.including.classified - self.window.classified, 0)

    @property
    def coverage(self) -> float | None:
        return classified_coverage(self.window.total, self.window.classified)

    @property
    def prev_coverage(self) -> float | None:
        return classified_coverage(self.prev_total, self.prev_classified)

    def stats(self) -> dict[str, ThemeWindowStat]:
        return theme_stats(self.window.counts, self.including.counts)

    def statuses(self) -> list[DataStatus]:
        """Cobertura da janela e do baseline anterior, como ``DataStatus`` de ``themes``."""
        prev_days = self.baseline_days - self.window_days
        return [
            theme_coverage_status(self.window.classified, self.window.total, days=self.window_days),
            theme_coverage_status(
                self.prev_classified,
                self.prev_total,
                days=self.baseline_days,
                scope=(f"do baseline ({prev_days} dias antes da janela de {self.window_days})"),
            ),
        ]


def _worst(statuses: Iterable[DataStatus]) -> DataStatus:
    return max(statuses, key=lambda s: (_STATUS_RANK[s.status], -(s.metric.get("ratio") or 0)))


def pair_status(pair: WindowPair) -> Status:
    """Pior status entre a cobertura da janela e a do baseline anterior."""
    return _worst(pair.statuses()).status


def theme_confidence(
    count_long: int,
    min_count: int,
    *,
    degraded: bool = False,
    recovery: bool = False,
    classifier_changed: bool = False,
) -> Confidence:
    """``high`` com ≥ 3×``min_count`` artigos na janela longa (numa queda, os que a fatia do
    baseline previa), ``medium`` com ≥ ``min_count``;
    cobertura degradada limita a ``low``; recuperação e troca de classificador tiram um
    nível cada."""
    level = 2 if count_long >= 3 * min_count else 1 if count_long >= min_count else 0
    if degraded:
        level = 0
    level -= int(recovery) + int(classifier_changed)
    return _CONFIDENCE[max(level, 0)]


def classify_sustained(
    short: Mapping[str, ThemeWindowStat],
    long: Mapping[str, ThemeWindowStat],
    *,
    sens: Sensitivity,
    k_themes: int,
    degraded: bool = False,
    recovery: bool = False,
    classifier_changed: bool = False,
    flags: Iterable[str] = (),
) -> list[ThemeSignal]:
    """Picos e quedas sustentados (as duas janelas além do limiar), por severidade."""
    extra = list(flags)
    signals: list[ThemeSignal] = []
    for label in sorted(set(short) & set(long)):
        s, lg = short[label], long[label]
        r_short = share_of_voice_ratio(s, k_themes=k_themes)
        r_long = share_of_voice_ratio(lg, k_themes=k_themes)
        if r_short >= sens.ratio and r_long >= sens.ratio and s.w >= sens.min_count:
            kind, sev = "sustained_spike", severity(min(r_short, r_long), sens.ratio)
            volume = lg.w
        elif (
            r_short <= 1 / sens.ratio
            and r_long <= 1 / sens.ratio
            and min(s.b_prev, lg.b_prev) >= sens.min_count
        ):
            kind, sev = "sustained_drop", severity(1 / max(r_short, r_long), sens.ratio)
            # numa queda, o volume que sustenta o sinal é o que a fatia do baseline previa
            volume = round(lg.b_prev * lg.total_w / lg.total_prev) if lg.total_prev else lg.w
        else:
            continue
        signals.append(
            ThemeSignal(
                label=label,
                domain=theme_domain(label),
                kind=kind,
                ratio_short=round(r_short, 3),
                ratio_long=round(r_long, 3),
                count_short=s.w,
                count_long=lg.w,
                share_long=round(lg.share, 4),
                severity=round(sev, 3),
                band=band(sev),
                confidence=theme_confidence(
                    volume,
                    sens.min_count,
                    degraded=degraded,
                    recovery=recovery,
                    classifier_changed=classifier_changed,
                ),
                flags=extra,
                daily=None,
            )
        )
    return sorted(signals, key=lambda t: (-t.severity, t.label))


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def build_themes_block(
    short: WindowPair,
    long: WindowPair,
    *,
    sens: Sensitivity,
    now: datetime,
    today: date | None = None,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    cutoff: date | None = CLASSIFIER_CUTOFF,
) -> tuple[ThemesBlock, DataStatus]:
    """Bloco de temas do ``AnomalyReport`` e o ``DataStatus`` de ``themes`` (o pior entre as
    coberturas das duas janelas e dos seus baselines)."""
    today = today or reference_date(now)
    worst = _worst([*short.statuses(), *long.statuses()])
    status: Status = worst.status

    ranges = [rolling_range(p.baseline_days, today) for p in (short, long)]
    classifier_changed = any(classifier_changed_within(r, cutoff) for r in ranges)
    blackout_baseline = [overlaps_blackout(r, periods) for r in ranges]
    recovery = phase(today, periods) == "recovery"
    degraded = status == "degraded"
    flags = [
        flag
        for flag, on in (
            ("degraded_coverage", degraded),
            ("classifier_changed", classifier_changed),
            ("blackout_baseline", any(blackout_baseline)),
            ("recovery", recovery),
        )
        if on
    ]

    signals: list[ThemeSignal] = []
    note: str | None = None
    if status == "unavailable":
        note = f"Bloco de temas indisponível. {worst.message}."
    else:
        labels = set(short.including.counts) | set(long.including.counts)
        signals = classify_sustained(
            short.stats(),
            long.stats(),
            sens=sens,
            k_themes=max(len(labels), 1),
            degraded=degraded,
            recovery=recovery,
            classifier_changed=classifier_changed,
            flags=flags,
        )
        if degraded:
            note = (
                f"Cobertura de classificação parcial; confiança limitada a baixa. {worst.message}."
            )

    block = ThemesBlock(
        status=status,
        note=note,
        windows=ThemeWindows(
            short=rolling_window(
                short.window_days, now, baseline_overlaps_blackout=blackout_baseline[0]
            ),
            long=rolling_window(
                long.window_days, now, baseline_overlaps_blackout=blackout_baseline[1]
            ),
        ),
        classified_coverage=ClassifiedCoverage(
            short=_round(short.coverage), long=_round(long.coverage)
        ),
        signals=signals,
    )
    return block, worst
