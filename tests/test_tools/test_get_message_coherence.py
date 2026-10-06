"""``gobus_get_message_coherence`` (F5): roteamento por operação, paginação, tom por aliases
de contagem, prior, tema dinâmico e erros. Relógio fixo em 06/10/2026 12:00 BRT."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from graphql import build_schema, parse, validate

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import BRT
from gobus_mcp.payloads.coherence import CoherenceReport
from gobus_mcp.payloads.common import payload_size
from gobus_mcp.tools.get_message_coherence import (
    MAX_TONE_AGENCIES,
    build_coherence_output,
    counts_query,
    get_message_coherence,
)
from tests.conftest import route_catalog

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=BRT)  # D = 06/10; padrão: 22/09–05/10
SCHEMA = build_schema(
    (Path(__file__).parents[1] / "fixtures" / "schema.graphql").read_text(encoding="utf-8")
)

LABELS = [
    "Saúde",
    "Educação",
    "Desenvolvimento Social",
    "Defesa e Forças Armadas",
    "Minorias e Grupos Especiais",
    "Justiça e Direitos Humanos",
]

BOLSA = ("Q575545", "Bolsa Família", "POLICY", 0.9)
CADUNICO = ("dgb_cadastro-unico", "Cadastro Único", "POLICY", 0.7)
BRASIL = ("Q155", "Brasil", "LOC", 0.5)
DGB_MDS = ("dgb_mds", "MDS", "ORG", 0.8)  # mds é código do catálogo: excluída
DGB_SAUDE = ("dgb_saude", "Ministério da Saúde", "ORG", 0.8)


def art(agency, published, entities=(), title="Nota", summary=None, uid=None):
    return {
        "uniqueId": uid or f"{agency}-{published}-{title}",
        "title": title,
        "agency": agency,
        "agencyName": None,
        "publishedAt": published,
        "subtitle": None,
        "editorialLead": None,
        "summary": summary,
        "tags": [],
        "features": {
            "entities": [
                {"canonicalId": c, "text": t, "type": k, "salience": s} for c, t, k, s in entities
            ]
        },
    }


ARTICLES = [
    art("mds", "2026-09-22T13:00:00+00:00", [BOLSA, CADUNICO, DGB_MDS, ("Q1", "Wellington Dias", "PER", 0.6)], "Calendário de pagamento do Bolsa Família"),  # noqa: E501
    art("mds", "2026-09-23T13:00:00+00:00", [BOLSA, CADUNICO, BRASIL, ("Q1", "Wellington Dias", "PER", 0.6)], "Saiba como consultar o benefício"),  # noqa: E501
    art("mds", "2026-09-24T13:00:00+00:00", [BOLSA, CADUNICO, BRASIL], "Pagamento começa nesta segunda"),  # noqa: E501
    art("mds", "2026-09-25T13:00:00+00:00", [BOLSA, CADUNICO, BRASIL], "Inscrições no Cadastro Único"),  # noqa: E501
    art("saude", "2026-09-23T15:00:00+00:00", [BOLSA, CADUNICO, DGB_SAUDE, ("Q2", "Vacinação", "MISC", 0.6)], "Ministério anuncia vacinação de beneficiários"),  # noqa: E501
    art("saude", "2026-09-24T15:00:00+00:00", [BOLSA, CADUNICO, DGB_SAUDE, ("Q2", "Vacinação", "MISC", 0.6)], "Saúde lança campanha"),  # noqa: E501
    art("saude", "2026-09-26T01:30:00+00:00", [BOLSA, CADUNICO, BRASIL], "Calendário de pagamento"),  # noqa: E501
    art("mec", "2026-09-29T12:00:00+00:00", [BOLSA, ("Q3", "Pé-de-Meia", "POLICY", 0.8), BRASIL], "Pé-de-Meia: resultado cresce"),  # noqa: E501
    art("mec", "2026-09-30T12:00:00+00:00", [BOLSA, ("Q3", "Pé-de-Meia", "POLICY", 0.8), BRASIL], "Balanço do programa bate recorde"),  # noqa: E501
    art("agencia_brasil", "2026-09-22T20:00:00+00:00", [BOLSA, CADUNICO], "Governo paga Bolsa Família"),  # noqa: E501
    art("agencia_brasil", "2026-09-23T20:00:00+00:00", [BOLSA], "Nota"),
    art("tvbrasil", "2026-09-24T20:00:00+00:00", [BOLSA], "Nota"),
    art("secom", "2026-09-25T20:00:00+00:00", [BOLSA, CADUNICO], "Nota"),
]  # fmt: skip

TONE = {  # (agência, rótulo) → artigos
    ("mds", "positive"): 3,
    ("mds", "neutral"): 1,
    ("saude", "positive"): 2,
    ("saude", "neutral"): 1,
    ("mec", "positive"): 2,
}


def _matches(article: dict, filt: dict) -> bool:
    agencies = filt.get("agencies")
    return not agencies or article["agency"] in agencies


def articles_route(articles=ARTICLES, found=None):
    """``CoherenceArticles`` paginado: 250 por página (ou ``found`` fixo, com as linhas de
    ``articles`` repetidas por página)."""

    def handler(variables):
        rows = [a for a in articles if _matches(a, variables["filter"])]
        page = variables["page"]
        if found is None:
            chunk = rows[(page - 1) * 250 : page * 250]
            total = len(rows)
        else:
            chunk = [dict(a, uniqueId=f"{a['uniqueId']}-p{page}") for a in rows]
            total = found
        return {"articles": {"found": total, "page": page, "articles": chunk}}

    return handler


def counts_route(tone=TONE, totals=None, themes=None, theme_total=None):
    """``CoherenceCounts``: ``found`` de cada alias pelo filtro (agência × sentimento, total
    por agência, label de tema ou total da janela)."""
    totals = totals or {}
    themes = themes or {}

    def found(filt: dict) -> int:
        if "sentiment" in filt:
            ((agency,), (label,)) = filt["agencies"], filt["sentiment"]
            return tone.get((agency, label), 0)
        if "themeLabel" in filt and "entityCanonical" not in filt and theme_total is not None:
            return themes.get(filt["themeLabel"], 0)
        if filt.get("agencies") and len(filt["agencies"]) == 1 and totals:
            return totals.get(filt["agencies"][0], 0)
        return theme_total or 0

    def handler(variables):
        return {f"c{k[1:]}": {"found": found(v)} for k, v in variables.items()}

    return handler


ENTITY = {"entity": {"entityId": "Q575545", "canonicalName": "Bolsa Família", "type": "POLICY"}}


def scenario(client, *, articles=ARTICLES, found=None, prior=(), tone=TONE, totals=None):
    route_catalog(client)
    client.route("CoherenceEntity", ENTITY)
    client.route("CoherenceArticles", articles_route(articles, found))
    client.route(
        "CoherencePrior",
        {
            "entityCoverage": [
                {"period": f"2026-09-{d:02d} 00:00:00+00", "agencyKey": "mds", "articleCount": n}
                for d, n in prior
            ]
        },
    )
    client.route("CoherenceCounts", counts_route(tone, totals))
    return client


async def run(client, **kwargs):
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("catalog", AgencyCatalog(client))
    return await build_coherence_output(client, **kwargs)


# ── parâmetros ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"entity_id": "Q575545", "theme": "Saúde"}, {"entity_id": "  ", "theme": ""}],
)
async def test_exige_exatamente_um_entre_entity_id_e_theme(fake_client, kwargs):
    text = await get_message_coherence(fake_client, now=NOW, **kwargs)
    assert "exatamente um" in text
    fake_client.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("date_from", "date_to", "expected"),
    [
        ("2026-01-01", "2026-06-30", "92 dias"),
        ("2026-09-10", "2026-09-01", "anterior"),
        ("01/09/2026", "", "AAAA-MM-DD"),
        ("2026-10-01", "2026-10-10", "futuro"),
    ],
)
async def test_janela_invalida_devolve_o_motivo_sem_consultar(
    fake_client, date_from, date_to, expected
):
    text = await get_message_coherence(
        fake_client, entity_id="Q575545", date_from=date_from, date_to=date_to, now=NOW
    )
    assert "Parâmetro inválido" in text
    assert expected in text
    fake_client.execute.assert_not_awaited()


async def test_janela_padrao_d14_a_d1_em_brt(fake_client):
    scenario(fake_client)
    report, _ = await run(fake_client, entity_id="Q575545")

    (first,) = fake_client.calls("CoherenceArticles")
    assert first == {
        "filter": {
            "entityCanonical": ["Q575545"],
            "startDate": "2026-09-22T00:00:00-03:00",
            "endDate": "2026-10-06T00:00:00-03:00",
        },
        "page": 1,
    }
    assert report.window.days == 14
    assert report.params == {
        "entity_id": "Q575545",
        "theme": None,
        "agencies": None,
        "date_from": "2026-09-22",
        "date_to": "2026-10-05",
    }


async def test_so_date_from_usa_14_dias_limitados_a_ontem(fake_client):
    scenario(fake_client)
    report, _ = await run(fake_client, entity_id="Q575545", date_from="2026-09-30")
    assert (report.params["date_from"], report.params["date_to"]) == ("2026-09-30", "2026-10-05")


# ── fluxo por entidade ──────────────────────────────────────────────────────


async def test_relatorio_por_entidade_com_republicadoras_a_parte(fake_client):
    scenario(fake_client)
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert report.subject.label == "Bolsa Família"
    assert report.subject.resolved_by == "id"
    assert report.index_status == "scored"
    assert 1 <= report.index.level <= 5
    assert [a.agency_key for a in report.agencies] == ["mds", "saude", "mec"]
    assert report.agencies[0].agency_name == "Ministério do Desenvolvimento e Assistência Social"
    assert {r.agency_key for r in report.republishers.agencies} == {"agencia_brasil", "tvbrasil"}
    assert report.republishers.articles == 3
    assert report.sample.single_article_agencies == 1  # secom
    assert report.sample.found == len(ARTICLES)
    assert markdown.startswith("## Coerência de Mensagem — Bolsa Família (POLICY · `Q575545`)")
    assert "### Índice:" in markdown
    assert "### Republicadoras" in markdown
    republishers_part = markdown.split("### Republicadoras")[1]
    assert "agencia_brasil" in republishers_part
    agencies_part = markdown.split("### Por agência")[1].split("###")[0]
    assert "agencia_brasil" not in agencies_part


async def test_exclui_a_propria_entidade_e_as_dgb_do_catalogo(fake_client):
    scenario(fake_client)
    report, _ = await run(fake_client, entity_id="Q575545")

    anchors = {a.entity_id for a in report.shared_anchors}
    anchors |= {e.entity_id for a in report.agencies for e in a.exclusive_anchors}
    assert "Q575545" not in anchors
    assert "dgb_mds" not in anchors and "dgb_saude" not in anchors
    assert "dgb_cadastro-unico" in {a.entity_id for a in report.shared_anchors}


async def test_tom_por_aliases_de_contagem_agencia_rotulo(fake_client):
    scenario(fake_client)
    report, markdown = await run(fake_client, entity_id="Q575545")

    (variables,) = fake_client.calls("CoherenceCounts")
    filters = list(variables.values())
    assert len(filters) == 3 * 3  # 3 emissores × 3 rótulos (sem total: amostra completa)
    assert {(f["agencies"][0], f["sentiment"][0]) for f in filters} == {
        (a, lbl) for a in ("mds", "saude", "mec") for lbl in ("positive", "negative", "neutral")
    }
    assert all(f["entityCanonical"] == ["Q575545"] for f in filters)
    tone = next(d for d in report.dimensions if d.key == "tone")
    assert tone.status == "ok"
    assert tone.metric["coverage"] == pytest.approx(1.0)
    assert report.agencies[0].tone.positive == 3


async def test_tom_indisponivel_com_cobertura_abaixo_de_50_pct(fake_client):
    scenario(fake_client, tone={("mds", "positive"): 1})
    report, markdown = await run(fake_client, entity_id="Q575545")

    tone = next(d for d in report.dimensions if d.key == "tone")
    assert tone.status == "unavailable"
    assert tone.effective_weight is None
    assert "SENTIMENT_UNAVAILABLE" in {n.code for n in report.notices}
    assert "Tom" in markdown and "indisponível" in markdown
    assert report.status == "partial"


async def test_falha_do_tom_nao_derruba_a_tool(fake_client):
    scenario(fake_client)
    fake_client.route("CoherenceCounts", RuntimeError("timeout"))
    report, _ = await run(fake_client, entity_id="Q575545")

    tone = next(d for d in report.dimensions if d.key == "tone")
    assert tone.status == "unavailable"
    assert "timeout" in tone.detail
    assert report.index_status == "scored"


async def test_paginacao_found_600_busca_as_paginas_2_e_3(fake_client):
    scenario(fake_client, found=600)
    report, _ = await run(fake_client, entity_id="Q575545")

    assert sorted(v["page"] for v in fake_client.calls("CoherenceArticles")) == [1, 2, 3]
    assert report.sample.found == 600
    assert report.sample.fetched == 3 * len(ARTICLES)
    assert not report.sample.truncated
    assert "SAMPLE_TRUNCATED" not in {n.code for n in report.notices}


async def test_acima_de_1000_artigos_trunca_e_mede_o_tom_com_totais(fake_client):
    totals = {"mds": 400, "saude": 300, "mec": 200}
    tone = {(a, "positive"): n for a, n in totals.items()}
    scenario(fake_client, found=1200, tone=tone, totals=totals)
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert sorted(v["page"] for v in fake_client.calls("CoherenceArticles")) == [1, 2, 3, 4]
    assert report.sample.truncated
    notice = next(n for n in report.notices if n.code == "SAMPLE_TRUNCATED")
    assert "1000" in notice.message and "1200" in notice.message
    (variables,) = fake_client.calls("CoherenceCounts")
    totals_aliases = [f for f in variables.values() if "sentiment" not in f]
    # as 4 páginas repetem as linhas da fixture: secom (1 por página) vira emissor
    assert sorted(f["agencies"][0] for f in totals_aliases) == ["mds", "mec", "saude", "secom"]
    tone_dim = next(d for d in report.dimensions if d.key == "tone")
    assert tone_dim.metric["coverage"] == pytest.approx(1.0)


async def test_falha_das_paginas_seguintes_mantem_a_primeira(fake_client):
    scenario(fake_client)

    def handler(variables):
        if variables["page"] > 1:
            raise RuntimeError("página 2 caiu")
        return articles_route(found=600)(variables)

    fake_client.route("CoherenceArticles", handler)
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert report.sample.fetched == len(ARTICLES)
    assert report.status == "partial"
    notice = next(n for n in report.notices if n.code == "SAMPLE_TRUNCATED")
    assert "página 2 caiu" in notice.message


async def test_falha_da_consulta_de_artigos(fake_client):
    scenario(fake_client)
    fake_client.route("CoherenceArticles", RuntimeError("graphql fora do ar"))
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert report.status == "unavailable"
    assert report.index_status == "unavailable"
    assert "graphql fora do ar" in markdown
    assert not fake_client.calls("CoherenceCounts")


async def test_found_0_retorna_cedo_com_dica(fake_client):
    scenario(fake_client, articles=[])
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert report.status == "empty"
    assert report.index_status == "no_articles"
    assert "Nenhum artigo" in markdown and "92 dias" in markdown
    assert not fake_client.calls("CoherenceCounts")


async def test_entidade_inexistente(fake_client):
    scenario(fake_client, articles=[])
    fake_client.route("CoherenceEntity", {"entity": None})
    text = await get_message_coherence(fake_client, entity_id="Q999999999", now=NOW)

    assert "Entidade não encontrada" in text
    assert "gobus_resolve_entity" in text


async def test_voz_unica_e_insuficiente(fake_client):
    only_mds = [a for a in ARTICLES if a["agency"] in ("mds", "agencia_brasil")]
    scenario(fake_client, articles=only_mds)
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert report.index_status == "insufficient"
    assert report.index.level is None
    assert "voz única" in markdown
    assert not fake_client.calls("CoherenceCounts")  # sem 2 emissores, sem tom


async def test_resolucao_por_nome_escolhe_o_maior_volume_e_lista_alternativas(fake_client):
    scenario(fake_client)
    fake_client.route(
        "CoherenceEntitySearch",
        {
            "entitySearch": [
                {"entityId": "dgb_programa-pe-de-meia", "canonicalName": "Programa Pé-de-Meia",
                 "type": "POLICY", "articleCount": 0},
                {"entityId": "dgb_pe-de-meia", "canonicalName": "Pé-de-Meia", "type": "POLICY",
                 "articleCount": 827},
                {"entityId": "dgb_pe-de-meia", "canonicalName": "Pé-de-Meia", "type": "POLICY",
                 "articleCount": 827},
            ]
        },
    )  # fmt: skip
    report, markdown = await run(fake_client, entity_id="pé de meia")

    assert fake_client.calls("CoherenceEntitySearch") == [{"query": "pé de meia"}]
    assert not fake_client.calls("CoherenceEntity")
    assert report.subject.id == "dgb_pe-de-meia"
    assert report.subject.resolved_by == "search"
    assert report.subject.query == "pé de meia"
    assert [a.entity_id for a in report.subject.alternatives] == ["dgb_programa-pe-de-meia"]
    assert fake_client.calls("CoherenceArticles")[0]["filter"]["entityCanonical"] == [
        "dgb_pe-de-meia"
    ]
    assert "Programa Pé-de-Meia" in markdown  # alternativa listada


async def test_busca_sem_resultado(fake_client):
    scenario(fake_client)
    fake_client.route("CoherenceEntitySearch", {"entitySearch": []})
    text = await get_message_coherence(fake_client, entity_id="xyzzy", now=NOW)
    assert "Entidade não encontrada" in text


async def test_prior_com_taxa_alta_marca_inicio_truncado(fake_client):
    scenario(fake_client, prior=[(d, 2) for d in range(1, 21)])  # 40 artigos em 30 dias
    report, markdown = await run(fake_client, entity_id="Q575545")

    (prior_call,) = fake_client.calls("CoherencePrior")
    assert prior_call == {"id": "Q575545", "dateFrom": "2026-08-23", "dateTo": "2026-09-22"}
    assert report.prior.articles == 40
    assert report.prior.truncated_start
    timing = next(d for d in report.dimensions if d.key == "timing")
    assert "início truncado" in timing.detail
    assert "início truncado" in markdown


async def test_prior_baixo_nao_marca(fake_client):
    scenario(fake_client, prior=[(1, 1)])
    report, _ = await run(fake_client, entity_id="Q575545")
    assert report.prior.truncated_start is False


async def test_agencias_filtram_a_consulta_e_validam_pelo_catalogo(fake_client):
    scenario(fake_client)
    report, _ = await run(fake_client, entity_id="Q575545", agencies=["Saúde", "mds"])

    assert fake_client.calls("CoherenceArticles")[0]["filter"]["agencies"] == ["saude", "mds"]
    assert report.params["agencies"] == ["saude", "mds"]


async def test_agencia_invalida_devolve_sugestao_sem_buscar_artigos(fake_client):
    scenario(fake_client)
    text = await get_message_coherence(
        fake_client,
        entity_id="Q575545",
        agencies=["ms"],
        now=NOW,
        catalog=AgencyCatalog(fake_client),
    )
    assert "saude" in text
    assert not fake_client.calls("CoherenceArticles")


async def test_mock_ignorado_no_enquadramento(fake_client):
    mocked = [dict(a, summary="[MOCK] Resumo gerado para teste local — anuncia") for a in ARTICLES]
    scenario(fake_client, articles=mocked)
    report, markdown = await run(fake_client, entity_id="Q575545")

    assert report.sample.mock_summaries_ignored == len(ARTICLES)
    assert "[MOCK]" in markdown


async def test_defeso_na_janela_gera_aviso(fake_client):
    scenario(fake_client)
    report, markdown = await run(
        fake_client, entity_id="Q575545", date_from="2026-08-01", date_to="2026-09-30"
    )
    assert "ELECTORAL_BLACKOUT" in {n.code for n in report.notices}
    assert "defeso" in markdown

    scenario(fake_client)
    report, _ = await run(
        fake_client, entity_id="Q575545", date_from="2026-06-01", date_to="2026-06-30"
    )
    assert "ELECTORAL_BLACKOUT" not in {n.code for n in report.notices}


async def test_payload_valida_e_cabe_no_orcamento(fake_client):
    many = [
        art(f"ag{i:02d}", f"2026-09-{22 + d}T1{d}:00:00+00:00",
            [BOLSA, CADUNICO, ("Q9", "Cadastro", "POLICY", 0.5), (f"Q{i}x", f"Entidade exclusiva {i}", "ORG", 0.7)],  # noqa: E501
            "Governo anuncia pagamento")
        for i in range(20)
        for d in range(3)
    ]  # fmt: skip
    scenario(fake_client, articles=many, tone={})
    report, markdown = await run(fake_client, entity_id="Q575545")

    CoherenceReport.model_validate(json.loads(report.model_dump_json()))
    assert report.summary == markdown or len(report.summary.encode()) <= 6_144
    assert len(markdown.encode()) <= 5_120
    assert payload_size(report) <= 20_000
    assert len(report.agencies) == 12 and report.agencies_omitted == 8
    assert len(fake_client.calls("CoherenceCounts")[0]) == MAX_TONE_AGENCIES * 3


# ── fluxo por tema ──────────────────────────────────────────────────────────


def theme_scenario(client, *, classified, total):
    scenario(client)
    client.route("CoherenceThemes", {"themes": [{"label": lbl} for lbl in LABELS]})
    themes = {lbl: 0 for lbl in LABELS}
    themes["Desenvolvimento Social"] = classified

    def handler(variables):
        out = {}
        for key, filt in variables.items():
            if "sentiment" in filt:
                ((agency,), (label,)) = filt["agencies"], filt["sentiment"]
                found = TONE.get((agency, label), 0)
            elif "themeLabel" in filt:
                found = themes.get(filt["themeLabel"], 0)
            else:
                found = total
            out[f"c{key[1:]}"] = {"found": found}
        return out

    client.route("CoherenceCounts", handler)
    return client


async def test_tema_resolve_a_label_l1_e_filtra_por_themelabel(fake_client):
    theme_scenario(fake_client, classified=95, total=100)
    report, markdown = await run(fake_client, theme="desenvolvimento social")

    assert report.subject.kind == "theme"
    assert report.subject.label == "Desenvolvimento Social"
    assert report.subject.resolved_by == "taxonomy"
    first = fake_client.calls("CoherenceArticles")[0]["filter"]
    assert first["themeLabel"] == "Desenvolvimento Social"
    assert "entityCanonical" not in first
    assert not fake_client.calls("CoherencePrior")  # prior só no caminho por entidade
    assert "THEMES_UNCLASSIFIED" not in {n.code for n in report.notices}
    assert markdown.startswith("## Coerência de Mensagem — Desenvolvimento Social (tema)")


async def test_tema_com_classificacao_baixa_avisa_e_sugere_entity_id(fake_client):
    theme_scenario(fake_client, classified=30, total=100)
    report, markdown = await run(fake_client, theme="Desenvolvimento Social")

    notice = next(n for n in report.notices if n.code == "THEMES_UNCLASSIFIED")
    assert "30%" in notice.message
    assert "entity_id" in markdown
    assert report.status == "partial"


async def test_tema_por_prefixo_unico(fake_client):
    theme_scenario(fake_client, classified=95, total=100)
    report, _ = await run(fake_client, theme="Defesa")
    assert report.subject.label == "Defesa e Forças Armadas"


async def test_tema_inexistente_sugere_opcoes(fake_client):
    theme_scenario(fake_client, classified=95, total=100)
    text = await get_message_coherence(fake_client, theme="Saude publica xyz", now=NOW)
    assert "Tema não encontrado" in text
    assert "gobus://themes" in text
    assert not fake_client.calls("CoherenceArticles")


async def test_tema_cruzando_a_troca_de_classificador(fake_client):
    theme_scenario(fake_client, classified=95, total=100)
    report, _ = await run(fake_client, theme="Saúde", date_from="2026-09-15")
    assert "CLASSIFIER_CHANGED" in {n.code for n in report.notices}


# ── contrato da query gerada ────────────────────────────────────────────────


@pytest.mark.parametrize("n", [1, 2, 26, MAX_TONE_AGENCIES * 4])
def test_query_de_contagem_gerada_e_valida_contra_o_sdl(n):
    query = counts_query(n)
    document = parse(query)
    assert not validate(SCHEMA, document)
    (operation,) = document.definitions
    assert operation.operation.value == "query"
    assert operation.name.value == "CoherenceCounts"
    assert query.count("articles(limit: 1") == n
