"""Enquadramento lexical pt-BR do F5 (``analytics.framing``)."""

import pytest

from gobus_mcp.analytics.framing import (
    FRAME_LABELS,
    FRAME_PRIORITY,
    article_frame,
    classify_frame,
    frame_scores,
    is_mock_summary,
    normalize_text,
)


def test_normaliza_sem_acento_minusculas_e_sem_pontuacao():
    assert normalize_text("Operação  CONTRA-fraude: já!") == "operacao contra fraude ja"
    assert normalize_text(None) == ""


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Governo anuncia novo programa de crédito", "announcement"),
        ("Presidente sanciona lei e lança plano nacional", "announcement"),
        ("PF deflagra operação contra fraude no INSS", "challenge"),
        ("Ministério alerta para golpe com falso benefício", "challenge"),
        ("Número de beneficiários cresce 12% e bate recorde", "result"),
        ("Percentual de jovens nem-nem cai para 22,4%, mostra estudo", "result"),
        ("Inscrições abertas: saiba como se inscrever no Enem", "service"),
        ("Calendário de pagamento do Bolsa Família começa nesta segunda", "service"),
        ("Ministro participa de reunião com governadores", "agenda"),
        ("Comitiva visita obras e encontro reúne prefeitos", "agenda"),
    ],
)
def test_lexico_pt_br_classifica_o_enquadramento(title, expected):
    assert classify_frame(title) == expected


def test_sem_termo_do_lexico_fica_sem_enquadramento():
    assert classify_frame("Texto qualquer sobre a semana") is None
    assert frame_scores("") == dict.fromkeys(FRAME_PRIORITY, 0)


def test_instituto_e_crianca_nao_sao_anuncio():
    # prefixos curtos não podem casar palavras comuns (instituto ≠ institui; criança ≠ cria)
    assert classify_frame("Instituto divulga dados sobre crianças") != "announcement"


def test_titulo_pesa_o_dobro_do_corpo():
    # corpo com 1 termo de agenda contra título com 1 termo de serviço: o título vence
    assert classify_frame("Inscrições abertas", "reunião técnica") == "service"
    # 3 termos de agenda no corpo superam 1 termo de serviço no título (peso 2)
    assert classify_frame("Inscrições", "reunião, visita e encontro") == "agenda"


def test_empate_usa_a_prioridade_fixa():
    scores = frame_scores("anuncia operação")  # 1 anúncio, 1 desafio
    assert scores["announcement"] == scores["challenge"] == 1
    assert classify_frame("anuncia operação") == FRAME_PRIORITY[0] == "challenge"


def test_rotulos_pt_cobrem_todos_os_enquadramentos():
    assert set(FRAME_LABELS) == {*FRAME_PRIORITY, "other"}
    assert FRAME_LABELS["announcement"] == "anúncio"


def test_resumo_mock_e_ignorado():
    assert is_mock_summary("[MOCK] Resumo gerado para teste local — anuncia")
    assert is_mock_summary("  [MOCK] x")
    assert not is_mock_summary("Resumo de verdade")
    assert not is_mock_summary(None)

    article = {
        "title": "Texto qualquer",
        "summary": "[MOCK] Resumo gerado para teste local — governo anuncia programa",
        "tags": [],
    }
    assert article_frame(article) == (None, True)


def test_artigo_usa_titulo_subtitulo_lead_resumo_e_tags():
    article = {
        "title": "Nota oficial",
        "subtitle": None,
        "editorialLead": "O governo anuncia hoje",
        "summary": "Resumo sem termo",
        "tags": ["Lançamento"],
    }
    assert article_frame(article) == ("announcement", False)
