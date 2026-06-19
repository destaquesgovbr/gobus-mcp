import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.resolve_entity import resolve_entity


class TestResolveEntity:
    @pytest.mark.asyncio
    async def test_retorna_entidade_encontrada(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": [{
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
        }]})
        result = await resolve_entity("MEC", client)
        assert "Q4294522" in result
        assert "Ministério da Educação" in result
        assert "1.00" in result

    @pytest.mark.asyncio
    async def test_sem_resultado_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": []})
        result = await resolve_entity("xyz_inexistente", client)
        assert "Nenhuma" in result

    @pytest.mark.asyncio
    async def test_passa_entity_type_nas_variaveis(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": []})
        await resolve_entity("MEC", client, entity_type="ORG")
        call_args = client.execute.call_args
        variables = call_args[0][1]
        assert variables["entityType"] == "ORG"
