"""Legibilidade: escala Flesch (inglesa, textstat) com clamp, faixas únicas e cobertura."""

from datetime import date

import pytest

from gobus_mcp.calendario import DateRange
from gobus_mcp.readability import (
    FLESCH_BANDS,
    FLESCH_SCALE_ID,
    TARGET_INSTITUTIONAL,
    TARGET_SERVICE,
    clamp_flesch,
    describe_flesch,
    effective_window,
    flesch_band,
    last_period_with_data,
    period_range,
    readability_coverage,
    readability_score,
    weighted_metric,
)

D = date


def test_escala_e_metas():
    assert FLESCH_SCALE_ID == "flesch_en_textstat"
    assert (TARGET_SERVICE, TARGET_INSTITUTIONAL) == (50.0, 30.0)


def test_faixas_unicas_0_25_50_75():
    assert [(b.key, b.lower, b.upper) for b in FLESCH_BANDS] == [
        ("very_hard", 0.0, 25.0),
        ("hard", 25.0, 50.0),
        ("medium", 50.0, 75.0),
        ("easy", 75.0, 100.0),
    ]
    assert [b.label for b in FLESCH_BANDS] == ["muito difícil", "difícil", "médio", "fácil"]


@pytest.mark.parametrize(
    ("raw", "value", "clamped"),
    [(-125.1, 0.0, True), (-0.1, 0.0, True), (0.0, 0.0, False), (33.5, 33.5, False),
     (100.0, 100.0, False), (100.2, 100.0, True), (None, None, False)],
)  # fmt: skip
def test_clamp_flesch(raw, value, clamped):
    fv = clamp_flesch(raw)
    assert (fv.raw, fv.value, fv.clamped) == (raw, value, clamped)


@pytest.mark.parametrize(
    ("value", "key"),
    [(0, "very_hard"), (24.99, "very_hard"), (25, "hard"), (49.99, "hard"), (50, "medium"),
     (74.99, "medium"), (75, "easy"), (100, "easy"), (-22.9, "very_hard"), (130, "easy")],
)  # fmt: skip
def test_flesch_band_nas_bordas(value, key):
    assert flesch_band(value).key == key


def test_flesch_band_de_nulo_e_none():
    assert flesch_band(None) is None
    assert flesch_band(clamp_flesch(None)) is None


def test_describe_flesch():
    assert describe_flesch(None) == "indisponível"
    assert describe_flesch(33.5) == "33.5 (difícil)"
    assert describe_flesch(0.0) == "0.0 (muito difícil)"
    assert describe_flesch(-22.9) == "0.0 (muito difícil; valor bruto -22.9)"
    assert describe_flesch(clamp_flesch(101.0)) == "100.0 (fácil; valor bruto 101.0)"


def test_readability_score_linear_ate_a_meta_de_servico():
    assert readability_score(None) is None
    assert readability_score(-10) == 0.0
    assert readability_score(25) == 5.0
    assert readability_score(33.5) == 6.7
    assert readability_score(50) == 10.0
    assert readability_score(80) == 10.0


# ── médias ponderadas ───────────────────────────────────────────────────────


def _row(n, flesch, period="2026-06-01 00:00:00+00", agency="saude"):
    return {
        "agencyKey": agency,
        "period": period,
        "articleCount": n,
        "avgReadabilityFlesch": flesch,
    }


def test_weighted_metric_ignora_nulos_e_reporta_cobertura():
    cov = weighted_metric([_row(100, 30.0), _row(50, None), _row(50, 10.0)], "avgReadabilityFlesch")
    assert cov.value == pytest.approx((100 * 30 + 50 * 10) / 150)
    assert (cov.covered_articles, cov.total_articles) == (150, 200)
    assert (cov.covered_rows, cov.total_rows) == (2, 3)
    assert cov.ratio == pytest.approx(0.75)


def test_weighted_metric_tudo_nulo_e_none_nunca_zero():
    cov = weighted_metric([_row(100, None), _row(20, None)], "avgReadabilityFlesch")
    assert cov.value is None
    assert cov.ratio == 0.0
    assert weighted_metric([], "avgReadabilityFlesch").ratio is None


def test_weighted_metric_com_clamp():
    cov = weighted_metric([_row(10, -20.0), _row(10, 40.0)], "avgReadabilityFlesch", clamp=True)
    assert cov.value == pytest.approx(20.0)
    assert cov.clamped_rows == 1
    raw = weighted_metric([_row(10, -20.0), _row(10, 40.0)], "avgReadabilityFlesch")
    assert raw.value == pytest.approx(10.0) and raw.clamped_rows == 0


# ── períodos, cobertura e janela efetiva ────────────────────────────────────


@pytest.mark.parametrize(
    ("period", "granularity", "expected"),
    [("2026-05-01 00:00:00+00", "MONTH", (D(2026, 5, 1), D(2026, 5, 31))),
     ("2026-02", "MONTH", (D(2026, 2, 1), D(2026, 2, 28))),
     ("2026-09-28 00:00:00+00", "WEEK", (D(2026, 9, 28), D(2026, 10, 4))),
     ("2026-10-04", "DAY", (D(2026, 10, 4), D(2026, 10, 4)))],
)  # fmt: skip
def test_period_range(period, granularity, expected):
    r = period_range(period, granularity)
    assert (r.start, r.end) == expected


def test_last_period_with_data():
    rows = [
        _row(10, 20.0, "2026-05-01 00:00:00+00"),
        _row(10, 14.8, "2026-06-01 00:00:00+00"),
        _row(10, None, "2026-07-01 00:00:00+00"),
        _row(0, None, "2026-08-01 00:00:00+00"),
    ]
    assert last_period_with_data(rows, "avgReadabilityFlesch") == "2026-06-01 00:00:00+00"
    assert last_period_with_data([_row(5, None)], "avgReadabilityFlesch") is None


def test_readability_coverage_por_periodo():
    rows = [
        _row(10, 20.0, "2026-05-01 00:00:00+00", "saude"),
        _row(5, None, "2026-05-01 00:00:00+00", "mec"),
        _row(10, None, "2026-07-01 00:00:00+00", "saude"),
        _row(20, None, "2026-08-01 00:00:00+00", "saude"),
    ]
    cov = readability_coverage(rows)
    assert cov.periods_total == 3
    assert cov.periods_with_data == 1
    assert cov.articles_total == 45
    assert cov.articles_in_periods_with_data == 15
    assert cov.last_period_with_data == "2026-05-01 00:00:00+00"


def test_janela_efetiva_recua_ate_o_ultimo_periodo_com_dado():
    requested = DateRange(D(2026, 7, 7), D(2026, 10, 4))  # 90 dias
    ew = effective_window(requested, "2026-06-01 00:00:00+00", granularity="MONTH")
    assert ew.shifted is True
    assert ew.effective == DateRange(D(2026, 4, 2), D(2026, 6, 30))
    assert ew.effective.days == requested.days
    assert ew.note == "dados até 06/2026"


def test_janela_efetiva_igual_a_pedida_quando_ha_dado_recente():
    requested = DateRange(D(2026, 7, 7), D(2026, 10, 4))
    ew = effective_window(requested, "2026-10-01 00:00:00+00", granularity="MONTH")
    assert ew.shifted is False and ew.effective == requested and ew.note is None


def test_janela_efetiva_sem_dado_algum():
    requested = DateRange(D(2026, 7, 7), D(2026, 10, 4))
    ew = effective_window(requested, None)
    assert ew.effective is None and ew.shifted is False
    assert "sem dados" in ew.note


def test_janela_efetiva_diaria_usa_data_completa_na_nota():
    requested = DateRange(D(2026, 9, 1), D(2026, 9, 30))
    ew = effective_window(requested, "2026-06-29", granularity="DAY")
    assert ew.effective == DateRange(D(2026, 5, 31), D(2026, 6, 29))
    assert ew.note == "dados até 29/06/2026"
