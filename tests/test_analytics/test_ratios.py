"""Razões de crescimento: limiar convertido para o baseline sobreposto do trendingThemes
e razão sem sobreposição (integration.md §5 item 15)."""

import math

import pytest

from gobus_mcp.analytics.ratios import (
    ThemeWindowStat,
    band,
    laplace_ratio,
    overlap_growth_threshold,
    per_day_log_rate,
    ratio_from_trending_row,
    severity,
    share_of_voice_ratio,
    theme_stats,
    true_growth_ratio,
)


def test_limiar_convertido_7_28():
    # g0 = B·r0 / (r0·W + B − W) = 28·1,5 / (10,5 + 21)
    assert overlap_growth_threshold(1.5, 7, 28) == pytest.approx(1.3333, abs=1e-4)


def test_limiar_1_nao_muda():
    assert overlap_growth_threshold(1.0, 7, 28) == pytest.approx(1.0)


def test_limiar_corresponde_a_razao_sem_sobreposicao():
    # w = 21 em 7 dias e 21 nos 21 dias anteriores: razão real 3,0; growth da API 2,0
    w, b_prev, W, B = 21, 21, 7, 28
    growth_api = (w / W) / ((w + b_prev) / B)
    assert growth_api == pytest.approx(2.0)
    assert overlap_growth_threshold(3.0, W, B) == pytest.approx(growth_api)


def test_limiar_e_monotonico_e_limitado_por_b_sobre_w():
    values = [overlap_growth_threshold(r, 7, 28) for r in (1.0, 1.5, 2.0, 5.0, 100.0)]
    assert values == sorted(values)
    assert values[-1] < 28 / 7


@pytest.mark.parametrize(("r0", "W", "B"), [(1.5, 7, 7), (1.5, 28, 7), (0.0, 7, 28)])
def test_limiar_invalido(r0, W, B):
    with pytest.raises(ValueError):
        overlap_growth_threshold(r0, W, B)


def test_razao_sem_sobreposicao_com_laplace():
    g = true_growth_ratio(21, 42.0, 7, 28)
    assert g.baseline_prev_count == 21
    assert g.ratio == pytest.approx(3.0)  # ((21+1)/7) / ((21+1)/21)
    assert g.is_new is False


def test_baseline_so_com_a_janela_e_entidade_nova():
    # resolver: baselineDailyAvg = 21/28 = 0,75 → baseline inteiro é a própria janela
    g = ratio_from_trending_row({"windowCount": 21, "baselineDailyAvg": 0.75}, 7, 28)
    assert g.baseline_prev_count == 0
    assert g.is_new is True


def test_arredonda_baseline_da_api_e_protege_contra_negativo():
    assert true_growth_ratio(1, 0.107 * 28, 7, 28).baseline_prev_count == 2  # 2,996 → 3 − 1
    assert true_growth_ratio(10, 4.0, 7, 28).baseline_prev_count == 0


# ── G2: Laplace, share-of-voice, taxa log por dia, severidade e faixa ──────────


def test_laplace_ratio():
    # ((w+α)/W) / ((b+α)/B): 12 em 7 dias contra 7 em 28 → (13/7)/(8/28) = 6,5
    assert laplace_ratio(12, 7, 7, 28) == pytest.approx(6.5)
    # baseline zero não divide por zero
    assert laplace_ratio(10, 7, 0, 28) == pytest.approx((11 / 7) / (1 / 28))
    assert laplace_ratio(0, 7, 0, 28) == pytest.approx(4.0)  # (1/7)/(1/28)
    assert laplace_ratio(3, 7, 12, 28, alpha=0.5) == pytest.approx((3.5 / 7) / (12.5 / 28))


@pytest.mark.parametrize(("W", "B"), [(0, 28), (7, 0)])
def test_laplace_ratio_exige_dias_positivos(W, B):
    with pytest.raises(ValueError):
        laplace_ratio(1, W, 1, B)


def test_theme_stats_remove_a_sobreposicao_e_usa_totais_classificados():
    window = {"Saúde": 30, "Educação": 10}
    including = {"Saúde": 60, "Educação": 70, "Cultura": 20}
    stats = theme_stats(window, including)
    assert set(stats) == {"Saúde", "Educação", "Cultura"}
    assert stats["Saúde"] == ThemeWindowStat("Saúde", w=30, b_prev=30, total_w=40, total_prev=110)
    assert stats["Cultura"].w == 0 and stats["Cultura"].b_prev == 20
    assert stats["Saúde"].share == pytest.approx(0.75)


def test_theme_stats_protege_contra_contagens_inconsistentes():
    # as duas queries rodam em momentos diferentes: o range maior pode vir menor
    stats = theme_stats({"Saúde": 12}, {"Saúde": 10})
    assert stats["Saúde"].b_prev == 0 and stats["Saúde"].total_prev == 0
    assert theme_stats({}, {}) == {}


def test_share_of_voice_proporcional_da_um():
    # o tema cresce na mesma proporção que o total: SoV = 1
    s = ThemeWindowStat("Saúde", w=40, b_prev=160, total_w=400, total_prev=1600)
    # o Laplace puxa as fatias de amostras pequenas para 1/K: viés de poucos %
    assert share_of_voice_ratio(s, k_themes=25) == pytest.approx(1.0, abs=0.05)


def test_cenario_segunda_feira_sov_cancela_o_fim_de_semana():
    # janela de 3 dias = sáb+dom+seg: volume total despenca, a fatia do tema não muda
    w, total_w = 26, 260  # 10% em sáb+dom+seg
    b_prev, total_prev = 360, 3600  # 10% nos 18 dias anteriores
    raw = (w / 3) / (b_prev / 18)
    assert raw == pytest.approx(0.433, abs=0.001)
    s = ThemeWindowStat("Saúde", w=w, b_prev=b_prev, total_w=total_w, total_prev=total_prev)
    sov = share_of_voice_ratio(s, k_themes=25)
    assert sov == pytest.approx(1.0, abs=0.06)
    assert severity(1 / sov, 1.3) < 0.33  # nem "queda" na sensibilidade alta


def test_share_of_voice_pico_e_queda():
    spike = ThemeWindowStat("Saúde", w=60, b_prev=40, total_w=200, total_prev=800)
    drop = ThemeWindowStat("Saúde", w=2, b_prev=160, total_w=200, total_prev=800)
    assert share_of_voice_ratio(spike, k_themes=25) > 4
    assert share_of_voice_ratio(drop, k_themes=25) < 0.1


def test_share_of_voice_com_totais_zerados_e_neutro():
    s = ThemeWindowStat("Saúde", w=0, b_prev=0, total_w=0, total_prev=0)
    assert share_of_voice_ratio(s, k_themes=25) == pytest.approx(1.0)


@pytest.mark.parametrize(("W", "B", "dt"), [(3, 14, 7), (7, 28, 14), (21, 84, 42)])
def test_per_day_log_rate_usa_meia_distancia_do_baseline(W, B, dt):
    assert per_day_log_rate(2.0, W, B) == pytest.approx(math.log(2.0) / dt)
    assert per_day_log_rate(1.0, W, B) == 0.0
    assert per_day_log_rate(0.5, W, B) == pytest.approx(-math.log(2.0) / dt)


def test_per_day_log_rate_exige_razao_positiva():
    with pytest.raises(ValueError):
        per_day_log_rate(0.0, 7, 28)


@pytest.mark.parametrize("thr", [1.3, 1.5, 2.0, 3.0])
def test_severidade_no_limiar_comeca_watch_e_no_quadrado_vira_alert(thr):
    assert severity(thr, thr) == pytest.approx(1 / 3)
    assert severity(thr**2, thr) == pytest.approx(2 / 3)
    assert severity(thr**3, thr) == pytest.approx(1.0)
    assert severity(thr**5, thr) == 1.0
    assert severity(1.0, thr) == 0.0
    assert severity(0.5, thr) == 0.0
    assert band(severity(thr, thr)) == "watch"
    assert band(severity(thr**2, thr)) == "alert"


def test_severidade_exige_limiar_maior_que_um():
    with pytest.raises(ValueError):
        severity(2.0, 1.0)


@pytest.mark.parametrize(
    ("sev", "expected"),
    [(0.0, "normal"), (0.329, "normal"), (0.33, "watch"), (0.659, "watch"), (0.66, "alert"),
     (1.0, "alert")],
)  # fmt: skip
def test_faixa_da_severidade(sev, expected):
    assert band(sev) == expected
