import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_article import get_article


class TestGetArticle:
    @pytest.mark.asyncio
    async def test_retorna_artigo_completo(self):
        client = FakeGraphQLClient()
        client.set_response({"article": {
            "uniqueId": "abc123",
            "title": "Título do Artigo",
            "content": "Conteúdo completo do artigo.",
            "summary": "Resumo.",
            "agencyName": "MEC",
            "publishedAt": "2024-06-01T10:00:00Z",
            "url": "https://gov.br/abc",
            "tags": ["educação", "governo"],
            "features": {
                "viewCount": 1500,
                "uniqueSessions": 900,
                "trendingScore": 2.1,
                "wordCount": 400,
                "readabilityFlesch": 65.0,
                "entities": [{"text": "MEC", "type": "ORG", "count": 3, "canonicalId": "Q4294522"}],
            },
        }})
        result = await get_article("abc123", client)
        assert "Título do Artigo" in result
        assert "Conteúdo completo" in result
        assert "MEC" in result
        assert "fácil" in result.lower() or "médio" in result.lower()
        assert "Instituições" in result

    @pytest.mark.asyncio
    async def test_artigo_nao_encontrado(self):
        client = FakeGraphQLClient()
        client.set_response({"article": None})
        result = await get_article("inexistente", client)
        assert "não encontrado" in result.lower()
