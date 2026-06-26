import pytest
from unittest.mock import AsyncMock
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_agency_summary import get_agency_summary


class TestGetAgencySummary:
    @pytest.mark.asyncio
    async def test_combina_analytics_e_trends(self):
        """Deve fazer 2 chamadas GraphQL e combinar no output."""
        client = FakeGraphQLClient()
        client.execute = AsyncMock(side_effect=[
            {"agencyAnalytics": [{
                "period": "2026-06",
                "agencyKey": "saude",
                "agencyName": "Ministério da Saúde",
                "articleCount": 42,
                "avgSentimentScore": 0.0,
                "pctPositive": 0.0,
                "avgReadabilityFlesch": 55.0,
            }]},
            {"trendingThemes": [{
                "themeLabel": "Vacinação",
                "growthScore": 2.3,
                "windowCount": 15,
                "topArticles": [
                    {"uniqueId": "a1", "title": "Novo imunizante aprovado",
                     "publishedAt": "2026-06-20", "url": "https://gov.br/saude/a1"},
                ],
            }]},
        ])
        result = await get_agency_summary("saude", client)
        assert "Ministério da Saúde" in result
        assert "42" in result
        assert "Vacinação" in result
        assert "Novo imunizante aprovado" in result

    @pytest.mark.asyncio
    async def test_sem_dados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.execute = AsyncMock(side_effect=[
            {"agencyAnalytics": []},
            {"trendingThemes": []},
        ])
        result = await get_agency_summary("invalida", client)
        assert "invalida" in result

    @pytest.mark.asyncio
    async def test_agency_key_passado_na_primeira_call(self):
        """analytics deve ser chamado com a agency_key."""
        client = FakeGraphQLClient()
        client.execute = AsyncMock(side_effect=[
            {"agencyAnalytics": []},
            {"trendingThemes": []},
        ])
        await get_agency_summary("mec", client, days=30)
        first_call_vars = client.execute.call_args_list[0][0][1]
        assert "mec" in first_call_vars["agencies"]
