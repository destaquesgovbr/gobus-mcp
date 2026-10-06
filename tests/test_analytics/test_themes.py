"""Temas: sensibilidade, cobertura de classificação e picos/quedas sustentados (SoV)."""

from datetime import UTC, date, datetime

import pytest

from gobus_mcp.analytics.ratios import share_of_voice_ratio, theme_stats
from gobus_mcp.analytics.themes import (
    LONG_WINDOW,
    SENSITIVITY,
    SHORT_WINDOW,
    ThemeRange,
    WindowPair,
    build_themes_block,
    classified_coverage,
    classify_sustained,
    pair_status,
    parse_sensitivity,
    theme_confidence,
)
from gobus_mcp.domains import Domain
from gobus_mcp.payloads.anomalies import ThemesBlock

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)
MEDIUM = SENSITIVITY["medium"]


def _pair(window: dict, including: dict, days: tuple[int, int], *, totals=None) -> WindowPair:
    W, B = days
    total_w, total_incl = totals or (sum(window.values()), sum(including.values()))
    return WindowPair(
        window=ThemeRange(W, window, total_w), including=ThemeRange(B, including, total_incl)
    )


# Cenário com 3 temas: Saúde dispara nas duas janelas; Educação cai nas duas.
SHORT = _pair(
    {"Saúde": 30, "Educação": 4, "Cultura": 26},
    {"Saúde": 60, "Educação": 124, "Cultura": 116},
    SHORT_WINDOW,
)
LONG = _pair(
    {"Saúde": 50, "Educação": 10, "Cultura": 80},
    {"Saúde": 80, "Educação": 160, "Cultura": 200},
    LONG_WINDOW,
)


def test_tabela_de_sensibilidade():
    assert SHORT_WINDOW == (3, 21) and LONG_WINDOW == (7, 28)
    assert set(SENSITIVITY) == {"high", "medium", "low"}
    high, medium, low = SENSITIVITY["high"], SENSITIVITY["medium"], SENSITIVITY["low"]
    assert (medium.ratio, medium.window_agencies, medium.silence_ratio, medium.min_count) == (
        1.5,
        5,
        2.0,
        5,
    )
    assert high.ratio < medium.ratio < low.ratio
    assert high.min_count < medium.min_count < low.min_count
    t = medium.thresholds()
    assert (t.ratio, t.window_agencies, t.silence_ratio, t.min_count) == (1.5, 5, 2.0, 5)


def test_parse_sensitivity():
    assert parse_sensitivity("HIGH ") == ("high", SENSITIVITY["high"])
    assert parse_sensitivity("") == ("medium", MEDIUM)
    with pytest.raises(ValueError) as exc:
        parse_sensitivity("altissima")
    assert "high" in str(exc.value) and "medium" in str(exc.value) and "low" in str(exc.value)


def test_theme_range_da_resposta_da_api():
    data = {
        "topThemes": [{"label": "Saúde", "count": 10}, {"label": "Educação", "count": None}],
        "analyticsKpis": {"total": 40},
    }
    r = ThemeRange.from_response(7, data)
    assert r.days == 7 and r.counts == {"Saúde": 10, "Educação": 0} and r.total == 40
    assert r.classified == 10
    empty = ThemeRange.from_response(3, {})
    assert empty.counts == {} and empty.total == 0


def test_classified_coverage():
    assert classified_coverage(0, 0) is None
    assert classified_coverage(200, 100) == pytest.approx(0.5)
    assert classified_coverage(100, 120) == 1.0  # nunca acima de 100%


def test_pair_status_olha_a_janela_e_o_baseline_anterior():
    assert pair_status(SHORT) == "ok"
    window_dead = _pair({"Saúde": 0}, {"Saúde": 300}, SHORT_WINDOW, totals=(100, 400))
    assert pair_status(window_dead) == "unavailable"
    # janela classificada, mas o baseline anterior não (logo depois do conserto do F0a)
    prev_dead = _pair({"Saúde": 100}, {"Saúde": 110}, SHORT_WINDOW, totals=(100, 1000))
    assert pair_status(prev_dead) == "unavailable"
    partial = _pair({"Saúde": 65}, {"Saúde": 260}, SHORT_WINDOW, totals=(100, 400))
    assert pair_status(partial) == "degraded"


def test_pico_sustentado_exige_as_duas_janelas():
    signals = classify_sustained(SHORT.stats(), LONG.stats(), sens=MEDIUM, k_themes=3)
    spikes = {s.label: s for s in signals if s.kind == "sustained_spike"}
    assert set(spikes) == {"Saúde"}
    s = spikes["Saúde"]
    k = 3
    expected_short = share_of_voice_ratio(SHORT.stats()["Saúde"], k_themes=k)
    expected_long = share_of_voice_ratio(LONG.stats()["Saúde"], k_themes=k)
    assert s.ratio_short == pytest.approx(expected_short, abs=1e-3)
    assert s.ratio_long == pytest.approx(expected_long, abs=1e-3)
    assert (s.count_short, s.count_long) == (30, 50)
    assert s.share_long == pytest.approx(50 / 140, abs=1e-3)
    assert s.domain is Domain.HEALTH
    assert s.daily is None
    assert 1 / 3 <= s.severity <= 1 and s.band in {"watch", "alert"}


def test_so_a_janela_curta_nao_basta():
    long_flat = _pair(
        {"Saúde": 20, "Educação": 40, "Cultura": 80},
        {"Saúde": 60, "Educação": 160, "Cultura": 280},
        LONG_WINDOW,
    )
    assert share_of_voice_ratio(theme_stats(long_flat.window.counts, long_flat.including.counts)[
        "Saúde"], k_themes=3) < MEDIUM.ratio  # fmt: skip
    signals = classify_sustained(SHORT.stats(), long_flat.stats(), sens=MEDIUM, k_themes=3)
    assert "Saúde" not in {s.label for s in signals if s.kind == "sustained_spike"}


def test_queda_sustentada_exige_as_duas_janelas_e_baseline_minimo():
    signals = classify_sustained(SHORT.stats(), LONG.stats(), sens=MEDIUM, k_themes=3)
    drops = {s.label: s for s in signals if s.kind == "sustained_drop"}
    assert set(drops) == {"Educação"}
    assert drops["Educação"].ratio_short < 1 / MEDIUM.ratio
    assert drops["Educação"].severity >= 1 / 3

    # baseline pequeno: a fatia despenca, mas "4 artigos → 0" não é sinal em medium
    tiny_short = _pair({"Saúde": 1000, "X": 0}, {"Saúde": 1300, "X": 4}, SHORT_WINDOW)
    tiny_long = _pair({"Saúde": 2000, "X": 0}, {"Saúde": 2600, "X": 4}, LONG_WINDOW)
    x_short = share_of_voice_ratio(tiny_short.stats()["X"], k_themes=2)
    assert x_short < 1 / SENSITIVITY["low"].ratio
    tiny = classify_sustained(tiny_short.stats(), tiny_long.stats(), sens=MEDIUM, k_themes=2)
    assert "X" not in {s.label for s in tiny}
    high = SENSITIVITY["high"]  # min_count 3
    tiny_high = classify_sustained(tiny_short.stats(), tiny_long.stats(), sens=high, k_themes=2)
    assert "X" in {s.label for s in tiny_high if s.kind == "sustained_drop"}


def test_min_count_barra_pico_com_pouco_volume():
    short = _pair({"Raro": 3, "Saúde": 100}, {"Raro": 3, "Saúde": 700}, SHORT_WINDOW)
    long = _pair({"Raro": 4, "Saúde": 200}, {"Raro": 4, "Saúde": 800}, LONG_WINDOW)
    medium = classify_sustained(short.stats(), long.stats(), sens=MEDIUM, k_themes=2)
    assert "Raro" not in {s.label for s in medium}
    high = classify_sustained(short.stats(), long.stats(), sens=SENSITIVITY["high"], k_themes=2)
    assert "Raro" in {s.label for s in high if s.kind == "sustained_spike"}


def test_sinais_ordenados_por_severidade():
    signals = classify_sustained(SHORT.stats(), LONG.stats(), sens=MEDIUM, k_themes=3)
    assert [s.severity for s in signals] == sorted((s.severity for s in signals), reverse=True)


@pytest.mark.parametrize(
    ("count", "kwargs", "expected"),
    [(15, {}, "high"), (5, {}, "medium"), (4, {}, "low"), (15, {"degraded": True}, "low"),
     (15, {"recovery": True}, "medium"), (15, {"recovery": True, "classifier_changed": True},
                                           "low"), (5, {"recovery": True}, "low")],
)  # fmt: skip
def test_theme_confidence(count, kwargs, expected):
    assert theme_confidence(count, 5, **kwargs) == expected


def test_bloco_indisponivel_sem_classificacao_desde_26_09():
    # estado de 05/10: 0% dos artigos dos últimos 3 e 7 dias com tema
    short = _pair({}, {"Saúde": 300}, SHORT_WINDOW, totals=(400, 3200))
    long = _pair({}, {"Saúde": 900}, LONG_WINDOW, totals=(1097, 4300))
    block, status = build_themes_block(short, long, sens=MEDIUM, now=NOW)
    assert isinstance(block, ThemesBlock)
    assert block.status == "unavailable" and block.signals == []
    assert block.classified_coverage.short == 0.0 and block.classified_coverage.long == 0.0
    assert status.key == "themes" and status.status == "unavailable"
    assert status.since == date(2026, 9, 26)
    assert block.note and "26/09/2026" in block.note
    assert block.windows.short.kind == "rolling" and block.windows.short.days == 3
    assert block.windows.long.bucket_tz == "UTC" and block.windows.long.days == 7


def test_bloco_degradado_limita_a_confianca():
    scale = {k: v for k, v in SHORT.window.counts.items()}
    short = _pair(scale, SHORT.including.counts, SHORT_WINDOW, totals=(90, 400))  # 67%
    block, status = build_themes_block(short, LONG, sens=MEDIUM, now=NOW)
    assert block.status == "degraded" and status.status == "degraded"
    assert block.signals
    assert all(s.confidence == "low" for s in block.signals)
    assert all("degraded_coverage" in s.flags for s in block.signals)


def test_bloco_ok_com_flags_de_calendario():
    block, status = build_themes_block(SHORT, LONG, sens=MEDIUM, now=NOW)
    assert block.status == "ok" and status.status == "ok" and block.note is None
    assert block.classified_coverage.short == 1.0
    spike = next(s for s in block.signals if s.kind == "sustained_spike")
    # 05/10: o baseline de 28 dias cruza a troca de classificador (25/09) e o defeso
    assert "classifier_changed" in spike.flags
    assert "blackout_baseline" in spike.flags
    assert block.windows.long.baseline_overlaps_blackout is True

    later = datetime(2026, 12, 15, 15, 0, tzinfo=UTC)
    block_later, _ = build_themes_block(SHORT, LONG, sens=MEDIUM, now=later)
    spike_later = next(s for s in block_later.signals if s.kind == "sustained_spike")
    assert "classifier_changed" not in spike_later.flags
    assert "blackout_baseline" not in spike_later.flags
    assert spike_later.confidence == "high"


def test_bloco_na_recuperacao_rebaixa_a_confianca():
    recovery = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
    block, _ = build_themes_block(SHORT, LONG, sens=MEDIUM, now=recovery)
    spike = next(s for s in block.signals if s.kind == "sustained_spike")
    assert "recovery" in spike.flags
    assert spike.confidence == "medium"


def test_confianca_da_queda_usa_o_volume_esperado_pelo_baseline():
    # Educação: 150 artigos nos 21 dias anteriores → ~50 esperados em 7 dias; vieram 10.
    # A confiança mede o volume que sustentaria o sinal, não os poucos que sobraram.
    signals = classify_sustained(SHORT.stats(), LONG.stats(), sens=MEDIUM, k_themes=3)
    drop = next(s for s in signals if s.kind == "sustained_drop")
    assert drop.label == "Educação" and drop.count_long == 10
    assert drop.confidence == "high"
