"""Links nos top artigos dos temas em alta (``ArticleSummary.url``, GQL-1): detect_trends e
get_agency_summary. Sem o campo na API ("Cannot query field"), a query antiga responde e o
título sai sem link, com o unique_id."""

from datetime import date

from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.schema_compat import ARTICLE_SUMMARY_URL, COMPAT
from gobus_mcp.tools.detect_trends import (
    _TRENDING_LEGACY_QUERY,
    _TRENDING_QUERY,
    detect_trends,
)
from gobus_mcp.tools.get_agency_summary import (
    _TRENDS_LEGACY_QUERY,
    _TRENDS_QUERY,
    get_agency_summary,
)
from tests.conftest import route_catalog

TODAY = date(2026, 10, 5)
URL1 = "https://www.gov.br/saude/pt-br/assuntos/noticias/2026/outubro/vacina"
NO_URL = GobusGraphQLError([{"message": "Cannot query field 'url' on type 'ArticleSummary'."}])


def _theme(with_url: bool = True) -> dict:
    article = {
        "uniqueId": "a1",
        "title": "Novo imunizante aprovado",
        "agencyName": "saude",
        "publishedAt": "2026-10-01",
    }
    if with_url:
        article["url"] = URL1
    return {
        "themeLabel": "Saúde",
        "windowCount": 42,
        "baselineDailyAvg": 3.0,
        "growthScore": 2.0,
        "topArticles": [article],
    }


def _route_coverage(client):
    client.route(
        "ThemeCoverage",
        {"topThemes": [{"label": "Saúde", "count": 900}], "analyticsKpis": {"total": 1000}},
    )


def _route_summary(client, trends):
    route_catalog(client)
    _route_coverage(client)
    client.route(
        "AgencySummaryAnalytics",
        {"agencyAnalytics": [{"period": "2026-09-01", "agencyKey": "saude", "articleCount": 42}]},
    )
    client.route("AgencySummaryTrends", trends)


def test_queries_novas_pedem_url_e_as_antigas_nao():
    for new, old in (
        (_TRENDING_QUERY, _TRENDING_LEGACY_QUERY),
        (_TRENDS_QUERY, _TRENDS_LEGACY_QUERY),
    ):
        assert " url" in new.split("topArticles", 1)[1]
        assert " url" not in old.split("topArticles", 1)[1]
        assert "Legacy" in old.split("(", 1)[0]


class TestDetectTrendsLinks:
    async def test_top_artigos_com_link(self, fake_client):
        route_catalog(fake_client)
        _route_coverage(fake_client)
        fake_client.route("TrendingThemes", {"trendingThemes": [_theme()]})

        result = await detect_trends(fake_client)

        assert f"[Novo imunizante aprovado]({URL1})" in result
        assert "`a1`" in result

    async def test_api_sem_url_usa_a_query_antiga_e_cita_o_id(self, fake_client):
        route_catalog(fake_client)
        _route_coverage(fake_client)
        fake_client.route("TrendingThemes", NO_URL)
        fake_client.route("TrendingThemesLegacy", {"trendingThemes": [_theme(with_url=False)]})

        first = await detect_trends(fake_client)
        await detect_trends(fake_client)

        assert "Novo imunizante aprovado" in first and "`a1`" in first
        assert "](" not in first.split("## ", 1)[1].split("_Razão", 1)[0]
        assert len(fake_client.calls("TrendingThemes")) == 1  # a 2ª vai direto à antiga
        assert len(fake_client.calls("TrendingThemesLegacy")) == 2
        assert not COMPAT.available(ARTICLE_SUMMARY_URL)


class TestAgencySummaryLinks:
    async def test_top_artigos_com_link_e_id(self, fake_client):
        _route_summary(fake_client, {"trendingThemes": [_theme()]})

        result = await get_agency_summary("saude", fake_client, today=TODAY)

        line = next(line for line in result.splitlines() if "Novo imunizante" in line)
        assert f"[Novo imunizante aprovado]({URL1})" in line
        assert "`a1`" in line

    async def test_api_sem_url_usa_a_query_antiga(self, fake_client):
        _route_summary(fake_client, NO_URL)
        fake_client.route("AgencySummaryTrendsLegacy", {"trendingThemes": [_theme(with_url=False)]})

        result = await get_agency_summary("saude", fake_client, today=TODAY)

        line = next(line for line in result.splitlines() if "Novo imunizante" in line)
        assert "](" not in line and "`a1`" in line
        assert fake_client.calls("AgencySummaryTrendsLegacy")
