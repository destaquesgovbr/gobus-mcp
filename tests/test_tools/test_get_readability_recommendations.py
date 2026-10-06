"""gobus_get_readability_recommendations: ranking e diagnóstico null-aware, janela efetiva,
amostra via ``articles`` (nunca ``search``) e payload pydantic separado do Markdown."""

from datetime import datetime

from gobus_mcp.calendario import BRT
from gobus_mcp.payloads.readability import ReadabilityReport
from gobus_mcp.tools.get_readability_recommendations import (
    build_readability_payload,
    get_readability_recommendations,
    render_readability_markdown,
)
from tests.conftest import route_catalog

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=BRT)
REQ_FROM, REQ_TO = "2026-07-07", "2026-10-04"  # closed_window(90) em 05/10
LOOKBACK_FROM = "2025-10-04"


def _row(period, key, count, flesch, wc=450.0, name=None):
    return {
        "period": f"{period}-01 00:00:00+00",
        "agencyKey": key,
        "agencyName": name or key.upper(),
        "articleCount": count,
        "avgReadabilityFlesch": flesch,
        "avgWordCount": wc if flesch is not None else None,
    }


RANKING_ROWS = [
    _row("2026-10", "secom", 150, 17.2),
    _row("2026-10", "cgu", 80, -1.2),
    _row("2026-10", "defesa", 200, -22.9, wc=800.0),
    _row("2026-10", "agencia_brasil", 300, 33.5, wc=473.0),
    _row("2026-10", "mec", 120, None),
]


def _route_window(client, by_from):
    client.route(
        "ReadabilityWindow",
        lambda v: {
            "agencyAnalytics": [
                r for r in by_from.get(v["dateFrom"], []) if r["agencyKey"] in v["agencies"]
            ]
        },
    )


def _article(uid, flesch, wc=500, title=None):
    return {
        "uniqueId": uid,
        "title": title or f"Artigo {uid}",
        "url": f"https://www.gov.br/{uid}",
        "publishedAt": "2026-09-20T10:00:00-03:00",
        "features": {"readabilityFlesch": flesch, "wordCount": wc},
    }


def _route_articles(client, articles):
    client.route(
        "ReadabilityArticles",
        {"articles": {"found": len(articles), "articles": articles}},
    )


async def _md(client, **kwargs):
    return await get_readability_recommendations(client=client, now=NOW, **kwargs)


# ── ranking geral ───────────────────────────────────────────────────────────


async def test_ranking_ordena_por_flesch_limitado_com_nomes_do_catalogo(fake_client):
    route_catalog(fake_client)
    _route_window(fake_client, {REQ_FROM: RANKING_ROWS, LOOKBACK_FROM: RANKING_ROWS})

    result = await _md(fake_client, agency_key=None)

    order = [
        result.index("Agência Brasil"),
        result.index("Secretaria de Comunicação Social"),
        result.index("Controladoria-Geral da União"),  # 0.0 (bruto -1.2)
        result.index("Ministério da Defesa"),  # 0.0 (bruto -22.9)
    ]
    assert order == sorted(order)
    assert "-22.9" in result  # valor bruto aparece quando houve clamp
    assert "muito difícil" in result


async def test_ranking_nunca_mostra_zero_para_nulo_e_lista_sem_dado(fake_client):
    route_catalog(fake_client)
    _route_window(fake_client, {REQ_FROM: RANKING_ROWS, LOOKBACK_FROM: RANKING_ROWS})

    result = await _md(fake_client, agency_key=None)

    table, _, rest = result.partition("Sem dado de legibilidade")
    assert "Ministério da Educação" not in table
    assert "Ministério da Educação" in rest
    mec_line = next(line for line in result.splitlines() if "Ministério da Educação" in line)
    assert "0.0" not in mec_line


async def test_ranking_benchmark_dinamico_sem_valor_fixo(fake_client):
    route_catalog(fake_client)
    rows = [_row("2026-10", "agencia_brasil", 300, 41.2), _row("2026-10", "saude", 90, 20.0)]
    _route_window(fake_client, {REQ_FROM: rows, LOOKBACK_FROM: rows})

    result = await _md(fake_client, agency_key=None)

    assert "33.5" not in result
    benchmark = next(line for line in result.splitlines() if "Benchmark" in line)
    assert "41.2" in benchmark


async def test_ranking_usa_agencias_ativas_do_catalogo(fake_client):
    route_catalog(fake_client, active=["agencia_brasil", "saude", "pf"])
    _route_window(fake_client, {REQ_FROM: RANKING_ROWS, LOOKBACK_FROM: RANKING_ROWS})

    await _md(fake_client, agency_key=None, days=90)

    (top,) = fake_client.calls("CatalogTopAgencies")
    assert top["days"] == 90
    first = fake_client.calls("ReadabilityWindow")[0]
    assert set(first["agencies"]) == {"agencia_brasil", "saude", "pf"}


async def test_ranking_com_janela_deslocada_avisa_dados_ate(fake_client):
    route_catalog(fake_client)
    empty = [_row("2026-09", "saude", 90, None), _row("2026-10", "agencia_brasil", 30, None)]
    june = [_row("2026-06", "saude", 100, 30.0), _row("2026-06", "agencia_brasil", 200, 35.0)]
    _route_window(fake_client, {REQ_FROM: empty, LOOKBACK_FROM: june + empty, "2026-04-02": june})

    report = await build_readability_payload(fake_client, agency_key=None, now=NOW)
    result = render_readability_markdown(report)

    assert report.window_shifted is True
    assert report.status == "partial"
    assert str(report.effective_window.start) == "2026-04-02"
    assert "Janela efetiva" in result
    assert "dados até 06/2026" in result
    assert "Ministério da Saúde" in result


async def test_ranking_sem_dado_no_historico_fica_indisponivel(fake_client):
    route_catalog(fake_client)
    empty = [_row("2026-09", "saude", 90, None)]
    _route_window(fake_client, {REQ_FROM: empty, LOOKBACK_FROM: empty})

    report = await build_readability_payload(fake_client, agency_key=None, now=NOW)
    result = render_readability_markdown(report)

    assert report.status == "unavailable"
    assert report.effective_window is None
    assert "indisponível" in result
    assert "0.0" not in result


# ── diagnóstico de agência ──────────────────────────────────────────────────


AGENCY_ROWS = [
    _row("2026-10", "saude", 200, 28.0, wc=520.0),
    _row("2026-10", "agencia_brasil", 300, 33.5, wc=473.0),
]


async def test_agencia_usa_articles_e_escolhe_pior_e_melhor_no_cliente(fake_client):
    route_catalog(fake_client)
    _route_window(fake_client, {REQ_FROM: AGENCY_ROWS, LOOKBACK_FROM: AGENCY_ROWS})
    _route_articles(
        fake_client,
        [
            _article("a1", 12.0, title="Artigo mediano"),
            _article("a2", -40.2, wc=900, title="Artigo técnico denso"),
            _article("a3", 55.0, wc=300, title="Artigo claro"),
            _article("a4", None, title="Artigo sem métrica"),
        ],
    )

    report = await build_readability_payload(fake_client, agency_key="saude", now=NOW)
    result = render_readability_markdown(report)

    assert report.mode == "agency"
    assert report.worst_article.unique_id == "a2"
    assert report.best_article.unique_id == "a3"
    (call,) = fake_client.calls("ReadabilityArticles")
    assert call["agencies"] == ["saude"]
    assert call["startDate"] == "2026-07-07T00:00:00-03:00"
    assert call["endDate"] == "2026-10-05T00:00:00-03:00"
    assert "Ministério da Saúde" in result
    assert "Artigo técnico denso" in result and "-40.2" in result
    assert "Artigo claro" in result
    assert "Recomendações" in result
    benchmark = next(line for line in result.splitlines() if "Benchmark" in line)
    assert "33.5" in benchmark


async def test_agencia_invalida_sugere_codigo_sem_consultar_metricas(fake_client):
    route_catalog(fake_client)

    trabalho = await _md(fake_client, agency_key="trabalho")
    ms = await _md(fake_client, agency_key="ms")

    assert "trabalho-e-emprego" in trabalho
    assert "saude" in ms
    assert fake_client.calls("ReadabilityWindow") == []


async def test_agencia_sem_dado_nao_vira_zero(fake_client):
    route_catalog(fake_client)
    rows = [_row("2026-10", "saude", 200, None), _row("2026-10", "agencia_brasil", 300, None)]
    _route_window(fake_client, {REQ_FROM: rows, LOOKBACK_FROM: rows})

    result = await _md(fake_client, agency_key="saude")

    assert "indisponível" in result
    assert "0.0" not in result
    assert fake_client.calls("ReadabilityArticles") == []  # sem janela efetiva, sem amostra


async def test_date_to_define_o_fim_da_janela_pedida(fake_client):
    route_catalog(fake_client)
    june = [_row("2026-06", "saude", 100, 30.0), _row("2026-06", "agencia_brasil", 200, 35.0)]
    _route_window(fake_client, {"2026-04-02": june, "2025-06-30": june})
    _route_articles(fake_client, [_article("a1", 30.0)])

    report = await build_readability_payload(
        fake_client, agency_key="saude", date_to="2026-06-30", now=NOW
    )

    first = fake_client.calls("ReadabilityWindow")[0]
    assert (first["dateFrom"], first["dateTo"]) == ("2026-04-02", "2026-07-01")  # MONTH: exclusivo
    assert report.window_shifted is False
    assert report.params["date_to"] == "2026-06-30"


async def test_date_to_invalida_devolve_erro(fake_client):
    route_catalog(fake_client)
    result = await _md(fake_client, agency_key="saude", date_to="30/06/2026")
    assert "date_to" in result


# ── payload ─────────────────────────────────────────────────────────────────


async def test_payload_serializa_em_camel_case_e_summary_e_o_markdown(fake_client):
    route_catalog(fake_client)
    _route_window(fake_client, {REQ_FROM: AGENCY_ROWS, LOOKBACK_FROM: AGENCY_ROWS})
    _route_articles(fake_client, [_article("a1", 20.0)])

    report = await build_readability_payload(fake_client, agency_key="saude", now=NOW)

    assert isinstance(report, ReadabilityReport)
    assert report.summary == render_readability_markdown(report)
    data = report.model_dump(mode="json")
    for key in ("schemaVersion", "effectiveWindow", "worstArticle", "dataStatus", "coverage"):
        assert key in data
    assert data["kind"] == "gobus.readability"
    assert data["scale"] == "flesch_en_textstat"
    assert [b["key"] for b in data["bands"]] == ["very_hard", "hard", "medium", "easy"]
    assert ReadabilityReport.model_validate(data) == report
