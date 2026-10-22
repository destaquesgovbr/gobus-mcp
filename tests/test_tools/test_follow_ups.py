"""Rodapé "Para explorar": até 3 chamadas concretas (argumentos tirados do resultado), em até
400 B, nas tools de texto. As 4 tools de MCP App não têm rodapé (o ``summary`` é o
``fit_summary`` do conteúdo; ver ``test_apps_wire``)."""

import re
from datetime import date

import pytest

from gobus_mcp.formatting import FOLLOW_UPS_MAX, FOLLOW_UPS_MAX_BYTES, FOLLOW_UPS_TITLE
from gobus_mcp.tools.detect_trends import detect_trends
from gobus_mcp.tools.get_agency_summary import get_agency_summary
from gobus_mcp.tools.get_article import get_article
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from gobus_mcp.tools.get_message_coherence import get_message_coherence
from gobus_mcp.tools.get_message_coherence import parse_params as parse_coherence_params
from gobus_mcp.tools.get_policy_lifecycle import get_policy_lifecycle
from gobus_mcp.tools.search_news import search_news
from tests.conftest import route_catalog
from tests.test_tools import test_entity_network as network_fx
from tests.test_tools import test_entity_profile as profile_fx
from tests.test_tools import test_get_message_coherence as coherence_fx
from tests.test_tools import test_get_policy_lifecycle as policy_fx

TODAY = date(2026, 10, 5)


def footer(markdown: str) -> str:
    """O rodapé (do título ao fim); falha se não houver."""
    assert FOLLOW_UPS_TITLE in markdown, markdown[-500:]
    part = markdown[markdown.index(FOLLOW_UPS_TITLE) :]
    assert markdown.rstrip().endswith(part.rstrip()), "o rodapé fecha a resposta"
    return part


def calls(markdown: str) -> list[str]:
    """Chamadas do rodapé, na ordem."""
    return re.findall(r"^- `(gobus_[a-z_]+\(.*?\))`", footer(markdown), flags=re.MULTILINE)


def check_budget(markdown: str) -> None:
    part = footer(markdown)
    assert len(part.encode()) <= FOLLOW_UPS_MAX_BYTES
    assert 1 <= len(calls(markdown)) <= FOLLOW_UPS_MAX


# ── search_news ─────────────────────────────────────────────────────────────


def _search(found=45, page=1):
    return {
        "search": {
            "articles": [
                {
                    "uniqueId": f"u{i}",
                    "title": f"Notícia {i}",
                    "agency": "mec" if i else "saude",
                    "agencyName": None,
                    "publishedAt": "2026-10-03T12:00:00-03:00",
                    "summary": "Resumo.",
                    "url": f"https://www.gov.br/x/{i}",
                    "features": None,
                }
                for i in range(3)
            ],
            "found": found,
            "page": page,
        }
    }


async def test_search_news_sugere_ler_resumo_do_orgao_e_proxima_pagina(fake_client):
    fake_client.route("SearchNews", _search())

    md = await search_news("Pé-de-Meia", fake_client, date_from="2026-10-01", date_to="2026-10-04")

    check_budget(md)
    assert calls(md) == [
        'gobus_get_article(unique_id="u0")',
        'gobus_get_agency_summary(agency_key="mec")',  # o órgão que mais aparece
        'gobus_search_news(query="Pé-de-Meia", date_from="2026-10-01", '
        'date_to="2026-10-04", page=2)',
    ]


async def test_search_news_ultima_pagina_sugere_resolver_a_entidade(fake_client):
    fake_client.route("SearchNews", _search(found=3))

    md = await search_news("Pé-de-Meia", fake_client)

    assert calls(md)[-1] == 'gobus_resolve_entity(query="Pé-de-Meia")'


async def test_search_news_sem_resultado_nao_tem_rodape(fake_client):
    fake_client.route("SearchNews", {"search": {"articles": [], "found": 0}})

    md = await search_news("xyz", fake_client)

    assert FOLLOW_UPS_TITLE not in md


# ── get_article ─────────────────────────────────────────────────────────────


async def test_get_article_sugere_nota_entidade_e_orgao(fake_client):
    route_catalog(fake_client)
    fake_client.route(
        "GetArticle",
        {
            "article": {
                "uniqueId": "x1",
                "title": "Pé-de-Meia paga parcela",
                "content": "Corpo.",
                "agency": "mec",
                "agencyName": "mec",
                "publishedAt": "2026-10-01T10:00:00Z",
                "url": "https://www.gov.br/x1",
                "tags": [],
                "features": {
                    "wordCount": 300,
                    "readabilityFleschPtbr": 20.0,
                    "entities": [
                        {"text": "Brasil", "type": "LOC", "count": 4, "canonicalId": "Q155"},
                        {"text": "sem id", "type": "ORG", "count": 3, "canonicalId": None},
                        {
                            "text": "Pé-de-Meia",
                            "type": "POLICY",
                            "count": 2,
                            "canonicalId": "dgb_pe-de-meia",
                        },
                    ],
                },
            }
        },
    )

    md = await get_article("x1", fake_client)

    check_budget(md)
    assert calls(md) == [
        'gobus_score_article(unique_id="x1")',
        'gobus_get_entity_profile(entity_name="dgb_pe-de-meia")',  # genérica e sem id: fora
        'gobus_get_agency_summary(agency_key="mec")',
    ]


# ── get_agency_summary e detect_trends ──────────────────────────────────────

THEME = {
    "themeLabel": "Educação",
    "windowCount": 42,
    "baselineDailyAvg": 3.0,
    "growthScore": 2.0,
    "topArticles": [
        {
            "uniqueId": "a1",
            "title": "Enem 2026",
            "agencyName": "mec",
            "publishedAt": "2026-10-01",
            "url": "https://www.gov.br/a1",
        }
    ],
}


def _route_coverage(client):
    client.route(
        "ThemeCoverage",
        {"topThemes": [{"label": "Educação", "count": 900}], "analyticsKpis": {"total": 1000}},
    )


async def test_agency_summary_sugere_artigo_legibilidade_e_serie(fake_client):
    route_catalog(fake_client)
    _route_coverage(fake_client)
    fake_client.route(
        "AgencySummaryAnalytics",
        {"agencyAnalytics": [{"period": "2026-09-01", "agencyKey": "mec", "articleCount": 42}]},
    )
    fake_client.route("AgencySummaryTrends", {"trendingThemes": [THEME]})

    md = await get_agency_summary("mec", fake_client, today=TODAY)

    check_budget(md)
    assert calls(md) == [
        'gobus_get_article(unique_id="a1")',
        'gobus_get_readability_recommendations(agency_key="mec")',
        'gobus_get_agency_analytics(agencies=["mec"], date_from="2026-09-05", '
        'date_to="2026-10-04", granularity="WEEK")',
    ]


async def test_detect_trends_sugere_artigo_busca_do_tema_e_forecast(fake_client):
    route_catalog(fake_client)
    _route_coverage(fake_client)
    fake_client.route("TrendingThemes", {"trendingThemes": [THEME]})

    md = await detect_trends(fake_client, agency_key="mec", today=TODAY)

    check_budget(md)
    assert calls(md) == [
        'gobus_get_article(unique_id="a1")',
        'gobus_search_news(query="Educação", agency_key="mec", date_from="2026-09-28", '
        'date_to="2026-10-04")',
        "gobus_forecast_trends()",
    ]


async def test_detect_trends_sem_temas_sugere_anomalias_e_limiar_menor(fake_client):
    route_catalog(fake_client)
    _route_coverage(fake_client)
    fake_client.route("TrendingThemes", {"trendingThemes": []})

    md = await detect_trends(fake_client, today=TODAY)

    assert calls(md) == [
        "gobus_detect_anomalies()",
        "gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.2)",
    ]


# ── get_policy_lifecycle ────────────────────────────────────────────────────


async def test_policy_lifecycle_sugere_perfil_coerencia_no_pico_e_artigo(fake_client):
    policy_fx._route(fake_client)

    md = await get_policy_lifecycle("Pé-de-Meia", fake_client, today=TODAY)

    check_budget(md)
    assert calls(md) == [
        'gobus_get_entity_profile(entity_name="dgb_pe-de-meia")',
        'gobus_get_message_coherence(entity_id="dgb_pe-de-meia", date_from="2024-03-01", '
        'date_to="2024-03-31")',
        'gobus_get_article(unique_id="p1")',
    ]


def _coherence_calls(markdown: str) -> list[str]:
    return [c for c in calls(markdown) if c.startswith("gobus_get_message_coherence(")]


def _call_args(call: str) -> dict[str, str]:
    return dict(re.findall(r'(\w+)="([^"]*)"', call))


async def test_policy_lifecycle_pico_no_mes_corrente_limita_a_coerencia_a_ontem(fake_client):
    # política nova: toda a cobertura no mês corrente (parcial), então o pico é ele; o fim
    # do mês (31/10) está no futuro e a coerência recusaria a chamada
    today = date(2026, 10, 21)
    coverage = {"entityCoverage": [policy_fx._point("2026-10", "mec", "MEC", 12)]}
    policy_fx._route(fake_client, coverage=coverage)

    md = await get_policy_lifecycle("Pé-de-Meia", fake_client, today=today)

    check_budget(md)
    (call,) = _coherence_calls(md)
    assert call == (
        'gobus_get_message_coherence(entity_id="dgb_pe-de-meia", date_from="2026-10-01", '
        'date_to="2026-10-20")'
    )
    args = _call_args(call)
    params = parse_coherence_params(
        args["entity_id"], None, None, args["date_from"], args["date_to"], today=today
    )
    assert params.window.end == date(2026, 10, 20)  # D−1: a chamada sugerida é válida


async def test_policy_lifecycle_pico_no_mes_corrente_no_dia_1_nao_sugere_coerencia(fake_client):
    # no dia 1, o mês de pico ainda não tem dia fechado: não há janela válida para sugerir
    coverage = {"entityCoverage": [policy_fx._point("2026-10", "mec", "MEC", 3)]}
    policy_fx._route(fake_client, coverage=coverage)

    md = await get_policy_lifecycle("Pé-de-Meia", fake_client, today=date(2026, 10, 1))

    check_budget(md)
    assert _coherence_calls(md) == []
    assert calls(md)[0] == 'gobus_get_entity_profile(entity_name="dgb_pe-de-meia")'


async def test_policy_lifecycle_cita_o_pico_com_link(fake_client):
    policy_fx._route(fake_client)

    md = await get_policy_lifecycle("Pé-de-Meia", fake_client, today=TODAY)

    assert "- [Pé-de-Meia paga primeira parcela](https://www.gov.br/p1) — " in md


# ── get_message_coherence ───────────────────────────────────────────────────


async def test_coherence_por_entidade_sugere_perfil_busca_e_rede(fake_client):
    coherence_fx.scenario(fake_client)

    md = await get_message_coherence(fake_client, entity_id="Q575545", now=coherence_fx.NOW)

    check_budget(md)
    assert calls(md) == [
        'gobus_get_entity_profile(entity_name="Q575545", date_from="2026-09-22", '
        'date_to="2026-10-05")',
        'gobus_search_news(query="Bolsa Família", agency_key="mds", date_from="2026-09-22", '
        'date_to="2026-10-05")',
        'gobus_get_entity_network(entity_id="Q575545")',
    ]


async def test_coherence_rodape_sobrevive_ao_corte_do_summary(fake_client):
    from gobus_mcp.analytics.render import SUMMARY_MAX_BYTES
    from gobus_mcp.tools.get_message_coherence import build_coherence_output

    coherence_fx.scenario(fake_client)

    report, md = await build_coherence_output(
        fake_client, entity_id="Q575545", now=coherence_fx.NOW
    )

    assert FOLLOW_UPS_TITLE in report.summary
    assert len(report.summary.encode()) <= SUMMARY_MAX_BYTES
    assert footer(md) == footer(report.summary)


async def test_coherence_entrada_invalida_nao_tem_rodape(fake_client):
    md = await get_message_coherence(fake_client, now=coherence_fx.NOW)
    assert FOLLOW_UPS_TITLE not in md


# ── rede e perfil ───────────────────────────────────────────────────────────


async def test_rede_depth1_sugere_perfil_rede_do_vizinho_e_segundo_grau(fake_client):
    network_fx._route(fake_client)

    md = await get_entity_network(network_fx.FOCUS, fake_client)

    check_budget(md)
    assert calls(md) == [
        'gobus_get_entity_profile(entity_name="dgb_pe-de-meia")',
        'gobus_get_entity_network(entity_id="Q4294522")',
        'gobus_get_entity_network(entity_id="dgb_pe-de-meia", depth=2)',
    ]


async def test_rede_depth2_sugere_artigos_que_citam_os_dois(fake_client):
    network_fx._route(fake_client)

    md = await get_entity_network(network_fx.FOCUS, fake_client, depth=2)

    check_budget(md)
    assert calls(md)[-1] == 'gobus_search_news(query="Pé-de-Meia Ministério da Educação")'


async def test_perfil_sugere_rede_busca_no_orgao_e_ciclo_da_politica(fake_client):
    profile_fx._route(fake_client)

    md = await get_entity_profile(
        profile_fx.ID, fake_client, date_from="2026-01-01", today=profile_fx.TODAY
    )

    check_budget(md)
    assert calls(md) == [
        'gobus_get_entity_network(entity_id="dgb_pe-de-meia")',
        'gobus_search_news(query="Pé-de-Meia", agency_key="mec", date_from="2026-01-01")',
        'gobus_get_policy_lifecycle(policy_name="Pé-de-Meia")',  # type POLICY
    ]


async def test_perfil_nao_encontrado_nao_tem_rodape(fake_client):
    profile_fx._route(fake_client, EntityNode={"entity": None})

    md = await get_entity_profile(profile_fx.ID, fake_client, today=profile_fx.TODAY)

    assert FOLLOW_UPS_TITLE not in md


# ── tools de MCP App: sem rodapé ────────────────────────────────────────────


@pytest.mark.parametrize(
    "module",
    [
        "gobus_mcp.tools.get_readability_recommendations",
        "gobus_mcp.tools.score_article",
        "gobus_mcp.tools.detect_anomalies",
        "gobus_mcp.tools.forecast_trends",
    ],
)
def test_tools_de_app_nao_usam_o_rodape(module):
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(module))
    assert "follow_ups" not in source
