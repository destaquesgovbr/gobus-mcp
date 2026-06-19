import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_agency_analytics import get_agency_analytics
from gobus_mcp.tools.detect_trends import detect_trends


class TestGetAgencyAnalytics:
    @pytest.mark.asyncio
    async def test_retorna_metricas_formatadas(self):
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": [{
            "period": "2024-01",
            "agencyKey": "mec",
            "agencyName": "Ministério da Educação",
            "articleCount": 45,
            "avgSentimentScore": 0.62,
            "pctPositive": 0.71,
            "pctNegative": 0.08,
            "avgReadabilityFlesch": 65.0,
            "avgWordCount": 380.0,
        }]})
        result = await get_agency_analytics(["mec"], "2024-01-01", "2024-01-31", client, "MONTH")
        assert "Ministério da Educação" in result
        assert "45" in result
        assert "positivos" in result.lower()
        assert "médio" in result.lower()

    @pytest.mark.asyncio
    async def test_sem_dados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": []})
        result = await get_agency_analytics(["xyz"], "2024-01-01", "2024-01-31", client)
        assert "Nenhum" in result


class TestDetectTrends:
    @pytest.mark.asyncio
    async def test_retorna_temas_em_crescimento(self):
        client = FakeGraphQLClient()
        client.set_response({"trendingThemes": [
            {
                "themeLabel": "Saúde",
                "themeCode": "SAU",
                "windowCount": 42,
                "baselineDailyAvg": 1.5,
                "growthScore": 4.0,
                "topArticles": [],
            },
            {
                "themeLabel": "Educação",
                "themeCode": "EDU",
                "windowCount": 21,
                "baselineDailyAvg": 2.0,
                "growthScore": 1.5,
                "topArticles": [],
            },
        ]})
        result = await detect_trends(client)
        assert "Saúde" in result
        assert "4.0" in result
        assert "🔥" in result or "trending" in result.lower() or "crescimento" in result.lower()

    @pytest.mark.asyncio
    async def test_sem_temas_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"trendingThemes": []})
        result = await detect_trends(client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_agency_key_passado_nas_variaveis(self):
        client = FakeGraphQLClient()
        client.set_response({"trendingThemes": []})
        await detect_trends(client, agency_key="mec")
        call_vars = client.execute.call_args[0][1]
        assert call_vars.get("agencyKey") == "mec"
