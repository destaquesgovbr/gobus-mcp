import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_readability_recommendations import get_readability_recommendations


MOCK_ANALYTICS = {
    "agencyAnalytics": [
        {"period": "2026-04-01", "agencyKey": "secom", "agencyName": "Secom", "articleCount": 150, "avgReadabilityFlesch": 17.2, "avgWordCount": 450.0},
        {"period": "2026-04-01", "agencyKey": "cgu", "agencyName": "CGU", "articleCount": 80, "avgReadabilityFlesch": -1.2, "avgWordCount": 620.0},
        {"period": "2026-04-01", "agencyKey": "defesa", "agencyName": "Min. Defesa", "articleCount": 200, "avgReadabilityFlesch": -22.9, "avgWordCount": 800.0},
        {"period": "2026-04-01", "agencyKey": "agencia_brasil", "agencyName": "Agência Brasil", "articleCount": 300, "avgReadabilityFlesch": 33.5, "avgWordCount": 473.0},
    ]
}

MOCK_ARTICLES = {
    "search": {
        "articles": [
            {"uniqueId": "art-1", "title": "Artigo Legível", "agencyName": "Secom", "agency": "secom", "publishedAt": "2026-06-01", "summary": "...", "url": "https://example.com/1", "features": {"trendingScore": None, "viewCount": None}},
            {"uniqueId": "art-2", "title": "Artigo Técnico Complexo", "agencyName": "Secom", "agency": "secom", "publishedAt": "2026-06-02", "summary": "...", "url": "https://example.com/2", "features": {"trendingScore": None, "viewCount": None}},
        ],
        "found": 2,
        "page": 1
    }
}


class TestGetReadabilityRecommendations:

    async def test_ranking_geral_retorna_tabela_ordenada(self, fake_client):
        """Sem agency_key, deve retornar tabela com agências ordenadas por Flesch decrescente."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await get_readability_recommendations(agency_key=None, client=fake_client)
        # Agência Brasil (33.5) deve aparecer antes de Min. Defesa (-22.9)
        idx_brasil = result.index("Agência Brasil")
        idx_defesa = result.index("Min. Defesa")
        assert idx_brasil < idx_defesa

    async def test_ranking_geral_inclui_todas_as_agencias(self, fake_client):
        """Ranking geral deve incluir todas as 4 agências dos dados mock."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await get_readability_recommendations(agency_key=None, client=fake_client)
        assert "Secom" in result
        assert "CGU" in result
        assert "Min. Defesa" in result
        assert "Agência Brasil" in result

    async def test_agency_especifica_retorna_apenas_dados_dessa_agency(self, fake_client):
        """Com agency_key='secom', deve focar nos dados de Secom e listar artigos exemplos."""
        fake_client.set_responses([MOCK_ANALYTICS, MOCK_ARTICLES])
        result = await get_readability_recommendations(agency_key="secom", client=fake_client)
        assert "Secom" in result
        assert "Artigo Legível" in result or "Artigo Técnico Complexo" in result

    async def test_flesch_negativo_label_abaixo_do_piso(self, fake_client):
        """Flesch < 0 deve exibir label indicando dificuldade máxima (abaixo do piso)."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await get_readability_recommendations(agency_key=None, client=fake_client)
        # Min. Defesa tem -22.9; deve ter algum label de dificuldade extrema
        assert any(label in result for label in ["muito difícil", "abaixo do piso", "ilegível", "< 0", "Muito Difícil", "Abaixo do Piso"])

    async def test_flesch_entre_25_e_50_label_difícil(self, fake_client):
        """Flesch entre 25 e 50 deve ser classificado como 'difícil' ou equivalente."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await get_readability_recommendations(agency_key=None, client=fake_client)
        # Secom tem 17.2 (abaixo de 25) e Agência Brasil 33.5 (entre 25 e 50)
        assert any(label in result for label in ["difícil", "Difícil", "hard"])

    async def test_flesch_acima_de_50_label_médio_facil(self, fake_client):
        """Flesch >= 50 deve exibir label de leitura média ou fácil."""
        mock_com_facil = {
            "agencyAnalytics": [
                {"period": "2026-04-01", "agencyKey": "fácil", "agencyName": "Agência Fácil", "articleCount": 50, "avgReadabilityFlesch": 62.0, "avgWordCount": 300.0},
            ]
        }
        fake_client.set_response(mock_com_facil)
        result = await get_readability_recommendations(agency_key=None, client=fake_client)
        assert any(label in result for label in ["médio", "fácil", "Médio", "Fácil", "médio/fácil", "medium", "easy"])

    async def test_agency_sem_dados_retorna_mensagem_de_erro(self, fake_client):
        """Agency inexistente deve retornar mensagem de ausência de dados."""
        fake_client.set_responses([
            {"agencyAnalytics": []},
            {"search": {"articles": [], "found": 0, "page": 1}},
        ])
        result = await get_readability_recommendations(agency_key="inexistente", client=fake_client)
        assert "inexistente" in result or "sem dados" in result.lower() or "não encontrada" in result.lower() or "nenhum" in result.lower()

    async def test_retorna_markdown_nao_vazio(self, fake_client):
        """O retorno deve ser uma string Markdown não vazia."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await get_readability_recommendations(agency_key=None, client=fake_client)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        # Markdown deve ter pelo menos um cabeçalho ou item de lista
        assert "#" in result or "|" in result or "-" in result
