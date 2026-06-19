import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from gobus_mcp.tools.get_entity_network import get_entity_network


class TestGetEntityProfile:
    @pytest.mark.asyncio
    async def test_retorna_perfil_completo(self):
        client = FakeGraphQLClient()
        responses = [
            {"entitySearch": [{
                "entityId": "Q4294522",
                "canonicalName": "Ministério da Educação",
                "type": "ORG",
                "description": "Ministério federal",
                "wikidataUrl": "https://www.wikidata.org/wiki/Q4294522",
                "agencyKey": "mec",
                "aliases": ["MEC"],
                "articleCount": 1223,
                "confidence": 1.0,
                "matchType": "alias_exact",
            }]},
            {"entityCoverage": [
                {"period": "2024-01", "agencyKey": "mec", "agencyName": "MEC",
                 "articleCount": 45, "totalMentions": 132, "avgSentimentScore": 0.6},
            ]},
            {"relatedEntities": [
                {"entityId": "Q9592631", "canonicalName": "INEP", "type": "ORG", "weight": 96}
            ]},
        ]
        call_count = 0
        from unittest.mock import AsyncMock
        async def mock_execute(query, variables=None):
            nonlocal call_count
            r = responses[call_count]
            call_count += 1
            return r
        client.execute = mock_execute

        result = await get_entity_profile("MEC", client)
        assert "Ministério da Educação" in result
        assert "Q4294522" in result
        assert "INEP" in result
        assert "2024-01" in result

    @pytest.mark.asyncio
    async def test_entidade_nao_encontrada(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": []})
        result = await get_entity_profile("xyz_inexistente", client)
        assert "não encontrada" in result.lower()


class TestGetEntityNetwork:
    @pytest.mark.asyncio
    async def test_retorna_rede_formatada(self):
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [
                {"entityId": "Q4294522", "canonicalName": "MEC", "type": "ORG", "wikidataId": "Q4294522"},
                {"entityId": "Q9592631", "canonicalName": "INEP", "type": "ORG", "wikidataId": "Q9592631"},
            ],
            "edges": [{"src": "Q4294522", "dst": "Q9592631", "weight": 96, "kind": "co_mention"}],
        }})
        result = await get_entity_network("Q4294522", client)
        assert "MEC" in result
        assert "INEP" in result
        assert "96" in result

    @pytest.mark.asyncio
    async def test_rede_vazia_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {"nodes": [], "edges": []}})
        result = await get_entity_network("Q_inexistente", client)
        assert "Nenhuma" in result
