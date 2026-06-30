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
        assert "pos" in result.lower()
        assert "médio" in result.lower()

    @pytest.mark.asyncio
    async def test_sem_dados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": []})
        result = await get_agency_analytics(["xyz"], "2024-01-01", "2024-01-31", client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_legibilidade_exibe_score_numerico(self):
        """Flesch score numérico deve aparecer além do label."""
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": [{
            "period": "2026-06", "agencyKey": "mec", "agencyName": "MEC",
            "articleCount": 10, "avgSentimentScore": 0.1,
            "pctPositive": 0.3, "pctNegative": 0.1,
            "avgReadabilityFlesch": 72.5, "avgWordCount": 380.0,
        }]})
        result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
        assert "72.5" in result
        assert "fácil" in result.lower()

    @pytest.mark.asyncio
    async def test_exibe_pct_negativo(self):
        """pctNegative deve aparecer no output."""
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": [{
            "period": "2026-06", "agencyKey": "mec", "agencyName": "MEC",
            "articleCount": 10, "avgSentimentScore": 0.1,
            "pctPositive": 0.3, "pctNegative": 0.12,
            "avgReadabilityFlesch": 65.0, "avgWordCount": 300.0,
        }]})
        result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
        assert "12%" in result or "neg" in result.lower()

    @pytest.mark.asyncio
    async def test_exibe_avg_word_count(self):
        """avgWordCount deve aparecer no output."""
        client = FakeGraphQLClient()
        client.set_response({"agencyAnalytics": [{
            "period": "2026-06", "agencyKey": "mec", "agencyName": "MEC",
            "articleCount": 10, "avgSentimentScore": 0.1,
            "pctPositive": 0.3, "pctNegative": 0.05,
            "avgReadabilityFlesch": 65.0, "avgWordCount": 420.0,
        }]})
        result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
        assert "420" in result


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

    @pytest.mark.asyncio
    async def test_exibe_agencias_por_tema(self):
        """Contagem de agências dos topArticles deve aparecer por tema."""
        client = FakeGraphQLClient()
        client.set_response({"trendingThemes": [{
            "themeLabel": "Saúde Pública",
            "themeCode": "SAU",
            "windowCount": 10,
            "baselineDailyAvg": 1.0,
            "growthScore": 2.5,
            "topArticles": [
                {"uniqueId": "a1", "title": "T1", "agencyName": "Ministério da Saúde",
                 "publishedAt": "2026-06-01", "trendingScore": 1.5},
                {"uniqueId": "a2", "title": "T2", "agencyName": "Ministério da Saúde",
                 "publishedAt": "2026-06-02", "trendingScore": 1.2},
                {"uniqueId": "a3", "title": "T3", "agencyName": "SECOM",
                 "publishedAt": "2026-06-03", "trendingScore": 1.0},
            ],
        }]})
        result = await detect_trends(client)
        assert "Ministério da Saúde" in result
        assert "SECOM" in result
        assert "T1" in result
        assert "T2" in result
        assert "a1" in result
