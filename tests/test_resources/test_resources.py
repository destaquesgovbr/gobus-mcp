import pytest

from gobus_mcp.resources.agencies import fetch_agencies
from gobus_mcp.resources.platform_stats import fetch_platform_stats
from gobus_mcp.resources.themes import fetch_themes
from tests.conftest import FakeGraphQLClient, route_catalog


class TestAgenciesResource:
    async def test_lista_nomes_do_catalogo_com_codigo(self, fake_client):
        route_catalog(fake_client)

        result = await fetch_agencies(fake_client)

        assert "**Ministério da Saúde** (`saude`)" in result
        assert "**Ministério da Educação** (`mec`)" in result
        assert "(10)" in result.splitlines()[0]

    async def test_republicadoras_em_secao_propria(self, fake_client):
        route_catalog(fake_client)

        result = await fetch_agencies(fake_client)

        main, _, republishers = result.partition("## Republicadoras")
        assert "Agência Brasil" in republishers and "TV Brasil" in republishers
        assert "Agência Brasil" not in main

    async def test_sem_agencias_retorna_mensagem(self, fake_client):
        route_catalog(fake_client, [])

        result = await fetch_agencies(fake_client)

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
        client.set_response(
            {
                "analyticsKpis": {
                    "total": 335268,
                    "activeThemes": 25,
                    "activeAgencies": 45,
                    "dailyAverage": 42.5,
                }
            }
        )
        result = await fetch_platform_stats(client)
        assert "335" in result
        assert "25" in result
