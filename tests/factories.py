"""Fábricas de payloads de anomalias e forecast para os testes (dados fictícios)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from gobus_mcp.calendario import DateRange, as_window, calendar_context, rolling_window
from gobus_mcp.domains import DOMAIN_LABELS, DOMAIN_ORDER, Domain
from gobus_mcp.payloads.anomalies import (
    AnomalyReport,
    ClassifiedCoverage,
    DomainSummary,
    EntitiesBlock,
    EntitySignal,
    OwnerInfo,
    ThemesBlock,
    ThemeSignal,
    ThemeWindows,
    Thresholds,
    UpstreamInfo,
)
from gobus_mcp.payloads.common import DataStatus, Notice
from gobus_mcp.payloads.forecast import (
    ForecastReport,
    ForecastTheme,
    ForecastWindow,
    PlatformInfo,
    Projection,
    ProjectionDay,
    WindowRatio,
)

TODAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)


def theme_signal(**overrides) -> ThemeSignal:
    base = dict(
        label="Saúde",
        domain=Domain.HEALTH,
        kind="sustained_spike",
        ratio_short=2.4,
        ratio_long=1.9,
        count_short=42,
        count_long=80,
        share_long=0.12,
        severity=0.52,
        band="watch",
        confidence="medium",
        flags=[],
        daily=None,
    )
    base.update(overrides)
    return ThemeSignal(**base)


def entity_signal(**overrides) -> EntitySignal:
    base = dict(
        entity_id="dgb_programa-mais-medicos",
        name="Programa Mais Médicos",
        type="POLICY",
        domain=Domain.HEALTH,
        kind="concentrated_coverage",
        window_count=12,
        baseline_count=8,
        window_agencies=2,
        distinct_days=4,
        max_day_share=0.42,
        ratio=5.2,
        upstream_volume_ratio=8571.43,
        upstream_computed_at=datetime(2026, 10, 4, 21, 6, tzinfo=UTC),
        owner=OwnerInfo(
            agency_key="saude", agency_name="Ministério da Saúde", method="coverage", share=0.71
        ),
        owner_window_count=9,
        owner_activity_ratio=0.9,
        silence_score=None,
        severity=0.61,
        band="watch",
        confidence="medium",
        explanation="Cobertura 5,2× acima do baseline concentrada em 2 agências.",
        flags=["republishers_excluded"],
        daily=[0, 1, 0, 0, 2, 3, 6],
        owner_daily=[0, 1, 0, 0, 1, 2, 5],
    )
    base.update(overrides)
    return EntitySignal(**base)


def domain_summaries(**by_domain) -> list[DomainSummary]:
    out = []
    for d in DOMAIN_ORDER:
        values = dict(
            domain=d,
            label=DOMAIN_LABELS[d],
            spikes=0,
            silences=0,
            concentrated=0,
            max_severity=0.0,
            spike_level=0.0,
            silence_level=0.0,
            spike_band="normal",
            silence_band="normal",
        )
        values.update(by_domain.get(d.value, {}))
        out.append(DomainSummary(**values))
    return out


def anomaly_report(
    *,
    theme_signals: list[ThemeSignal] | None = None,
    entity_signals: list[EntitySignal] | None = None,
    themes_status: str = "ok",
    themes_note: str | None = None,
    entities_status: str = "ok",
    entities_note: str | None = None,
    data_status: list[DataStatus] | None = None,
    notices: list[Notice] | None = None,
    today: date = TODAY,
    now: datetime = NOW,
    sensitivity: str = "medium",
    domain_filter: str | None = None,
    summary: str = "",
) -> AnomalyReport:
    theme_signals = [theme_signal()] if theme_signals is None else theme_signals
    entity_signals = [entity_signal()] if entity_signals is None else entity_signals
    window = DateRange(today - timedelta(days=7), today - timedelta(days=1))
    baseline = DateRange(today - timedelta(days=35), today - timedelta(days=8))
    return AnomalyReport(
        summary=summary,
        status="ok",
        generated_at=now,
        reference_date=today,
        params={"sensitivity": sensitivity, "domain_filter": domain_filter},
        calendar=calendar_context(today, silenced_agencies=39),
        data_status=data_status or [],
        notices=notices or [],
        thresholds=Thresholds(ratio=1.5, window_agencies=5, silence_ratio=2.0, min_count=5),
        themes=ThemesBlock(
            status=themes_status,
            note=themes_note,
            windows=ThemeWindows(short=rolling_window(3, now), long=rolling_window(7, now)),
            classified_coverage=ClassifiedCoverage(short=0.97, long=0.95),
            signals=theme_signals,
        ),
        entities=EntitiesBlock(
            status=entities_status,
            note=entities_note,
            window=as_window(window, bucket_tz="UTC"),
            baseline=as_window(baseline, baseline_overlaps_blackout=True, bucket_tz="UTC"),
            candidates=len(entity_signals),
            upstream=UpstreamInfo(
                last_run_at=datetime(2026, 10, 4, 21, 6, tzinfo=UTC),
                rows_total=50,
                rows_last_run=50,
                rows_legacy_floor=0,
            ),
            signals=entity_signals,
        ),
        domains=domain_summaries(),
    )


def projection(start: date = TODAY, horizon: int = 21, per_day: float = 5.0) -> Projection:
    daily = [
        ProjectionDay(date=start + timedelta(days=i), expected=per_day) for i in range(horizon)
    ]
    total = per_day * horizon
    return Projection(
        horizon_days=horizon,
        expected_articles=total,
        low=total - 1.96 * total**0.5,
        high=total + 1.96 * total**0.5,
        share_now=0.08,
        share_at_horizon=0.1,
        daily=daily,
    )


def window_ratio(**overrides) -> WindowRatio:
    base = dict(ratio=1.4, window_count=30, baseline_prev_count=80, share=0.1, per_day_rate=0.024)
    base.update(overrides)
    return WindowRatio(**base)


def forecast_theme(label: str = "Saúde", **overrides) -> ForecastTheme:
    base = dict(
        label=label,
        domain=Domain.HEALTH,
        windows={"3d": window_ratio(), "7d": window_ratio(ratio=1.3), "21d": None},
        per_day_rate=0.02,
        weekly_multiplier=1.15,
        momentum="accelerating",
        acceleration=0.01,
        confidence="medium",
        projection=projection(),
        flags=[],
    )
    base.update(overrides)
    return ForecastTheme(**base)


def forecast_window(days: int, baseline: int, weight: float, **overrides) -> ForecastWindow:
    base = dict(
        window_days=days,
        baseline_days=baseline,
        weight=weight,
        effective_weight=weight,
        classified_coverage=0.95,
        status="ok",
        business_days=round(days * 5.38 / 7, 2),
        baseline_overlaps_blackout=True,
    )
    base.update(overrides)
    return ForecastWindow(**base)


def forecast_report(
    *,
    themes: list[ForecastTheme] | None = None,
    horizon: int = 21,
    horizon_requested: int | None = None,
    today: date = TODAY,
    now: datetime = NOW,
    windows: dict | None = None,
    notices: list[Notice] | None = None,
    data_status: list[DataStatus] | None = None,
    status: str = "ok",
    summary: str = "",
) -> ForecastReport:
    return ForecastReport(
        summary=summary,
        status=status,
        generated_at=now,
        reference_date=today,
        params={
            "horizon_days_requested": horizon_requested or horizon,
            "horizon_days": horizon,
            "limit": 5,
        },
        calendar=calendar_context(today),
        data_status=data_status or [],
        notices=notices or [],
        windows=windows
        or {
            "3d": forecast_window(3, 14, 0.5),
            "7d": forecast_window(7, 28, 0.3),
            "21d": forecast_window(21, 84, 0.2),
        },
        platform=PlatformInfo(
            weekday_profile={str(i): v for i, v in enumerate([1, 1, 1, 1, 1, 0.26, 0.12])},
            level_by_phase={"normal": 267.0, "blackout": 177.0},
            profile_source="snapshot",
        ),
        themes=[forecast_theme()] if themes is None else themes,
    )
