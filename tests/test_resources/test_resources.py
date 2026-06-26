import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.resources.agencies import fetch_agencies
from gobus_mcp.resources.themes import fetch_themes
from gobus_mcp.resources.platform_stats import fetch_platform_stats


class TestAgenciesResource:
    @pytest.mark.asyncio
    async def test_formata_lista_de_agencias(self):
        client = FakeGraphQLClient()
        client.set_response({"agencies": [
            {"code": "mec", "label": "Ministério da Educação"},
            {"code": "ms", "label": "Ministério da Saúde"},
        ]})
        result = await fetch_agencies(client)
        assert "Ministério da Educação" in result
        assert "`mec`" in result

    @pytest.mark.asyncio
    async def test_sem_agencias_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"agencies": []})
        result = await fetch_agencies(client)
        assert "Nenhuma" in result


class TestThemesResource:
    @pytest.mark.asyncio
    async def test_formata_lista_de_temas(self):
        client = FakeGraphQLClient()
        client.set_response({"themes": [{"code": "SAU", "label": "Saúde"}]})
        result = await fetch_themes(client)
        assert "Saúde" in result
        assert "SAU" in result


class TestPlatformStatsResource:
    @pytest.mark.asyncio
    async def test_formata_kpis(self):
        client = FakeGraphQLClient()
        client.set_response({"analyticsKpis": {
            "total": 335268, "activeThemes": 25, "activeAgencies": 45, "dailyAverage": 42.5
        }})
        result = await fetch_platform_stats(client)
        assert "335" in result
        assert "25" in result
