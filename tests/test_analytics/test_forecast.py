"""Forecast: composto renormalizado, momentum, confiança, projeção amortecida e horizonte."""

import math
from datetime import date, timedelta

import pytest

from gobus_mcp.analytics.forecast import (
    MAX_HORIZON,
    MOMENTUM_DELTA,
    PHI,
    WEIGHTS,
    WINDOWS,
    clamp_horizon,
    composite,
    confidence,
    damped_multiplier,
    effective_weights,
    forecast_themes,
    momentum,
    project,
)
from gobus_mcp.analytics.themes import ThemeRange, WindowPair
from gobus_mcp.analytics.weekday import DEFAULT_WEEKDAY_PROFILE
from gobus_mcp.domains import Domain
from gobus_mcp.payloads.forecast import ForecastTheme, ForecastWindow, Projection

D = date
LEVELS = {"normal": 285.0, "blackout": 190.0}
PROFILE = DEFAULT_WEEKDAY_PROFILE


def test_janelas_e_pesos():
    assert WINDOWS == {"3d": (3, 14), "7d": (7, 28), "21d": (21, 84)}
    assert WEIGHTS == {"3d": 0.5, "7d": 0.3, "21d": 0.2}
    assert PHI == 0.9 and MAX_HORIZON == 28


def test_composite_renormaliza_nas_janelas_presentes():
    assert effective_weights(["7d", "21d"]) == pytest.approx({"7d": 0.6, "21d": 0.4})
    assert effective_weights([]) == {}
    rates = {"3d": None, "7d": 0.1, "21d": 0.2}
    assert composite(rates) == pytest.approx(0.6 * 0.1 + 0.4 * 0.2)
    assert composite({"3d": 0.3, "7d": 0.1, "21d": 0.2}) == pytest.approx(0.15 + 0.03 + 0.04)
    assert composite({"3d": None, "7d": None, "21d": None}) is None
    assert composite({}) is None


@pytest.mark.parametrize(
    ("rates", "expected"),
    [
        ({"3d": 0.05, "7d": 0.01, "21d": 0.0}, "accelerating"),
        ({"3d": -0.05, "7d": 0.01, "21d": 0.0}, "decelerating"),
        ({"3d": 0.012, "7d": 0.01, "21d": 0.0}, "stable"),
        ({"3d": None, "7d": 0.05, "21d": 0.0}, "accelerating"),  # fallback 7d − 21d
        ({"3d": None, "7d": None, "21d": 0.04}, "undetermined"),
        ({"3d": 0.04, "7d": None, "21d": None}, "undetermined"),
    ],
)
def test_momentum_nos_quatro_estados(rates, expected):
    state, acc = momentum(rates)
    assert state == expected
    assert (acc is None) == (expected == "undetermined")


def test_momentum_usa_a_diferenca_de_taxas():
    state, acc = momentum({"3d": 0.03, "7d": 0.01})
    assert acc == pytest.approx(0.02)
    assert MOMENTUM_DELTA == pytest.approx(math.log(1.10) / 7)


@pytest.mark.parametrize(
    ("args", "kwargs", "expected"),
    [((3, 40), {"phase": "normal"}, "high"), ((2, 40), {"phase": "normal"}, "medium"),
     ((3, 4), {"phase": "normal"}, "low"), ((1, 40), {"phase": "normal"}, "low"),
     ((3, 40), {"phase": "recovery"}, "medium"), ((2, 40), {"phase": "recovery"}, "low"),
     ((3, 40), {"phase": "normal", "degraded": True}, "low")],
)  # fmt: skip
def test_confianca_com_rebaixamento_na_recuperacao(args, kwargs, expected):
    assert confidence(*args, **kwargs) == expected


@pytest.mark.parametrize(
    ("h", "expected", "warns"), [(21, 21, False), (1, 1, False), (28, 28, False), (0, 1, True),
                                 (-3, 1, True), (40, 28, True)]
)  # fmt: skip
def test_clamp_horizon(h, expected, warns):
    value, warning = clamp_horizon(h)
    assert value == expected
    assert (warning is not None) == warns


def test_multiplicador_amortecido_e_limitado():
    assert damped_multiplier(0.0, 10) == 1.0
    k = 0.05
    assert damped_multiplier(k, 21) == pytest.approx(math.exp(k * 0.9 * (1 - 0.9**21) / 0.1))
    assert damped_multiplier(k, 1) == pytest.approx(math.exp(k * 0.9))
    # amortecido: o ganho de t=20 para t=21 é menor que o de t=1 para t=2
    assert damped_multiplier(k, 21) / damped_multiplier(k, 20) < damped_multiplier(
        k, 2
    ) / damped_multiplier(k, 1)
    assert damped_multiplier(5.0, 28) == 5.0
    assert damped_multiplier(-5.0, 28) == 0.2


def test_projecao_muda_com_o_horizonte():
    p7 = project(0.1, 0.03, start=D(2026, 11, 3), horizon_days=7, weights=PROFILE, levels=LEVELS)
    p21 = project(0.1, 0.03, start=D(2026, 11, 3), horizon_days=21, weights=PROFILE, levels=LEVELS)
    assert isinstance(p7, Projection)
    assert p7.horizon_days == 7 and len(p7.daily) == 7
    assert p21.horizon_days == 21 and len(p21.daily) == 21
    assert p21.expected_articles > p7.expected_articles
    assert p21.share_at_horizon > p7.share_at_horizon > 0.1


def test_projecao_respeita_fim_de_semana_feriado_e_troca_de_nivel_em_26_10():
    p = project(0.1, 0.0, start=D(2026, 10, 20), horizon_days=14, weights=PROFILE, levels=LEVELS)
    by_day = {d.date: d.expected for d in p.daily}
    assert by_day[D(2026, 10, 23)] == pytest.approx(19.0)  # sexta, defeso: 0,1 × 190
    assert by_day[D(2026, 10, 24)] == pytest.approx(0.1 * 190 * 0.26, abs=0.01)  # sábado
    assert by_day[D(2026, 10, 26)] == pytest.approx(28.5)  # segunda, recuperação: nível normal
    assert by_day[D(2026, 11, 2)] == pytest.approx(0.1 * 285 * 0.12, abs=0.01)  # Finados
    assert p.share_now == 0.1 and p.share_at_horizon == pytest.approx(0.1)


def test_intervalo_de_poisson():
    p = project(0.1, 0.0, start=D(2026, 11, 9), horizon_days=7, weights=PROFILE, levels=LEVELS)
    e = p.expected_articles
    assert e == pytest.approx(0.1 * 285 * 5.38, abs=0.1)
    assert p.low == pytest.approx(e - 1.96 * math.sqrt(e), abs=0.1)
    assert p.high == pytest.approx(e + 1.96 * math.sqrt(e), abs=0.1)
    zero = project(0.0, 0.0, start=D(2026, 11, 9), horizon_days=7, weights=PROFILE, levels=LEVELS)
    assert (zero.expected_articles, zero.low, zero.high) == (0.0, 0.0, 0.0)


# ── forecast_themes ─────────────────────────────────────────────────────────


def _pair(key: str, window: dict, including: dict, *, totals=None) -> WindowPair:
    W, B = WINDOWS[key]
    total_w, total_incl = totals or (sum(window.values()), sum(including.values()))
    return WindowPair(ThemeRange(W, window, total_w), ThemeRange(B, including, total_incl))


def _scenario(*, saude_growth: float = 2.0, totals_21=None) -> dict[str, WindowPair]:
    """Saúde cresce (mais forte na janela curta); Educação e Cultura estáveis."""

    def pair(key, w_saude, prev_saude, scale):
        window = {"Saúde": w_saude, "Educação": 10 * scale, "Cultura": 10 * scale}
        including = {
            "Saúde": w_saude + prev_saude,
            "Educação": 10 * scale + 30 * scale,
            "Cultura": 10 * scale + 30 * scale,
        }
        return window, including

    w3, i3 = pair("3d", int(12 * saude_growth), 18, 1)
    w7, i7 = pair("7d", int(20 * saude_growth * 0.8), 60, 2)
    w21, i21 = pair("21d", int(40 * saude_growth * 0.6), 120, 4)
    return {
        "3d": _pair("3d", w3, i3),
        "7d": _pair("7d", w7, i7),
        "21d": _pair("21d", w21, i21, totals=totals_21),
    }


def test_forecast_themes_ordena_por_crescimento_e_projeta():
    today = D(2026, 12, 7)
    windows, themes = forecast_themes(
        _scenario(), today=today, horizon_days=14, limit=5, weights=PROFILE, levels=LEVELS
    )
    assert set(windows) == {"3d", "7d", "21d"}
    assert all(isinstance(w, ForecastWindow) for w in windows.values())
    assert windows["3d"].weight == 0.5 and windows["3d"].effective_weight == pytest.approx(0.5)
    assert windows["7d"].status == "ok" and windows["7d"].classified_coverage == 1.0
    assert windows["7d"].business_days == pytest.approx(5.38)
    assert all(isinstance(t, ForecastTheme) for t in themes)
    top = themes[0]
    assert top.label == "Saúde" and top.domain is Domain.HEALTH
    assert top.per_day_rate > 0 and top.weekly_multiplier == pytest.approx(
        math.exp(7 * top.per_day_rate), rel=1e-3
    )
    assert top.momentum == "accelerating"
    assert top.windows["3d"].ratio > top.windows["21d"].ratio > 1
    assert top.projection is not None and top.projection.horizon_days == 14
    assert top.projection.daily[0].date == today
    assert top.confidence == "high"
    assert [t.label for t in themes] == sorted(
        (t.label for t in themes), key=lambda lb: -next(x.per_day_rate for x in themes
                                                        if x.label == lb)
    )  # fmt: skip


def test_horizonte_7_e_21_dao_saidas_diferentes():
    pairs = _scenario()
    kwargs = dict(today=D(2026, 12, 7), limit=5, weights=PROFILE, levels=LEVELS)
    _, t7 = forecast_themes(pairs, horizon_days=7, **kwargs)
    _, t21 = forecast_themes(pairs, horizon_days=21, **kwargs)
    assert t7[0].projection.expected_articles != t21[0].projection.expected_articles
    assert len(t7[0].projection.daily) == 7 and len(t21[0].projection.daily) == 21


def test_janela_sem_cobertura_e_excluida_e_os_pesos_renormalizam():
    pairs = _scenario(totals_21=(10_000, 40_000))  # 21d com ~2% classificado
    windows, themes = forecast_themes(
        pairs, today=D(2026, 12, 7), horizon_days=7, limit=5, weights=PROFILE, levels=LEVELS
    )
    assert windows["21d"].status == "unavailable" and windows["21d"].effective_weight == 0.0
    assert windows["3d"].effective_weight == pytest.approx(0.625)
    assert windows["7d"].effective_weight == pytest.approx(0.375)
    assert themes[0].windows["21d"] is None
    assert themes[0].confidence != "high"  # só 2 janelas


def test_estado_de_05_10_so_a_janela_de_21_dias_degradada():
    # 3d e 7d sem tema desde 26/09; 21d com ~60% classificado
    pairs = {
        "3d": _pair("3d", {}, {"Saúde": 30, "Educação": 30}, totals=(400, 1800)),
        "7d": _pair("7d", {}, {"Saúde": 80, "Educação": 80}, totals=(1000, 3800)),
        "21d": _pair(
            "21d",
            {"Saúde": 500, "Educação": 300},
            {"Saúde": 2000, "Educação": 1500},
            totals=(1300, 4000),
        ),
    }
    windows, themes = forecast_themes(
        pairs, today=D(2026, 10, 5), horizon_days=21, limit=5, weights=PROFILE, levels=LEVELS
    )
    assert windows["3d"].status == windows["7d"].status == "unavailable"
    assert windows["21d"].status == "degraded"
    assert windows["21d"].effective_weight == pytest.approx(1.0)
    for t in themes:
        assert t.windows["3d"] is None and t.windows["7d"] is None
        assert t.momentum == "undetermined" and t.acceleration is None
        assert t.confidence == "low"
        assert {"degraded_coverage", "classifier_changed", "horizon_crosses_blackout_end"} <= set(
            t.flags
        )


def test_tudo_indisponivel_nao_projeta():
    pairs = {k: _pair(k, {}, {}, totals=(100, 400)) for k in WINDOWS}
    windows, themes = forecast_themes(
        pairs, today=D(2026, 10, 5), horizon_days=21, limit=5, weights=PROFILE, levels=LEVELS
    )
    assert themes == []
    assert all(w.effective_weight == 0.0 for w in windows.values())


def test_janela_ausente_conta_como_indisponivel():
    pairs = _scenario()
    del pairs["3d"]
    windows, themes = forecast_themes(
        pairs, today=D(2026, 12, 7), horizon_days=7, limit=2, weights=PROFILE, levels=LEVELS
    )
    assert windows["3d"].status == "unavailable" and windows["3d"].classified_coverage is None
    assert len(themes) == 2


def test_recuperacao_rebaixa_e_marca():
    _, themes = forecast_themes(
        _scenario(), today=D(2026, 11, 10), horizon_days=7, limit=5, weights=PROFILE, levels=LEVELS
    )
    top = themes[0]
    assert "recovery" in top.flags
    assert top.confidence == "medium"
    # a projeção começa em D
    assert top.projection.daily[0].date == D(2026, 11, 10)
    assert top.projection.daily[-1].date == D(2026, 11, 10) + timedelta(days=6)
