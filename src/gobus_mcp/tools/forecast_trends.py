"""``gobus_forecast_trends``: projeção de temas por share-of-voice, ciente do calendário (G2, F3).

Fluxo de ``build_forecast_report`` (I/O aqui; a análise fica em ``analytics/forecast``):

1. Em paralelo: ``ThemeRangeCounts`` nos ranges 3, 14, 7, 28, 21 e 84 (``theme_data``) e o
   snapshot de atividade das agências (perfil de dia útil e nível por fase).
2. Janelas 3d/7d/21d (cada uma dentro de 14/28/84 dias): share-of-voice sem sobreposição e
   taxa log por dia. Cobertura de classificação < 50% tira a janela do composto (pesos
   renormalizados); entre 50% e 80% a janela fica degradada (confiança ``low``).
3. Composto, momentum, confiança (−1 nível na recuperação) e projeção amortecida
   (φ = 0,9) com ``horizon_days`` efetivo (1–28), perfil de dia útil e feriados, nível
   da fase do calendário em cada dia e intervalo de Poisson.
4. ``ForecastReport`` → Markdown (``summary``) → corte de orçamento do payload (20 KB).

Falha do snapshot de atividade: perfil semanal e níveis padrão (``profile_source:
"default"``), com aviso; a tool não cai. Orçamento: ≤ 2 s com cache quente.
"""

from __future__ import annotations

import asyncio

from gobus_mcp.agency_activity import AgencyActivityService, activity_status
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.analytics.forecast import (
    DEFAULT_HORIZON,
    FORECAST_RANGE_DAYS,
    WINDOWS,
    clamp_horizon,
    forecast_themes,
)
from gobus_mcp.analytics.render import render_forecast_markdown
from gobus_mcp.analytics.weekday import (
    DEFAULT_LEVEL_BY_PHASE,
    DEFAULT_WEEKDAY_PROFILE,
    level_by_phase,
    weekday_profile,
)
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import (
    calendar_context,
    calendar_notices,
    now_brt,
    reference_date,
    rolling_range,
)
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import failed_status, notices_for, worst_data_status
from gobus_mcp.payloads.common import DataStatus, ReportStatus
from gobus_mcp.payloads.forecast import (
    MAX_THEMES,
    ForecastReport,
    ForecastWindow,
    PlatformInfo,
    fit_forecast_budget,
)
from gobus_mcp.theme_data import ThemeRangeFetch, fetch_theme_ranges

DEFAULT_LIMIT = 5


def _report_status(
    windows: dict[str, ForecastWindow], themes: list, statuses: list[DataStatus]
) -> ReportStatus:
    if all(w.status == "unavailable" for w in windows.values()):
        return "unavailable"
    if any(w.status != "ok" for w in windows.values()) or any(s.status != "ok" for s in statuses):
        return "partial"
    if not themes:
        return "empty"
    return "ok"


async def build_forecast_report(
    client: GobusGraphQLClient,
    *,
    horizon_days: int = DEFAULT_HORIZON,
    limit: int = DEFAULT_LIMIT,
    catalog: AgencyCatalog | None = None,
    activity: AgencyActivityService | None = None,
    now=None,
    cache: TTLCache | None = None,
) -> ForecastReport:
    """``ForecastReport`` completo (``summary`` = Markdown). ``horizon_days`` fora de 1–28 é
    ajustado (com aviso no Markdown); ``limit`` fica entre 1 e 10."""
    now = now or now_brt()
    today = reference_date(now)
    catalog = catalog or AgencyCatalog(client)
    activity = activity or AgencyActivityService(client, catalog)
    horizon, _ = clamp_horizon(horizon_days)
    effective_limit = min(max(int(limit), 1), MAX_THEMES)

    fetch_r, snapshot_r = await asyncio.gather(
        fetch_theme_ranges(client, FORECAST_RANGE_DAYS, now=now, cache=cache),
        activity.snapshot(today),
        return_exceptions=True,
    )
    fetch = (
        ThemeRangeFetch(
            ranges={},
            errors=dict.fromkeys(FORECAST_RANGE_DAYS, str(fetch_r) or type(fetch_r).__name__),
            as_of=now,
        )
        if isinstance(fetch_r, BaseException)
        else fetch_r
    )
    pairs = {
        key: pair
        for key, (window_days, including_days) in WINDOWS.items()
        if (pair := fetch.pair(window_days, including_days)) is not None
    }

    snapshot = None if isinstance(snapshot_r, BaseException) else snapshot_r
    activity_data = activity_status(
        snapshot, error=str(snapshot_r) if isinstance(snapshot_r, BaseException) else None
    )
    if snapshot is not None:
        profile = weekday_profile(snapshot.platform_daily, today)
        weights, source = dict(profile.weights), profile.source
        levels = level_by_phase(snapshot.platform_daily, weights, today=today)
    else:
        weights, source = dict(DEFAULT_WEEKDAY_PROFILE), "default"
        levels = dict(DEFAULT_LEVEL_BY_PHASE)

    windows, themes = forecast_themes(
        pairs,
        today=today,
        horizon_days=horizon,
        limit=effective_limit,
        weights=weights,
        levels=levels,
    )

    theme_statuses = [s for pair in pairs.values() for s in pair.statuses()]
    if fetch.errors:
        theme_statuses.append(failed_status("themes", fetch.error_text()))
    theme_status = worst_data_status(theme_statuses)
    statuses = [theme_status, activity_data]
    notices = calendar_notices(
        today,
        baselines=[rolling_range(including, today) for _, including in WINDOWS.values()],
        silenced_agencies=len(snapshot.silenced) if snapshot else None,
    )
    notices += notices_for(statuses)

    report = ForecastReport(
        summary="",
        status=_report_status(windows, themes, statuses),
        generated_at=now,
        reference_date=today,
        params={
            "horizon_days_requested": horizon_days,
            "horizon_days": horizon,
            "limit": effective_limit,
        },
        calendar=calendar_context(
            today,
            silenced_agencies=len(snapshot.silenced) if snapshot else None,
            resumed_agencies=len(snapshot.resumed) if snapshot else None,
        ),
        data_status=statuses,
        notices=notices,
        windows=windows,
        platform=PlatformInfo(
            weekday_profile={str(day): round(w, 3) for day, w in sorted(weights.items())},
            level_by_phase=dict(levels),
            profile_source=source,
        ),
        themes=themes,
    )
    report = report.model_copy(update={"summary": render_forecast_markdown(report)})
    return fit_forecast_budget(report)


async def forecast_trends(
    client: GobusGraphQLClient,
    horizon_days: int = DEFAULT_HORIZON,
    limit: int = DEFAULT_LIMIT,
    *,
    catalog: AgencyCatalog | None = None,
    activity: AgencyActivityService | None = None,
    now=None,
    cache: TTLCache | None = None,
) -> str:
    """Markdown do forecast de tendências (o ``summary`` do ``ForecastReport``)."""
    report = await build_forecast_report(
        client,
        horizon_days=horizon_days,
        limit=limit,
        catalog=catalog,
        activity=activity,
        now=now,
        cache=cache,
    )
    return report.summary
