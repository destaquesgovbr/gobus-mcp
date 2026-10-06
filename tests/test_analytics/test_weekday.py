"""Perfil de dia útil, feriados, dias efetivos e nível de volume por fase."""

from datetime import date, timedelta

import pytest

from gobus_mcp.analytics.weekday import (
    DEFAULT_LEVEL_BY_PHASE,
    DEFAULT_WEEKDAY_PROFILE,
    effective_days,
    expected_platform_volume,
    level_by_phase,
    level_phase,
    weekday_normalize,
    weekday_profile,
)
from gobus_mcp.calendario import DateRange

D = date
SYNTHETIC = {0: 190, 1: 190, 2: 190, 3: 190, 4: 190, 5: 50, 6: 23}


def _daily(start: date, end: date, per_weekday=SYNTHETIC, scale: float = 1.0) -> dict:
    out = {}
    day = start
    while day <= end:
        out[day] = round(per_weekday[day.weekday()] * scale)
        day += timedelta(days=1)
    return out


def test_perfil_padrao_de_set_2026():
    assert DEFAULT_WEEKDAY_PROFILE == {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.26, 6: 0.12}


def test_perfil_estimado_do_snapshot():
    today = D(2026, 9, 30)
    profile = weekday_profile(_daily(D(2026, 8, 1), D(2026, 9, 29)), today)
    assert profile.source == "snapshot"
    assert profile.days_used >= 28
    for wd in range(5):
        assert profile.weights[wd] == pytest.approx(1.0, abs=0.01)
    assert profile.weights[5] == pytest.approx(50 / 190, abs=0.005)
    assert profile.weights[6] == pytest.approx(23 / 190, abs=0.005)


def test_perfil_cai_no_padrao_com_poucos_dias():
    today = D(2026, 9, 30)
    profile = weekday_profile(_daily(D(2026, 9, 10), D(2026, 9, 29)), today)  # 20 dias
    assert profile.source == "default"
    assert dict(profile.weights) == DEFAULT_WEEKDAY_PROFILE


def test_perfil_ignora_feriados_e_o_dia_corrente():
    today = D(2026, 10, 13)
    daily = _daily(D(2026, 8, 17), D(2026, 10, 12))
    daily[D(2026, 10, 12)] = 0  # segunda-feira, feriado: fora da estimativa
    daily[D(2026, 9, 7)] = 0  # segunda-feira, Independência
    daily[today] = 10_000  # dia parcial (D) não entra
    profile = weekday_profile(daily, today)
    assert profile.weights[0] == pytest.approx(1.0, abs=0.01)


def test_effective_days_sab_a_seg():
    sat_mon = DateRange(D(2026, 10, 3), D(2026, 10, 5))
    assert effective_days(sat_mon, DEFAULT_WEEKDAY_PROFILE) == pytest.approx(1.38)
    full_week = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert effective_days(full_week, DEFAULT_WEEKDAY_PROFILE) == pytest.approx(5.38)


def test_feriado_conta_como_domingo():
    # 10/10 sáb, 11/10 dom, 12/10 seg (Nossa Senhora Aparecida)
    r = DateRange(D(2026, 10, 10), D(2026, 10, 12))
    assert effective_days(r, DEFAULT_WEEKDAY_PROFILE) == pytest.approx(0.26 + 0.12 + 0.12)


def test_weekday_normalize():
    sat_mon = DateRange(D(2026, 10, 3), D(2026, 10, 5))
    assert weekday_normalize(138, sat_mon, DEFAULT_WEEKDAY_PROFILE) == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("day", "expected"),
    [(D(2026, 7, 3), "normal"), (D(2026, 7, 4), "blackout"), (D(2026, 10, 25), "blackout"),
     (D(2026, 10, 26), "normal"), (D(2026, 11, 30), "normal")],
)  # fmt: skip
def test_level_phase_recuperacao_usa_o_nivel_normal(day, expected):
    assert level_phase(day) == expected


def test_level_by_phase_mede_normal_e_defeso_por_dia_util():
    today = D(2026, 10, 5)
    weights = {wd: v / 190 for wd, v in SYNTHETIC.items()}
    daily = _daily(D(2026, 6, 6), D(2026, 7, 3), scale=1.5)  # pré-defeso: 285/dia útil
    daily |= _daily(D(2026, 7, 4), D(2026, 10, 4))  # defeso: 190/dia útil
    levels = level_by_phase(daily, weights, today=today)
    assert levels["normal"] == pytest.approx(285, rel=0.01)
    assert levels["blackout"] == pytest.approx(190, rel=0.01)


def test_level_by_phase_completa_a_fase_sem_dado_pela_proporcao_padrao():
    today = D(2026, 10, 5)
    weights = {wd: v / 190 for wd, v in SYNTHETIC.items()}
    levels = level_by_phase(_daily(D(2026, 8, 1), D(2026, 10, 4)), weights, today=today)
    assert levels["blackout"] == pytest.approx(190, rel=0.01)
    ratio = DEFAULT_LEVEL_BY_PHASE["normal"] / DEFAULT_LEVEL_BY_PHASE["blackout"]
    assert levels["normal"] == pytest.approx(190 * ratio, rel=0.01)


def test_level_by_phase_sem_snapshot_usa_o_padrao():
    assert level_by_phase({}, DEFAULT_WEEKDAY_PROFILE, today=D(2026, 10, 5)) == dict(
        DEFAULT_LEVEL_BY_PHASE
    )


def test_expected_platform_volume_troca_de_nivel_em_26_10_e_respeita_feriados():
    levels = {"normal": 285.0, "blackout": 190.0}
    w = DEFAULT_WEEKDAY_PROFILE
    assert expected_platform_volume(D(2026, 10, 23), w, levels) == pytest.approx(190.0)  # sex
    assert expected_platform_volume(D(2026, 10, 24), w, levels) == pytest.approx(190 * 0.26)
    assert expected_platform_volume(D(2026, 10, 26), w, levels) == pytest.approx(285.0)  # seg
    assert expected_platform_volume(D(2026, 10, 12), w, levels) == pytest.approx(190 * 0.12)
    assert expected_platform_volume(D(2026, 11, 2), w, levels) == pytest.approx(285 * 0.12)
