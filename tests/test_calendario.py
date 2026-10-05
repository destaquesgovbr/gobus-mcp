"""Calendário: BRT, defeso eleitoral 2026, recuperação, feriados e janelas.

As datas de fronteira (04/07, 25/10, 29/11, 30/11) são as mesmas fixadas nos testes do
data-platform (D2 do trend_detection) — contrato entre os repos.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from gobus_mcp.calendario import (
    BLACKOUTS,
    BRT,
    HOLIDAYS,
    BlackoutPeriod,
    DateRange,
    as_window,
    baseline_for,
    brt_bounds,
    calendar_context,
    classifier_changed_within,
    closed_window,
    effective_weekday,
    is_holiday,
    now_brt,
    phase,
    reference_date,
    utc_day_bounds,
)
from gobus_mcp.payloads.common import CalendarContext, Window

D = date


def test_brt_e_o_fuso_de_sao_paulo():
    assert BRT.key == "America/Sao_Paulo"
    assert datetime(2026, 10, 5, 12, tzinfo=BRT).utcoffset() == timedelta(hours=-3)
    assert now_brt().tzinfo is BRT


def test_defeso_2026_e_recuperacao_ate_29_11():
    (period,) = BLACKOUTS
    assert (period.start, period.end) == (D(2026, 7, 4), D(2026, 10, 25))
    # fim + janela 7 + baseline 28 (integration.md I3)
    assert period.recovery_until == D(2026, 11, 29)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (D(2026, 1, 1), "normal"),
        (D(2026, 7, 3), "normal"),
        (D(2026, 7, 4), "blackout"),
        (D(2026, 10, 5), "blackout"),
        (D(2026, 10, 25), "blackout"),
        (D(2026, 10, 26), "recovery"),
        (D(2026, 11, 29), "recovery"),
        (D(2026, 11, 30), "normal"),
    ],
)
def test_phase_nas_fronteiras(day, expected):
    assert phase(day) == expected


def test_phase_com_periodos_injetados():
    periods = (BlackoutPeriod(D(2030, 1, 10), D(2030, 1, 20), "Teste"),)
    assert phase(D(2030, 1, 9), periods) == "normal"
    assert phase(D(2030, 1, 10), periods) == "blackout"
    assert phase(D(2030, 1, 21), periods) == "recovery"
    assert phase(D(2030, 2, 24), periods) == "recovery"  # 20/01 + 35
    assert phase(D(2030, 2, 25), periods) == "normal"
    assert phase(D(2026, 10, 5), periods) == "normal"


@pytest.mark.parametrize(
    "day", [D(2026, 10, 12), D(2026, 11, 2), D(2026, 11, 15), D(2026, 11, 20), D(2026, 12, 25)]
)
def test_feriados_federais_do_horizonte(day):
    assert day in HOLIDAYS
    assert is_holiday(day)
    assert effective_weekday(day) == 6  # feriado conta como domingo


def test_dia_util_comum_nao_e_feriado():
    assert not is_holiday(D(2026, 10, 13))
    assert effective_weekday(D(2026, 10, 13)) == 1  # terça
    assert effective_weekday(D(2026, 10, 12), holidays=frozenset()) == 0  # segunda


def test_reference_date_e_o_dia_em_brt():
    # 02:00 UTC de 06/10 = 23:00 BRT de 05/10
    assert reference_date(datetime(2026, 10, 6, 2, 0, tzinfo=UTC)) == D(2026, 10, 5)
    assert reference_date(datetime(2026, 10, 6, 3, 0, tzinfo=UTC)) == D(2026, 10, 6)
    with pytest.raises(ValueError):
        reference_date(datetime(2026, 10, 6, 2, 0))  # sem fuso


def test_date_range_inclusivo():
    r = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert r.days == 7
    assert D(2026, 10, 4) in r and D(2026, 10, 5) not in r
    assert list(r)[0] == D(2026, 9, 28) and len(list(r)) == 7
    with pytest.raises(ValueError):
        DateRange(D(2026, 10, 4), D(2026, 9, 28))


def test_closed_window_termina_em_d_menos_1():
    assert closed_window(7, D(2026, 10, 5)) == DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert closed_window(1, D(2026, 10, 5)) == DateRange(D(2026, 10, 4), D(2026, 10, 4))


def test_brt_bounds_com_offset_e_fim_exclusivo():
    r = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert brt_bounds(r) == ("2026-09-28T00:00:00-03:00", "2026-10-05T00:00:00-03:00")


def test_utc_day_bounds_fim_exclusivo_ou_inclusivo():
    r = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert utc_day_bounds(r) == ("2026-09-28", "2026-10-05")  # entityCoverage
    assert utc_day_bounds(r, end_exclusive=False) == ("2026-09-28", "2026-10-04")  # DAY


def test_as_window_fechada_em_brt():
    w = as_window(DateRange(D(2026, 9, 28), D(2026, 10, 4)), baseline_overlaps_blackout=True)
    assert isinstance(w, Window)
    assert w.kind == "closed" and w.bucket_tz == "America/Sao_Paulo" and w.days == 7
    assert w.start == datetime(2026, 9, 28, 3, tzinfo=UTC)
    assert w.end == datetime(2026, 10, 5, 3, tzinfo=UTC)
    assert w.baseline_overlaps_blackout is True


def test_calendar_context_no_defeso():
    ctx = calendar_context(D(2026, 10, 5), silenced_agencies=39)
    assert isinstance(ctx, CalendarContext)
    assert ctx.phase == "blackout"
    assert ctx.label == "Defeso eleitoral 2026"
    assert (ctx.blackout_start, ctx.blackout_end) == (D(2026, 7, 4), D(2026, 10, 25))
    assert ctx.recovery_until == D(2026, 11, 29)
    assert ctx.days_to_end == 20
    assert ctx.silenced_agencies == 39 and ctx.resumed_agencies is None


def test_calendar_context_na_recuperacao_e_depois():
    ctx = calendar_context(D(2026, 10, 30))
    assert ctx.phase == "recovery"
    assert "Recuperação" in ctx.label
    assert ctx.days_to_end == 30  # até 29/11
    assert ctx.blackout_end == D(2026, 10, 25)

    after = calendar_context(D(2026, 11, 30))
    assert after.phase == "normal"
    assert after.label is None and after.blackout_start is None and after.days_to_end is None


def test_baseline_rolante_fora_do_defeso():
    window = closed_window(7, D(2026, 6, 20))  # 13/06..19/06
    base = baseline_for(window, 28)
    assert base.range == DateRange(D(2026, 5, 16), D(2026, 6, 12))
    assert base.overlaps_blackout is False and base.pre_blackout is False


def test_baseline_no_defeso_e_rolante_e_marca_sobreposicao():
    window = closed_window(7, D(2026, 10, 5))  # 28/09..04/10
    base = baseline_for(window, 28)
    assert base.range == DateRange(D(2026, 8, 31), D(2026, 9, 27))
    assert base.overlaps_blackout is True


@pytest.mark.parametrize("today", [D(2026, 10, 26), D(2026, 11, 10), D(2026, 11, 29)])
def test_baseline_na_recuperacao_e_o_pre_defeso(today):
    base = baseline_for(closed_window(7, today), 28)
    # mesmo intervalo do D2 upstream: [2026-06-06, 2026-07-04)
    assert base.range == DateRange(D(2026, 6, 6), D(2026, 7, 3))
    assert base.pre_blackout is True and base.overlaps_blackout is False


def test_baseline_volta_a_rolar_em_30_11():
    base = baseline_for(closed_window(7, D(2026, 11, 30)), 28)  # janela 23/11..29/11
    assert base.range == DateRange(D(2026, 10, 26), D(2026, 11, 22))
    assert base.pre_blackout is False and base.overlaps_blackout is False


def test_baseline_pre_defeso_respeita_baseline_days():
    base = baseline_for(closed_window(21, D(2026, 11, 1)), 84)
    assert base.range == DateRange(D(2026, 4, 11), D(2026, 7, 3))


def test_classifier_changed_within():
    r = DateRange(D(2026, 9, 1), D(2026, 10, 4))
    assert classifier_changed_within(r, D(2026, 9, 26)) is True
    assert classifier_changed_within(r, D(2026, 9, 1)) is False  # tudo depois do corte
    assert classifier_changed_within(r, D(2026, 10, 5)) is False  # corte no futuro
    assert classifier_changed_within(r, None) is False
