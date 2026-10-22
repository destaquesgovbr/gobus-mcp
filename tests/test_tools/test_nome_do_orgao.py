"""Nome do órgão pelo catálogo (gobus-mcp#17) no search_news e no detect_trends.

O ``search()`` da graphql-api devolve ``agencyName: null`` em 100% dos artigos
(graphql-api#34), e o ``ArticleSummary.agencyName`` dos temas em alta carrega a **key** por
compatibilidade (graphql-api#32, que criou ``ArticleSummary.agencyKey``). As duas tools
resolvem ``AgencyCatalog.display_names()`` uma vez por resposta e montam
``[código] Nome``; o catálogo fora do ar deixa só ``[código]``, sem erro.
"""

from datetime import date

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.tools.detect_trends import (
    _TRENDING_LEGACY_QUERY,
    _TRENDING_QUERY,
    detect_trends,
)
from gobus_mcp.tools.search_news import search_news
from tests.conftest import route_catalog

TODAY = date(2026, 10, 21)
PREVIDENCIA = [
    ("previdencia", False, "Ministério da Previdência Social"),
    ("inss", False, "Instituto Nacional do Seguro Social"),
    ("saude", False, "Ministério da Saúde"),
    ("mec", False, "Ministério da Educação"),
]
NO_URL = GobusGraphQLError([{"message": "Cannot query field 'url' on type 'ArticleSummary'."}])


def _search_article(i: int, code: str, name: str | None = None) -> dict:
    return {
        "uniqueId": f"id{i}",
        "title": f"Artigo {i}",
        "agencyName": name,
        "agency": code,
        "publishedAt": "2026-10-20T12:00:00Z",
        "summary": "Resumo",
        "url": f"https://www.gov.br/{code}/artigo-{i}",
        "features": {"trendingScore": 0.0, "viewCount": 0},
    }


def _route_search(client, articles: list[dict]) -> None:
    client.route(
        "SearchNews", {"search": {"articles": articles, "found": len(articles), "page": 1}}
    )


# ── search_news ─────────────────────────────────────────────────────────────


async def test_search_news_nome_do_catalogo_quando_a_api_devolve_nulo(fake_client):
    route_catalog(fake_client, PREVIDENCIA)
    _route_search(
        fake_client,
        [
            _search_article(1, "previdencia"),
            _search_article(2, "inss"),
            _search_article(3, "inss"),
        ],
    )

    result = await search_news(
        "INSS prova de vida", fake_client, catalog=AgencyCatalog(fake_client)
    )

    assert "**[previdencia] Ministério da Previdência Social** ·" in result
    assert result.count("**[inss] Instituto Nacional do Seguro Social** ·") == 2
    assert len(fake_client.calls("CatalogAgencyNames")) == 1  # uma vez por página


async def test_search_news_catalogo_fora_do_ar_mostra_so_o_codigo(fake_client):
    fake_client.route("CatalogAgencies", RuntimeError("catálogo fora do ar"))
    _route_search(fake_client, [_search_article(1, "previdencia")])

    result = await search_news("INSS", fake_client, catalog=AgencyCatalog(fake_client))

    assert "**[previdencia]** ·" in result
    assert "Artigo 1" in result


async def test_search_news_nome_da_api_quando_o_catalogo_nao_tem_o_codigo(fake_client):
    route_catalog(fake_client, PREVIDENCIA)
    _route_search(fake_client, [_search_article(1, "orgao_novo", "Órgão Novo")])

    result = await search_news("x", fake_client, catalog=AgencyCatalog(fake_client))

    assert "**[orgao_novo] Órgão Novo** ·" in result


# ── detect_trends ───────────────────────────────────────────────────────────


def _summary(uid: str, code: str, *, key: bool = True) -> dict:
    """``ArticleSummary``: ``agencyName`` carrega a key; ``agencyKey`` só na query nova."""
    art = {
        "uniqueId": uid,
        "title": f"Artigo {uid}",
        "agencyName": code,
        "publishedAt": "2026-10-15",
    }
    if key:
        art["agencyKey"] = code
        art["url"] = f"https://www.gov.br/{code}/{uid}"
    return art


def _theme(articles: list[dict]) -> dict:
    return {
        "themeLabel": "Saúde",
        "windowCount": 42,
        "baselineDailyAvg": 3.0,
        "growthScore": 2.0,
        "topArticles": articles,
    }


def _route_coverage(client) -> None:
    client.route(
        "ThemeCoverage",
        {"topThemes": [{"label": "Saúde", "count": 900}], "analyticsKpis": {"total": 1000}},
    )


def test_query_nova_do_trending_pede_agency_key_e_a_antiga_nao():
    assert "agencyKey" in _TRENDING_QUERY.split("topArticles", 1)[1]
    assert "agencyKey" not in _TRENDING_LEGACY_QUERY.split("topArticles", 1)[1]


async def test_detect_trends_agencias_com_o_nome_do_catalogo(fake_client):
    route_catalog(fake_client, PREVIDENCIA)
    _route_coverage(fake_client)
    articles = [_summary("a1", "saude"), _summary("a2", "saude"), _summary("a3", "mec")]
    fake_client.route("TrendingThemes", {"trendingThemes": [_theme(articles)]})

    result = await detect_trends(fake_client, catalog=AgencyCatalog(fake_client), today=TODAY)

    assert (
        "   Agências: [saude] Ministério da Saúde (2) · [mec] Ministério da Educação (1)" in result
    )


async def test_detect_trends_api_antiga_usa_o_agency_name_como_codigo(fake_client):
    route_catalog(fake_client, PREVIDENCIA)
    _route_coverage(fake_client)
    fake_client.route("TrendingThemes", NO_URL)
    legacy = [_summary("a1", "inss", key=False)]
    fake_client.route("TrendingThemesLegacy", {"trendingThemes": [_theme(legacy)]})

    result = await detect_trends(fake_client, catalog=AgencyCatalog(fake_client), today=TODAY)

    assert "   Agências: [inss] Instituto Nacional do Seguro Social (1)" in result


async def test_detect_trends_catalogo_fora_do_ar_mostra_o_codigo(fake_client):
    fake_client.route("CatalogAgencies", RuntimeError("catálogo fora do ar"))
    _route_coverage(fake_client)
    fake_client.route("TrendingThemes", {"trendingThemes": [_theme([_summary("a1", "saude")])]})

    result = await detect_trends(fake_client, catalog=AgencyCatalog(fake_client), today=TODAY)

    assert "   Agências: [saude] (1)" in result
