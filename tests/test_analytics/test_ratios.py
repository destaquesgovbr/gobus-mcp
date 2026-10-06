"""Razões de crescimento: limiar convertido para o baseline sobreposto do trendingThemes
e razão sem sobreposição (integration.md §5 item 15)."""

import pytest

from gobus_mcp.analytics.ratios import (
    overlap_growth_threshold,
    ratio_from_trending_row,
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
