"""gobus_score_article: scored | partial | refused, benchmark ancorado em publishedAt−90d
(mediana no cliente, sampleSize, null se n<10) e nomes do catálogo."""

from datetime import datetime

from gobus_mcp.calendario import BRT
from gobus_mcp.payloads.scorecard import ScoreReport
from gobus_mcp.tools.score_article import (
    build_score_payload,
    render_score_markdown,
    score_article,
)
from tests.conftest import route_catalog

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=BRT)


def _article(flesch=65.0, word_count=400, entities=None, agency="pf", agency_name="pf"):
    return {
        "article": {
            "uniqueId": "a1",
            "title": "Operação desarticula quadrilha",
            "url": "https://www.gov.br/pf/a1",
            "agency": agency,
            "agencyName": agency_name,
            "publishedAt": "2026-06-01T10:00:00Z",
            "features": {
                "readabilityFlesch": flesch,
                "wordCount": word_count,
                "entities": entities if entities is not None else [{"type": "ORG"}] * 2,
            },
        }
    }


def _sample(n, *, wc=420, flesch=30.0, start_day=3):
    return {
        "found": n,
        "articles": [
            {
                "uniqueId": f"s{i}",
                "publishedAt": f"2026-05-{start_day + i:02d}T12:00:00Z",
                "features": {"readabilityFlesch": flesch, "wordCount": wc},
            }
            for i in range(n)
        ],
    }


def _route(client, article, ag=None, ab=None):
    route_catalog(client)
    client.route("ScoreArticle", article)
    client.route(
        "ScoreArticleBenchmark",
        {"ag": ag if ag is not None else _sample(12), "ab": ab if ab is not None else _sample(20)},
    )
    return client


async def test_sem_flesch_e_sem_word_count_recusa_a_nota(fake_client):
    _route(fake_client, _article(flesch=None, word_count=None))

    report = await build_score_payload(fake_client, "a1", now=NOW)
    md = render_score_markdown(report)

    assert report.score_status == "refused"
    assert report.status == "unavailable"
    assert report.overall is None
    assert "Nota indisponível" in md
    assert "5.6" not in md


async def test_sem_word_count_tambem_recusa(fake_client):
    _route(fake_client, _article(flesch=40.0, word_count=None))

    report = await build_score_payload(fake_client, "a1", now=NOW)

    assert report.score_status == "refused"
    assert "Nota indisponível" in render_score_markdown(report)


async def test_sem_features_recusa(fake_client):
    art = _article()
    art["article"]["features"] = None
    _route(fake_client, art)

    md = await score_article("a1", fake_client, now=NOW)

    assert "Nota indisponível" in md


async def test_nota_com_tres_dimensoes(fake_client):
    # legibilidade 65 → 10; concisão 400/420 = 0,95 → 8; densidade 2/400·100 = 0,5 → 4
    _route(fake_client, _article(), ag=_sample(12, wc=420))

    report = await build_score_payload(fake_client, "a1", now=NOW)
    md = render_score_markdown(report)

    assert report.score_status == "scored"
    assert report.status == "ok"
    assert report.overall == 8.2
    assert "8.2/10" in md
    dims = {d.key: d.score for d in report.dimensions}
    assert dims == {"readability": 10.0, "conciseness": 8.0, "entity_density": 4.0}


async def test_benchmark_com_menos_de_10_artigos_fica_nulo_e_nota_parcial(fake_client):
    _route(fake_client, _article(), ag=_sample(5, wc=420))

    report = await build_score_payload(fake_client, "a1", now=NOW)
    md = render_score_markdown(report)

    assert report.benchmark.sample_size == 5
    assert report.benchmark.median_word_count is None
    assert report.score_status == "partial"
    assert report.status == "partial"
    # renormalizada: (10·0,5 + 4·0,2) / 0,7
    assert report.overall == 8.3
    assert "parcial" in md.lower()


async def test_benchmark_ancorado_na_publicacao_menos_90_dias(fake_client):
    _route(fake_client, _article())

    await build_score_payload(fake_client, "a1", now=NOW)

    (call,) = fake_client.calls("ScoreArticleBenchmark")
    assert call["agencies"] == ["pf"]
    assert call["startDate"] == "2026-03-03T10:00:00+00:00"
    assert call["endDate"] == "2026-06-01T10:00:00+00:00"


async def test_benchmark_usa_mediana_janela_real_e_agencia_brasil(fake_client):
    ag = _sample(11, wc=400, start_day=3)
    ag["articles"][0]["features"]["wordCount"] = 5000  # outlier: a mediana resiste
    ag["articles"].append(  # o próprio artigo nunca entra na amostra
        {
            "uniqueId": "a1",
            "publishedAt": "2026-05-30T12:00:00Z",
            "features": {"readabilityFlesch": 1.0, "wordCount": 1},
        }
    )
    _route(fake_client, _article(), ag=ag, ab=_sample(15, wc=473, flesch=35.0))

    report = await build_score_payload(fake_client, "a1", now=NOW)
    md = render_score_markdown(report)

    bench = report.benchmark
    assert bench.sample_size == 11
    assert bench.median_word_count == 400
    assert (str(bench.window.start), str(bench.window.end)) == ("2026-05-03", "2026-05-13")
    assert report.reference_benchmark.median_word_count == 473
    assert report.reference_benchmark.median_flesch == 35.0
    assert "Agência Brasil" in md


async def test_cabecalho_usa_nome_do_catalogo(fake_client):
    _route(fake_client, _article(agency="pf", agency_name="pf"))

    md = await score_article("a1", fake_client, now=NOW)

    assert "Polícia Federal" in md
    assert "[pf] pf" not in md


async def test_flesch_negativo_e_limitado(fake_client):
    _route(fake_client, _article(flesch=-30.0))

    report = await build_score_payload(fake_client, "a1", now=NOW)
    md = render_score_markdown(report)

    dims = {d.key: d for d in report.dimensions}
    assert dims["readability"].score == 0.0
    assert "valor bruto -30.0" in md


async def test_artigo_nao_encontrado(fake_client):
    route_catalog(fake_client)
    fake_client.route("ScoreArticle", {"article": None})

    md = await score_article("zz", fake_client, now=NOW)

    assert "não encontrado" in md.lower()
    assert fake_client.calls("ScoreArticleBenchmark") == []


async def test_payload_camel_case_e_summary(fake_client):
    _route(fake_client, _article())

    report = await build_score_payload(fake_client, "a1", now=NOW)

    assert isinstance(report, ScoreReport)
    assert report.summary == render_score_markdown(report)
    data = report.model_dump(mode="json")
    assert data["kind"] == "gobus.scorecard"
    for key in ("scoreStatus", "referenceBenchmark", "dimensions", "schemaVersion"):
        assert key in data
    assert data["benchmark"]["sampleSize"] == 12
    assert ScoreReport.model_validate(data) == report


# ── semáforos, sugestões e comparação (app ui://article-scorecard) ─────────


def _titled(sample: dict, prefix: str, flesch: list[float | None]) -> dict:
    """Ids ``<prefix><i>`` e títulos; os primeiros artigos recebem os Flesch dados."""
    for i, art in enumerate(sample["articles"]):
        art["uniqueId"] = f"{prefix}{i}"
        art["title"] = f"Título {prefix}{i}"
        if i < len(flesch):
            art["features"]["readabilityFlesch"] = flesch[i]
    return sample


def _route_two(client, articles: dict[str, dict], ag=None, ab=None):
    """Dois artigos (``ScoreArticle`` por ``uniqueId``) com o mesmo benchmark."""
    route_catalog(client)
    client.route("ScoreArticle", lambda v: {"article": articles.get(v["uniqueId"])})
    client.route(
        "ScoreArticleBenchmark",
        {"ag": ag if ag is not None else _sample(12), "ab": ab if ab is not None else _sample(20)},
    )
    return client


async def test_semaforo_por_dimensao_e_da_nota(fake_client):
    # 10 → verde; 8 → verde; 4 → amarelo (limiares no Python, não no JS)
    _route(fake_client, _article(), ag=_sample(12, wc=420))

    report = await build_score_payload(fake_client, "a1", now=NOW)

    lights = {d.key: d.light for d in report.dimensions}
    assert lights == {"readability": "green", "conciseness": "green", "entity_density": "yellow"}
    assert report.overall_light == "green"
    data = report.model_dump(mode="json")
    assert data["overallLight"] == "green"
    assert data["dimensions"][0]["light"] == "green"


async def test_nota_recusada_tem_semaforos_cinza(fake_client):
    _route(fake_client, _article(flesch=None, word_count=None))

    report = await build_score_payload(fake_client, "a1", now=NOW)

    assert {d.light for d in report.dimensions} == {"gray"}
    assert report.overall_light == "gray"


async def test_semaforo_vermelho_abaixo_de_4(fake_client):
    _route(fake_client, _article(flesch=10.0, word_count=900, entities=[]), ag=_sample(12, wc=400))

    report = await build_score_payload(fake_client, "a1", now=NOW)

    lights = {d.key: d.light for d in report.dimensions}
    assert lights["readability"] == "red"  # Flesch 10 → 2,0
    assert lights["conciseness"] == "red"  # 900/400 → 2,0
    assert report.overall_light == "red"


async def test_sugere_ate_2_comparacoes_com_o_maior_flesch_de_cada_amostra(fake_client):
    ag = _titled(_sample(12), "ag", [30.0, 61.0, 45.0])
    ab = _titled(_sample(15, flesch=35.0), "ab", [40.0, 72.0])
    ag["articles"].append(  # o próprio artigo nunca é sugerido
        {"uniqueId": "a1", "title": "Ele mesmo", "publishedAt": "2026-05-30T12:00:00Z",
         "features": {"readabilityFlesch": 99.0, "wordCount": 300}}
    )  # fmt: skip
    _route(fake_client, _article(), ag=ag, ab=ab)

    report = await build_score_payload(fake_client, "a1", now=NOW)

    own, reference = report.suggested_comparisons
    assert (own.unique_id, own.title, own.agency_key, own.flesch) == (
        "ag1",
        "Título ag1",
        "pf",
        61.0,
    )
    assert (reference.unique_id, reference.agency_key, reference.flesch) == (
        "ab1",
        "agencia_brasil",
        72.0,
    )
    assert "Polícia Federal" in own.reason and "Agência Brasil" in reference.reason
    md = render_score_markdown(report)
    assert "`ag1`" in md and "`ab1`" in md and "compare_with" in md


async def test_sem_titulo_na_amostra_a_sugestao_usa_o_id(fake_client):
    _route(fake_client, _article())

    report = await build_score_payload(fake_client, "a1", now=NOW)

    assert all(s.title == s.unique_id for s in report.suggested_comparisons)


async def test_compare_with_pontua_os_dois_artigos(fake_client):
    other = _article(flesch=20.0, word_count=700, agency="saude", agency_name="saude")
    other["article"]["uniqueId"] = "b2"
    other["article"]["title"] = "Portaria regulamenta repasses"
    _route_two(fake_client, {"a1": _article()["article"], "b2": other["article"]})

    report = await build_score_payload(fake_client, "a1", compare_with="b2", now=NOW)

    assert report.params == {"unique_id": "a1", "compare_with": "b2"}
    assert report.article.unique_id == "a1"
    cmp = report.comparison
    assert cmp is not None and report.comparison_error is None
    assert cmp.article.unique_id == "b2"
    assert cmp.article.agency_name == "Ministério da Saúde"
    assert cmp.score_status in ("scored", "partial")
    assert {d.key for d in cmp.dimensions} == {"readability", "conciseness", "entity_density"}
    assert {c["uniqueId"] for c in fake_client.calls("ScoreArticle")} == {"a1", "b2"}
    md = render_score_markdown(report)
    assert "## Comparação" in md and "Portaria regulamenta repasses" in md
    assert report.summary == md
    data = report.model_dump(mode="json")
    assert data["comparison"]["article"]["uniqueId"] == "b2"


async def test_compare_with_inexistente_avisa_sem_derrubar_a_nota(fake_client):
    _route_two(fake_client, {"a1": _article()["article"]})

    report = await build_score_payload(fake_client, "a1", compare_with="zz", now=NOW)

    assert report.score_status == "scored"
    assert report.comparison is None
    assert "zz" in report.comparison_error
    assert "Comparação indisponível" in render_score_markdown(report)


async def test_compare_with_igual_ao_artigo_e_ignorado(fake_client):
    _route(fake_client, _article())

    report = await build_score_payload(fake_client, "a1", compare_with="a1", now=NOW)

    assert report.comparison is None
    assert report.comparison_error
    assert len(fake_client.calls("ScoreArticle")) == 1
