import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.search_news import search_news


class TestSearchNews:
    @pytest.mark.asyncio
    async def test_retorna_artigos_formatados(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [{
                "uniqueId": "abc123",
                "title": "Governo lança programa",
                "agencyName": "MEC",
                "publishedAt": "2024-06-01T10:00:00Z",
                "summary": "Resumo do artigo",
                "url": "https://gov.br/abc",
                "trendingScore": 2.5,
                "viewCount": 1500,
            }],
            "found": 1,
            "page": 1,
        }})
        result = await search_news("programa", client)
        assert "Governo lança programa" in result
        assert "MEC" in result
        assert "abc123" in result
        assert "trending" in result.lower() or "🔥" in result

    @pytest.mark.asyncio
    async def test_sem_resultados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("xyz_inexistente", client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_limita_limit_a_50(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("test", client, limit=100)
        call_variables = client.execute.call_args[0][1]
        assert call_variables["limit"] == 50
