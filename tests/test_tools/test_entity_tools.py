from datetime import date

from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from tests.conftest import FakeGraphQLClient, route_catalog


class TestGetEntityProfile:
    async def test_retorna_perfil_completo(self, fake_client):
        route_catalog(fake_client)
        fake_client.route(
            "EntitySearch",
            {
                "entitySearch": [
                    {
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
                    }
                ]
            },
        )
        fake_client.route(
            "EntityCoverage",
            {
                "entityCoverage": [
                    {
                        "period": "2024-01",
                        "agencyKey": "mec",
                        "agencyName": "MEC",
                        "articleCount": 45,
                        "totalMentions": 132,
                        "avgSentimentScore": 0.6,
                    },
                ]
            },
        )
        fake_client.route(
            "RelatedEntities",
            {
                "relatedEntities": [
                    {"canonicalId": "Q9592631", "canonicalName": "INEP", "type": "ORG",
                     "weight": 96}
                ]
            },
        )  # fmt: skip
        fake_client.route("EntityDedupCounts", {"all": {"found": 0}, "distinct": {"found": 0}})

        result = await get_entity_profile("MEC", fake_client, today=date(2024, 3, 10))
        assert "Ministério da Educação" in result
        assert "Q4294522" in result
        assert "INEP" in result
        assert "2024-01" in result

    async def test_entidade_nao_encontrada(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": []})
        result = await get_entity_profile("xyz_inexistente", client)
        assert "não encontrada" in result.lower()


class TestGetEntityNetwork:
    async def test_retorna_rede_formatada(self, fake_client):
        route_catalog(fake_client)
        fake_client.route(
            "EntityNode",
            {"entity": {"entityId": "Q4294522", "canonicalName": "MEC", "type": "ORG"}},
        )
        fake_client.route(
            "RelatedEntities",
            {
                "relatedEntities": [
                    {
                        "canonicalId": "Q9592631",
                        "canonicalName": "INEP",
                        "type": "ORG",
                        "wikidataId": "Q9592631",
                        "weight": 96,
                        "kind": "co_mention",
                    }
                ]
            },
        )
        result = await get_entity_network("Q4294522", fake_client)
        assert "MEC" in result
        assert "INEP" in result
        assert "96" in result

    async def test_rede_vazia_retorna_mensagem(self, fake_client):
        route_catalog(fake_client)
        fake_client.route("EntityNode", {"entity": None})
        fake_client.route("RelatedEntities", {"relatedEntities": []})
        result = await get_entity_network("Q_inexistente", fake_client)
        assert "Nenhuma" in result
