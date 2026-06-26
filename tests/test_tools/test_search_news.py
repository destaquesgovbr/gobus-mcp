import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.search_news import search_news


def _make_article(i: int, agency_code: str = "mec", agency_name: str = "MEC") -> dict:
    return {
        "uniqueId": f"id{i}",
        "title": f"Artigo {i}",
        "agencyName": agency_name,
        "agency": agency_code,
        "publishedAt": "2026-01-01T00:00:00Z",
        "summary": "Resumo",
        "url": f"https://gov.br/{agency_code}/artigo-{i}",
        "features": {"trendingScore": 0.0, "viewCount": 0},
    }


class TestSearchNews:
    @pytest.mark.asyncio
    async def test_retorna_artigos_formatados(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(1, "mec", "Ministério da Educação")],
            "found": 1, "page": 1,
        }})
        result = await search_news("educação", client)
        assert "Artigo 1" in result
        assert "Ministério da Educação" in result
        assert "id1" in result

    @pytest.mark.asyncio
    async def test_sem_resultados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("xyz_inexistente", client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_campo_agency_code_exibido(self):
        """agency code (ex: 'mec') deve aparecer no Markdown."""
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(1, "saude", "Ministério da Saúde")],
            "found": 1, "page": 1,
        }})
        result = await search_news("saúde", client)
        assert "[saude]" in result

    @pytest.mark.asyncio
    async def test_date_from_passado_no_filter(self):
        """date_from deve ir para filter.startDate."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, date_from="2026-06-01")
        variables = client.execute.call_args[0][1]
        assert variables["filter"]["startDate"] == "2026-06-01"

    @pytest.mark.asyncio
    async def test_date_to_passado_no_filter(self):
        """date_to deve ir para filter.endDate."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, date_to="2026-06-24")
        variables = client.execute.call_args[0][1]
        assert variables["filter"]["endDate"] == "2026-06-24"

    @pytest.mark.asyncio
    async def test_date_filter_combinado_com_agency(self):
        """date_from + agency_key devem ir no mesmo filter."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, agency_key="saude", date_from="2026-06-01", date_to="2026-06-24")
        variables = client.execute.call_args[0][1]
        assert "saude" in variables["filter"]["agencies"]
        assert variables["filter"]["startDate"] == "2026-06-01"
        assert variables["filter"]["endDate"] == "2026-06-24"

    @pytest.mark.asyncio
    async def test_limit_fatia_resultados_cliente(self):
        """limit deve fatiar a lista após receber a resposta do servidor."""
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(i) for i in range(20)],
            "found": 20, "page": 1,
        }})
        result = await search_news("test", client, limit=5)
        assert "Artigo 0" in result
        assert "Artigo 4" in result
        assert "Artigo 5" not in result

    @pytest.mark.asyncio
    async def test_limit_cap_em_50(self):
        """limit > 50 deve ser silenciosamente capado em 50."""
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(i) for i in range(60)],
            "found": 60, "page": 1,
        }})
        result = await search_news("test", client, limit=100)
        assert "Artigo 49" in result
        assert "Artigo 50" not in result

    @pytest.mark.asyncio
    async def test_hint_quando_agency_key_invalida_sem_resultados(self):
        """0 resultados com agency_key → hint para gobus://agencies."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("saúde", client, agency_key="invalida_xyz")
        assert "gobus://agencies" in result
