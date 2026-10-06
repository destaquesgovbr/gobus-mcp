"""Funções puras da coerência de mensagem (F5, ``analytics.coherence``)."""

import math
from datetime import UTC, date, datetime

import pytest

from gobus_mcp.analytics.coherence import (
    DEFAULT_SALIENCE,
    assess,
    brt_day,
    combine,
    cosine,
    entity_dimension,
    excluded_entities,
    framing_dimension,
    hhi,
    idf,
    index_level,
    jaccard,
    jsd,
    parse_article,
    split_agencies,
    timing_dimension,
    tone_dimension,
    truncated_start,
)
from gobus_mcp.payloads.coherence import DIMENSION_ORDER

REPUBLISHERS = frozenset({"agencia_brasil", "tvbrasil", "ebc", "radioagencia_nacional"})


def row(agency, published="2026-09-10T12:00:00+00:00", entities=(), title="Nota", **extra):
    """Linha no formato do ``articles`` da graphql-api."""
    base = {
        "uniqueId": f"{agency}-{published}-{title}",
        "title": title,
        "agency": agency,
        "agencyName": None,
        "publishedAt": published,
        "subtitle": None,
        "editorialLead": None,
        "summary": None,
        "tags": [],
        "features": {
            "entities": [
                {"canonicalId": cid, "text": text, "type": etype, "salience": sal}
                for cid, text, etype, sal in entities
            ]
        },
    }
    base.update(extra)
    return base


def arts(*rows):
    return [parse_article(r) for r in rows]


ENTS_A = [("Q1", "Saúde", "ORG", 0.8), ("Q2", "SUS", "ORG", 0.6), ("Q3", "Vacina", "MISC", 0.5)]
ENTS_B = [("Q4", "PF", "ORG", 0.8), ("Q5", "Fraude", "MISC", 0.6), ("Q6", "INSS", "ORG", 0.5)]


# ── primitivas ──────────────────────────────────────────────────────────────


def test_virada_de_dia_brt():
    assert brt_day(datetime(2026, 9, 26, 1, 30, tzinfo=UTC)) == date(2026, 9, 25)
    assert brt_day(datetime(2026, 9, 26, 3, 0, tzinfo=UTC)) == date(2026, 9, 26)
    article = parse_article(row("mds", "2026-09-26T01:30:00+00:00"))
    assert brt_day(article.published_at) == date(2026, 9, 25)


def test_cosseno_identico_da_1_e_disjunto_da_0():
    assert cosine({"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0}) == pytest.approx(1.0)
    assert cosine({"a": 1.0, "b": 2.0}, {"a": 3.0, "b": 6.0}) == pytest.approx(1.0)
    assert cosine({"a": 1.0}, {"b": 1.0}) == 0.0
    assert cosine({}, {"b": 1.0}) == 0.0


def test_idf_derruba_a_entidade_onipresente():
    weights = idf({"Q155": 10, "Q1": 1}, 10)
    assert weights["Q155"] == pytest.approx(math.log(2))
    assert weights["Q1"] == pytest.approx(math.log(11))
    assert weights["Q155"] < weights["Q1"]


def test_jsd_propriedades():
    p = {"positive": 8, "negative": 1, "neutral": 1}
    q = {"positive": 1, "negative": 8, "neutral": 1}
    assert jsd(p, p) == pytest.approx(0.0)
    assert jsd({"a": 1}, {"b": 1}) == pytest.approx(1.0)  # base 2: disjuntas = 1
    assert jsd(p, q) == pytest.approx(jsd(q, p))
    assert 0.0 < jsd(p, q) < 1.0
    assert jsd({"a": 2, "b": 2}, {"a": 1, "b": 1}) == pytest.approx(0.0)  # escala não importa
    assert jsd({}, p) is None


def test_jaccard():
    assert jaccard({1, 2}, {2, 3}) == pytest.approx(1 / 3)
    assert jaccard(set(), set()) == 0.0


def test_hhi():
    assert hhi([10, 10]) == pytest.approx(0.5)
    assert hhi([10]) == pytest.approx(1.0)
    assert hhi([]) is None


def test_parse_dedup_de_entidade_por_artigo_e_salience_nula():
    article = parse_article(
        row(
            "mec",
            entities=[
                ("Q41550", "OCDE", "ORG", 0.6),
                ("Q41550", "Organização para a Cooperação", "ORG", 0.8),
                (None, "Ricardo", "PER", 0.4),
                ("Q1", "Saúde", "ORG", None),
            ],
        )
    )
    by_id = {m.id: m for m in article.entities}
    assert set(by_id) == {"Q41550", "Q1"}  # sem canonicalId fica fora
    assert by_id["Q41550"].salience == 0.8  # a maior entre as menções
    assert by_id["Q1"].salience == DEFAULT_SALIENCE
    assert article.texts["Q41550"] == ["OCDE", "Organização para a Cooperação"]


def test_parse_descarta_linha_sem_agencia_ou_data():
    assert parse_article(row("", "2026-09-10T12:00:00+00:00")) is None
    assert parse_article(row("mec", None)) is None


def test_excluidas_a_propria_entidade_e_as_dgb_do_catalogo():
    assert excluded_entities("Q575545", {"mds", "trabalho-e-emprego"}) == frozenset(
        {"Q575545", "dgb_mds", "dgb_trabalho-e-emprego"}
    )


# ── emissores ───────────────────────────────────────────────────────────────


def test_republicadoras_separadas_e_agencia_de_1_artigo_fora():
    split = split_agencies(
        arts(
            row("mds"),
            row("mds", "2026-09-11T12:00:00+00:00"),
            row("fazenda"),
            row("agencia_brasil"),
            row("agencia_brasil", "2026-09-12T12:00:00+00:00"),
            row("tvbrasil"),
        ),
        REPUBLISHERS,
    )
    assert set(split.emitters) == {"mds"}
    assert set(split.singles) == {"fazenda"}
    assert {k: len(v) for k, v in split.republishers.items()} == {
        "agencia_brasil": 2,
        "tvbrasil": 1,
    }


# ── dimensões ───────────────────────────────────────────────────────────────


def _emitters(rows):
    return split_agencies(arts(*rows), REPUBLISHERS).emitters


def test_entidades_identicas_dao_1_e_disjuntas_dao_0():
    same = _emitters([row("a", entities=ENTS_A), row("a", entities=ENTS_A),
                      row("b", entities=ENTS_A), row("b", entities=ENTS_A)])  # fmt: skip
    assert entity_dimension(same, exclude=frozenset()).value == pytest.approx(1.0)

    disjoint = _emitters([row("a", entities=ENTS_A), row("a", entities=ENTS_A),
                          row("b", entities=ENTS_B), row("b", entities=ENTS_B)])  # fmt: skip
    assert entity_dimension(disjoint, exclude=frozenset()).value == pytest.approx(0.0)


def test_entidade_onipresente_pesa_menos_no_vetor():
    brasil = ("Q155", "Brasil", "LOC", 0.8)
    emitters = _emitters(
        [
            row("a", entities=[*ENTS_A, brasil]),
            row("a", entities=[brasil, ("Q7", "X", "ORG", 0.1)]),
            row("b", entities=[*ENTS_B, brasil]),
            row("b", entities=[brasil, ("Q8", "Y", "ORG", 0.1)]),
        ]
    )
    result = entity_dimension(emitters, exclude=frozenset())
    # sem idf, o Q155 (0,8 nos 2 artigos de a) pesaria o dobro do Q1 (0,8 em 1 artigo);
    # com idf (Q155 em todos os artigos), passa a pesar menos
    assert result.vectors["a"]["Q155"] < result.vectors["a"]["Q1"]


def test_entidade_excluida_e_agencia_com_menos_de_3_entidades_fora():
    emitters = _emitters(
        [
            row("a", entities=[*ENTS_A, ("Q575545", "Bolsa Família", "POLICY", 0.9)]),
            row("a", entities=[("dgb_mds", "MDS", "ORG", 0.9)]),
            row("b", entities=ENTS_A),
            row("b", entities=ENTS_A),
            row("c", entities=[("Q1", "Saúde", "ORG", 0.5)]),
            row("c", entities=[("dgb_mds", "MDS", "ORG", 0.5)]),
        ]
    )
    result = entity_dimension(emitters, exclude=frozenset({"Q575545", "dgb_mds"}))
    assert "Q575545" not in result.vectors["a"]
    assert "dgb_mds" not in result.vectors["a"]
    assert result.eligible == ["a", "b"]  # c tem 1 entidade depois da exclusão


def test_entidades_indisponiveis_com_menos_de_2_agencias_elegiveis():
    emitters = _emitters([row("a", entities=ENTS_A), row("a"), row("b"), row("b")])
    result = entity_dimension(emitters, exclude=frozenset())
    assert result.value is None
    assert "3 entidades" in result.reason


def test_ancoras_compartilhadas_e_exclusivas():
    emitters = _emitters(
        [
            row("a", entities=[*ENTS_A, ("Q9", "Pé-de-Meia", "POLICY", 0.9)]),
            row("a", entities=[("Q9", "Programa Pé-de-Meia", "POLICY", 0.9), *ENTS_A]),
            row("b", entities=[*ENTS_B, ("Q9", "Pé-de-Meia", "POLICY", 0.7)]),
            row("b", entities=ENTS_B),
        ]
    )
    result = entity_dimension(emitters, exclude=frozenset())
    assert [a.entity_id for a in result.shared] == ["Q9"]
    assert result.shared[0].label == "Pé-de-Meia"  # o texto mais frequente
    assert result.shared[0].agencies == 2
    assert {a.entity_id for a in result.exclusive["a"]} <= {"Q1", "Q2", "Q3"}
    assert result.exclusive["a"][0].entity_id == "Q1"  # maior peso primeiro


def test_timing_brt_atraso_48h_e_jaccard_de_dias():
    emitters = _emitters(
        [
            row("a", "2026-09-01T12:00:00+00:00"),
            row("a", "2026-09-02T12:00:00+00:00"),
            row("b", "2026-09-02T13:00:00+00:00"),
            row("b", "2026-09-03T12:00:00+00:00"),
            row("c", "2026-09-06T12:00:00+00:00"),
            row("c", "2026-09-07T12:00:00+00:00"),
        ]
    )
    result = timing_dimension(emitters)
    assert result.delay_hours == {"a": 0.0, "b": 25.0, "c": 120.0}
    assert result.within == pytest.approx(0.5)  # b em 25 h; c em 120 h
    # jaccard: a×b = 1/3, a×c = 0, b×c = 0
    assert result.jaccard == pytest.approx(1 / 9)
    assert result.value == pytest.approx(0.5 * 0.5 + 0.5 / 9)
    assert result.first["a"].utcoffset().total_seconds() == -3 * 3600  # BRT


def test_timing_conta_os_dias_em_brt():
    # 26/09 01:30Z é 25/09 em BRT: os dois artigos caem no mesmo dia
    emitters = _emitters(
        [
            row("a", "2026-09-25T15:00:00+00:00"),
            row("a", "2026-09-25T16:00:00+00:00"),
            row("b", "2026-09-26T01:30:00+00:00"),
            row("b", "2026-09-25T18:00:00+00:00"),
        ]
    )
    assert timing_dimension(emitters).jaccard == pytest.approx(1.0)


def test_enquadramento_indisponivel_abaixo_de_40_pct_classificado():
    emitters = _emitters(
        [
            row("a", title="Governo anuncia programa"),
            row("a", title="Nota"),
            row("b", title="Nota"),
            row("b", title="Nota"),
            row("b", title="Nota"),
        ]
    )
    result = framing_dimension(emitters)
    assert result.value is None
    assert result.classified_share == pytest.approx(0.2)
    assert "20%" in result.reason


def test_enquadramento_1_menos_jsd():
    emitters = _emitters(
        [
            row("a", title="Governo anuncia programa"),
            row("a", title="Governo lança plano"),
            row("b", title="PF deflagra operação contra fraude"),
            row("b", title="Operação combate crime"),
        ]
    )
    result = framing_dimension(emitters)
    assert result.value == pytest.approx(0.0)  # distribuições disjuntas
    assert result.dominant == {"a": "announcement", "b": "challenge"}


def test_tom_so_com_cobertura_de_50_pct():
    low = tone_dimension(
        {"a": {"positive": 2, "negative": 0, "neutral": 0}, "b": {"positive": 2}},
        {"a": 10, "b": 10},
    )
    assert low.value is None
    assert low.coverage == pytest.approx(0.2)
    assert "20%" in low.reason

    ok = tone_dimension(
        {
            "a": {"positive": 8, "negative": 0, "neutral": 2},
            "b": {"positive": 4, "negative": 0, "neutral": 1},
        },
        {"a": 10, "b": 5},
    )
    assert ok.coverage == pytest.approx(1.0)
    assert ok.value == pytest.approx(1.0)


def test_renormalizacao_sem_tom_e_sem_enquadramento():
    score, effective = combine({"entities": 0.5, "timing": 1.0, "framing": None, "tone": None})
    assert score == pytest.approx((0.35 * 0.5 + 0.25 * 1.0) / 0.6)
    assert effective["entities"] == pytest.approx(0.35 / 0.6)
    assert effective["timing"] == pytest.approx(0.25 / 0.6)
    assert effective["framing"] is None and effective["tone"] is None
    assert combine(dict.fromkeys(DIMENSION_ORDER)) == (None, dict.fromkeys(DIMENSION_ORDER))


@pytest.mark.parametrize(
    ("score", "level"),
    [(0.0, 1), (0.19, 1), (0.2, 2), (0.39, 2), (0.4, 3), (0.59, 3), (0.6, 4), (0.8, 5), (1.0, 5)],
)
def test_cortes_do_indice(score, level):
    assert index_level(score) == level


def test_indice_nulo_sem_score():
    assert index_level(None) is None


def test_inicio_truncado_compara_taxas_diarias():
    # 30 artigos em 30 dias antes (1/dia) contra 14 em 14 dias: a pauta já corria
    assert truncated_start(30, 30, 14, 14)
    # 3 artigos antes (0,1/dia) contra 28 em 14 dias (2/dia): a janela pega o começo
    assert not truncated_start(3, 30, 28, 14)
    # entidade grande com prior alto, mas janela muito mais intensa: não é truncado
    assert not truncated_start(60, 30, 140, 14)
    # prior com menos de 3 artigos nunca dispara
    assert not truncated_start(2, 30, 1, 14)


# ── avaliação completa ──────────────────────────────────────────────────────


def test_insuficiente_com_voz_unica():
    result = assess(
        arts(
            row("mds"),
            row("mds", "2026-09-11T12:00:00+00:00"),
            row("fazenda"),
            row("agencia_brasil"),
        ),
        republishers=REPUBLISHERS,
        exclude=frozenset(),
        names={"mds": "Ministério do Desenvolvimento Social"},
    )
    assert result.index_status == "insufficient"
    assert (
        result.insufficient_reason == "voz única: Ministério do Desenvolvimento Social (2 artigos)"
    )
    assert result.index.score is None and result.index.level is None
    assert [d.key for d in result.dimensions] == list(DIMENSION_ORDER)
    assert all(d.status == "unavailable" for d in result.dimensions)
    assert result.sample["single_article_agencies"] == 1
    assert result.republishers.articles == 1


def test_insuficiente_sem_emissor():
    result = assess(
        arts(row("agencia_brasil"), row("fazenda")),
        republishers=REPUBLISHERS,
        exclude=frozenset(),
    )
    assert result.index_status == "insufficient"
    assert "nenhuma agência" in result.insufficient_reason
    assert result.republishers.agencies[0].delay_hours is None


def test_avaliacao_com_tres_emissores_e_divergencia():
    rows = [
        row("a", "2026-09-01T12:00:00+00:00", ENTS_A, "Governo anuncia programa"),
        row("a", "2026-09-02T12:00:00+00:00", ENTS_A, "Governo lança plano"),
        row("b", "2026-09-01T15:00:00+00:00", ENTS_A, "Governo anuncia programa"),
        row("b", "2026-09-02T15:00:00+00:00", ENTS_A, "Governo lança plano"),
        row("b", "2026-09-02T16:00:00+00:00", ENTS_A, "Nota"),
        row("c", "2026-09-08T12:00:00+00:00", ENTS_B, "PF deflagra operação contra fraude"),
        row("c", "2026-09-09T12:00:00+00:00", ENTS_B, "Operação combate crime"),
        row("agencia_brasil", "2026-09-01T18:00:00+00:00", ENTS_A, "Nota"),
    ]
    tone = {
        "a": {"positive": 2, "negative": 0, "neutral": 0},
        "b": {"positive": 3, "negative": 0, "neutral": 0},
        "c": {"positive": 0, "negative": 2, "neutral": 0},
    }
    result = assess(
        arts(*rows),
        republishers=REPUBLISHERS,
        exclude=frozenset(),
        names={"a": "Agência A"},
        tone_counts=tone,
        tone_totals={"a": 2, "b": 3, "c": 2},
    )
    assert result.index_status == "scored"
    assert [a.agency_key for a in result.agencies] == ["b", "a", "c"]  # por volume
    assert result.agencies[1].agency_name == "Agência A"
    assert result.agencies[2].agency_name == "c"  # sem nome: o código
    assert all(d.status == "ok" for d in result.dimensions)
    assert 1 <= result.index.level <= 5
    weights = [d.effective_weight for d in result.dimensions]
    assert sum(weights) == pytest.approx(1.0)
    # o par mais divergente envolve c (entidades, timing, enquadramento e tom opostos)
    worst = result.divergences[0]
    assert "c" in worst.agencies
    assert worst.weakest in ("entities", "framing", "tone")
    assert set(result.divergences[-1].agencies) == {"a", "b"}
    # republicadora: 6 h depois do 1º emissor (a, 09:00 BRT)
    (rep,) = result.republishers.agencies
    assert rep.delay_hours == pytest.approx(6.0)
    assert result.republishers.share == pytest.approx(1 / 8)
    assert result.hhi == pytest.approx((2 / 7) ** 2 + (3 / 7) ** 2 + (2 / 7) ** 2, abs=1e-4)


def test_avaliacao_renormaliza_sem_tom():
    rows = [
        row("a", "2026-09-01T12:00:00+00:00", ENTS_A, "Governo anuncia programa"),
        row("a", "2026-09-02T12:00:00+00:00", ENTS_A, "Governo lança plano"),
        row("b", "2026-09-01T15:00:00+00:00", ENTS_A, "Governo anuncia programa"),
        row("b", "2026-09-02T15:00:00+00:00", ENTS_A, "Governo lança plano"),
    ]
    result = assess(
        arts(*rows),
        republishers=REPUBLISHERS,
        exclude=frozenset(),
        tone_counts={"a": {"positive": 0}, "b": {"positive": 0}},
        tone_totals={"a": 2, "b": 2},
    )
    by_key = {d.key: d for d in result.dimensions}
    assert by_key["tone"].status == "unavailable"
    assert by_key["tone"].effective_weight is None
    assert by_key["entities"].effective_weight == pytest.approx(0.35 / 0.85, abs=1e-4)  # 4 casas
    assert result.index.score == pytest.approx(1.0)  # tudo idêntico
    assert result.index.level == 5


def test_tom_nao_medido_fica_indisponivel_com_o_motivo():
    rows = [row("a"), row("a"), row("b"), row("b")]
    result = assess(
        arts(*rows), republishers=REPUBLISHERS, exclude=frozenset(), tone_error="timeout"
    )
    tone = next(d for d in result.dimensions if d.key == "tone")
    assert tone.status == "unavailable"
    assert "timeout" in tone.detail


def test_mock_contado_na_amostra():
    rows = [
        row("a", summary="[MOCK] Resumo gerado para teste local"),
        row("a"),
        row("b"),
        row("b"),
    ]
    result = assess(arts(*rows), republishers=REPUBLISHERS, exclude=frozenset())
    assert result.sample["mock_summaries_ignored"] == 1
