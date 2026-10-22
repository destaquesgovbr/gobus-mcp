"""Flesch pt-BR (Martins et al., 1996, GQL-1) com a fórmula inglesa (legado) de reserva:
escalas, escolha por resposta, média pela contagem de artigos com valor, status e aviso."""

import pytest

from gobus_mcp.readability import (
    EN_SCALE,
    FLESCH_SCALE_EN,
    FLESCH_SCALE_PTBR,
    LEGACY_SCALE_MESSAGE,
    PTBR_SCALE,
    article_flesch,
    choose_scale,
    legacy_scale_notice,
    readability_status,
    scale_metric,
    weighted_metric,
)


def _row(n, ptbr=None, count=None, english=None):
    return {
        "period": "2026-10-01 00:00:00+00",
        "articleCount": n,
        "avgReadabilityFleschPtbr": ptbr,
        "readabilityFleschPtbrCount": (n if ptbr is not None else 0) if count is None else count,
        "avgReadabilityFlesch": english,
    }


def test_escalas_e_campos_da_api():
    assert (PTBR_SCALE.id, EN_SCALE.id) == (FLESCH_SCALE_PTBR, FLESCH_SCALE_EN)
    assert PTBR_SCALE.article_field == "readabilityFleschPtbr"
    assert PTBR_SCALE.avg_field == "avgReadabilityFleschPtbr"
    assert PTBR_SCALE.count_field == "readabilityFleschPtbrCount"
    assert (EN_SCALE.article_field, EN_SCALE.avg_field) == (
        "readabilityFlesch",
        "avgReadabilityFlesch",
    )
    assert EN_SCALE.count_field is None
    assert (PTBR_SCALE.legacy, EN_SCALE.legacy) == (False, True)
    assert "Martins" in PTBR_SCALE.label and "inglesa" in EN_SCALE.label


@pytest.mark.parametrize(
    ("features", "value", "scale"),
    [
        ({"readabilityFleschPtbr": 15.2, "readabilityFlesch": 13.0}, 15.2, PTBR_SCALE),
        ({"readabilityFleschPtbr": 0.0, "readabilityFlesch": 13.0}, 0.0, PTBR_SCALE),  # 0 é dado
        ({"readabilityFleschPtbr": None, "readabilityFlesch": 13.0}, 13.0, EN_SCALE),
        ({"readabilityFlesch": -4.0}, -4.0, EN_SCALE),  # API antiga
        ({"readabilityFleschPtbr": None, "readabilityFlesch": None}, None, PTBR_SCALE),
        ({}, None, PTBR_SCALE),
        (None, None, PTBR_SCALE),
    ],
)
def test_article_flesch_prefere_o_ptbr(features, value, scale):
    assert article_flesch(features) == (value, scale)


def test_media_ponderada_pela_contagem_de_artigos_com_valor():
    rows = [_row(100, ptbr=20.0, count=10), _row(50, ptbr=10.0, count=50), _row(30)]

    cov = scale_metric(rows, PTBR_SCALE)

    assert cov.value == pytest.approx((20 * 10 + 10 * 50) / 60)
    assert (cov.covered_articles, cov.total_articles) == (60, 180)
    # sem a contagem, o mesmo cálculo ponderaria pelos artigos da linha
    plain = weighted_metric(rows, "avgReadabilityFleschPtbr")
    assert plain.value == pytest.approx((20 * 100 + 10 * 50) / 150)


def test_contagem_maior_que_os_artigos_e_limitada():
    cov = scale_metric([_row(10, ptbr=30.0, count=99)], PTBR_SCALE)
    assert (cov.covered_articles, cov.total_articles) == (10, 10)


def test_sem_contagem_na_linha_usa_os_artigos():
    row = {"articleCount": 40, "avgReadabilityFleschPtbr": 12.0}
    assert scale_metric([row], PTBR_SCALE).covered_articles == 40


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([_row(100, ptbr=15.0, english=13.0)], PTBR_SCALE),
        ([_row(100, english=13.0)], EN_SCALE),  # pt-BR nulo: reserva
        ([{"articleCount": 100, "avgReadabilityFlesch": 13.0}], EN_SCALE),  # API antiga
        ([_row(100)], PTBR_SCALE),  # nada: pt-BR "indisponível"
        ([], PTBR_SCALE),
        # pt-BR em só 5% dos artigos (antes do backfill) e o inglês em todos: inglês
        ([_row(100, ptbr=15.0, count=5, english=13.0)], EN_SCALE),
        # pt-BR em 10%: já vale
        ([_row(100, ptbr=15.0, count=10, english=13.0)], PTBR_SCALE),
        # pt-BR raro, mas o inglês não tem nada: pt-BR
        ([_row(100, ptbr=15.0, count=5)], PTBR_SCALE),
    ],
)
def test_choose_scale(rows, expected):
    assert choose_scale(rows) is expected


def test_status_ptbr_diz_a_escala_e_nao_herda_a_data_do_ingles():
    status = readability_status([_row(100), _row(100)], PTBR_SCALE)

    assert status.status == "unavailable"
    assert status.since is None
    assert "Flesch pt-BR" in status.message


def test_status_ingles_mantem_a_dica_de_30_06():
    status = readability_status([_row(100)], EN_SCALE)

    assert status.status == "unavailable"
    assert status.since.isoformat() == "2026-06-30"


def test_status_conta_so_os_artigos_com_valor():
    status = readability_status([_row(100, ptbr=15.0, count=85)], PTBR_SCALE)

    assert status.status == "ok"
    assert status.metric["coveredArticles"] == 85
    assert status.metric["ratio"] == pytest.approx(0.85)


def test_aviso_so_na_escala_inglesa():
    assert legacy_scale_notice(PTBR_SCALE) is None
    notice = legacy_scale_notice(EN_SCALE)
    assert notice.code == "READABILITY_LEGACY_SCALE"
    assert notice.severity == "warn"
    assert notice.message == LEGACY_SCALE_MESSAGE
    assert notice.affects == ["readability"]
