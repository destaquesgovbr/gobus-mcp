"""Snapshot de atividade das agências: ``agencyAnalytics(todas, DAY)`` com cache de 6 h."""

import asyncio
from datetime import date, timedelta

import pytest

from gobus_mcp.agency_activity import (
    ACTIVITY_TIMEOUT,
    ACTIVITY_TTL,
    AgencyActivityService,
    activity_ratio,
    activity_status,
    snapshot_period,
    summarize_activity,
)
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import DateRange
from tests.conftest import CATALOG_AGENCIES, route_catalog

D = date
TODAY = D(2026, 10, 5)


def _rows(agency: str, counts: dict[date, int], name: str | None = None) -> list[dict]:
    return [
        {
            "period": day.isoformat(),
            "agencyKey": agency,
            "agencyName": name or agency.upper(),
            "articleCount": n,
        }
        for day, n in sorted(counts.items())
    ]


def _span(start: date, end: date, value: int) -> dict[date, int]:
    return {start + timedelta(days=i): value for i in range((end - start).days + 1)}


# ── período do snapshot ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        # defeso e recuperação: D−90 mais o pré-defeso (28 dias antes de 04/07)
        (D(2026, 10, 5), (D(2026, 6, 6), D(2026, 10, 4))),
        (D(2026, 10, 30), (D(2026, 6, 6), D(2026, 10, 29))),
        (D(2026, 11, 29), (D(2026, 6, 6), D(2026, 11, 28))),
        # fora: só D−90 (não cresce sem limite depois do defeso)
        (D(2026, 11, 30), (D(2026, 9, 1), D(2026, 11, 29))),
        (D(2026, 7, 3), (D(2026, 4, 4), D(2026, 7, 2))),
    ],
)
def test_snapshot_period(today, expected):
    r = snapshot_period(today)
    assert (r.start, r.end) == expected


# ── summarize_activity ──────────────────────────────────────────────────────


def test_series_preenchidas_last_active_e_dedup():
    period = DateRange(D(2026, 9, 1), D(2026, 10, 4))
    rows = _rows("saude", {D(2026, 9, 2): 5, D(2026, 10, 3): 2}, "Ministério da Saúde")
    rows.append(dict(rows[0]))  # duplicata (dois nomes no CTE): não soma
    snap = summarize_activity(rows, today=TODAY, period=period)
    saude = snap.by_agency["saude"]
    assert saude.name == "Ministério da Saúde"
    assert len(saude.series) == period.days
    assert saude.series[D(2026, 9, 2)] == 5 and saude.series[D(2026, 9, 3)] == 0
    assert saude.last_active == D(2026, 10, 3)
    assert snap.platform_daily[D(2026, 9, 2)] == 5
    assert (snap.start, snap.end) == (period.start, period.end)


def test_ignora_o_dia_corrente_e_linhas_fora_do_periodo():
    period = DateRange(D(2026, 9, 1), D(2026, 10, 4))
    rows = _rows("mec", {D(2026, 10, 5): 50, D(2026, 8, 1): 9, D(2026, 9, 10): 1})
    snap = summarize_activity(rows, today=TODAY, period=period)
    assert TODAY not in snap.platform_daily
    assert sum(snap.platform_daily.values()) == 1


def test_silenciada_com_14_dias_zerados_ate_d_menos_1():
    period = DateRange(D(2026, 8, 1), D(2026, 10, 4))
    rows = [
        *_rows("secom", _span(D(2026, 8, 1), D(2026, 9, 20), 3) | _span(D(2026, 9, 21), D(2026, 10, 4), 0)),
        *_rows("pf", _span(D(2026, 8, 1), D(2026, 9, 21), 3) | _span(D(2026, 9, 22), D(2026, 10, 4), 0)),
        *_rows("dormente", _span(D(2026, 8, 1), D(2026, 10, 4), 0)),
    ]  # fmt: skip
    snap = summarize_activity(rows, today=TODAY, period=period)
    assert snap.silenced == frozenset({"secom"})  # 14 dias; pf tem 13
    assert snap.by_agency["secom"].silent_since == D(2026, 9, 21)
    assert snap.by_agency["pf"].silent_since is None
    # nunca publicou no período: não é "silenciada" (não havia o que calar)
    assert snap.by_agency["dormente"].last_active is None
    assert "dormente" not in snap.silenced


def test_retomada_depois_de_silencio_longo():
    today = D(2026, 10, 30)
    period = snapshot_period(today)
    pre = _span(period.start, D(2026, 7, 3), 6)
    blackout = _span(D(2026, 7, 4), D(2026, 10, 25), 0)
    back = _span(D(2026, 10, 26), D(2026, 10, 29), 4)
    old_pause = (
        _span(period.start, D(2026, 7, 10), 2)
        | _span(D(2026, 7, 11), D(2026, 7, 31), 0)
        | _span(D(2026, 8, 1), D(2026, 10, 29), 2)
    )
    rows = [*_rows("secom", pre | blackout | back), *_rows("mec", old_pause)]
    snap = summarize_activity(rows, today=today, period=period)
    secom = snap.by_agency["secom"]
    assert secom.resumed_on == D(2026, 10, 26)
    assert secom.silent_since is None
    assert "secom" in snap.resumed and "secom" not in snap.silenced
    # pausa antiga (retomou em 01/08, há 90 dias): não conta como retomada agora
    assert snap.by_agency["mec"].resumed_on == D(2026, 8, 1)
    assert "mec" not in snap.resumed
    # média diária antes do defeso (para comparar a retomada)
    assert secom.pre_daily_mean == pytest.approx(6.0)


def test_pre_daily_mean_so_existe_no_defeso_e_na_recuperacao():
    period = snapshot_period(D(2026, 12, 15))
    rows = _rows("saude", _span(period.start, period.end, 3))
    snap = summarize_activity(rows, today=D(2026, 12, 15), period=period)
    assert snap.by_agency["saude"].pre_daily_mean is None


def test_activity_ratio():
    period = DateRange(D(2026, 8, 1), D(2026, 10, 4))
    counts = _span(D(2026, 8, 1), D(2026, 9, 27), 4) | _span(D(2026, 9, 28), D(2026, 10, 4), 2)
    snap = summarize_activity(_rows("saude", counts), today=TODAY, period=period)
    saude = snap.by_agency["saude"]
    window = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    baseline = DateRange(D(2026, 8, 31), D(2026, 9, 27))
    assert activity_ratio(saude, window, baseline) == pytest.approx(0.5)
    # baseline fora do snapshot ou zerado: sem razão
    assert activity_ratio(saude, window, DateRange(D(2026, 1, 1), D(2026, 1, 28))) is None
    zero = summarize_activity(_rows("x", _span(D(2026, 8, 1), D(2026, 10, 4), 0)), today=TODAY,
                              period=period).by_agency["x"]  # fmt: skip
    assert activity_ratio(zero, window, baseline) is None


def test_activity_status():
    period = DateRange(D(2026, 9, 1), D(2026, 10, 4))
    snap = summarize_activity(_rows("saude", _span(period.start, period.end, 1)), today=TODAY,
                              period=period)  # fmt: skip
    ok = activity_status(snap)
    assert ok.key == "agency_activity" and ok.status == "ok"
    assert ok.metric["agencies"] == 1 and ok.metric["silenced"] == 0
    down = activity_status(None, error="timeout")
    assert down.status == "unavailable" and "timeout" in down.message


# ── serviço com cache ───────────────────────────────────────────────────────


def _route_snapshot(fake_client, rows=None):
    calls = []

    async def respond(variables):
        calls.append(variables)
        await asyncio.sleep(0)
        return {"agencyAnalytics": rows if rows is not None else []}

    fake_client.route("AgencyActivitySnapshot", respond)
    return calls


async def test_snapshot_consulta_todas_as_agencias_do_catalogo_com_dateto_inclusivo(fake_client):
    route_catalog(fake_client)
    calls = _route_snapshot(fake_client, _rows("saude", {D(2026, 10, 1): 3}))
    service = AgencyActivityService(fake_client, AgencyCatalog(fake_client))
    snap = await service.snapshot(TODAY)
    (variables,) = calls
    assert variables["agencies"] == sorted(code for code, _, _ in CATALOG_AGENCIES)
    # DAY: dateTo inclusivo → D−1
    assert (variables["dateFrom"], variables["dateTo"]) == ("2026-06-06", "2026-10-04")
    assert snap.by_agency["saude"].last_active == D(2026, 10, 1)
    timeouts = [
        c.kwargs.get("timeout")
        for c in fake_client.execute.call_args_list
        if "AgencyActivitySnapshot" in c.args[0]
    ]
    assert timeouts == [ACTIVITY_TIMEOUT]


async def test_snapshot_cache_de_6h_single_flight(fake_client):
    route_catalog(fake_client)
    calls = _route_snapshot(fake_client)
    service = AgencyActivityService(fake_client, AgencyCatalog(fake_client))
    first, second = await asyncio.gather(service.snapshot(TODAY), service.snapshot(TODAY))
    assert first is second
    await service.snapshot(TODAY)
    assert len(calls) == 1
    await service.snapshot(TODAY + timedelta(days=1))  # outro D: outra chave
    assert len(calls) == 2
    assert ACTIVITY_TTL == 6 * 3600


async def test_snapshot_expira_pelo_ttl(fake_client):
    clock = [0.0]
    route_catalog(fake_client)
    calls = _route_snapshot(fake_client)
    service = AgencyActivityService(
        fake_client, AgencyCatalog(fake_client), cache=TTLCache(clock=lambda: clock[0])
    )
    await service.snapshot(TODAY)
    clock[0] = ACTIVITY_TTL + 1
    await service.snapshot(TODAY)
    assert len(calls) == 2


async def test_falha_do_snapshot_levanta_e_nao_e_cacheada(fake_client):
    route_catalog(fake_client)
    fake_client.route("AgencyActivitySnapshot", RuntimeError("timeout"))
    service = AgencyActivityService(fake_client, AgencyCatalog(fake_client))
    with pytest.raises(RuntimeError):
        await service.snapshot(TODAY)
    _route_snapshot(fake_client)
    snap = await service.snapshot(TODAY)
    assert snap.by_agency == {}
