import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_entity_network import get_entity_network


def _make_node(i: int, kind: str = "ORG") -> dict:
    return {"entityId": f"Q{i}", "canonicalName": f"Entidade{i}", "type": kind, "wikidataId": None}


def _make_edge(src: int, dst: int, weight: int = 5, kind: str = "co-mention") -> dict:
    return {"src": f"Q{src}", "dst": f"Q{dst}", "weight": weight, "kind": kind}


class TestGetEntityNetwork:
    @pytest.mark.asyncio
    async def test_retorna_rede_formatada(self):
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [_make_node(0), _make_node(1)],
            "edges": [_make_edge(0, 1)],
        }})
        result = await get_entity_network("Q0", client)
        assert "Entidade0" in result
        assert "Entidade1" in result

    @pytest.mark.asyncio
    async def test_exibe_kind_nas_arestas(self):
        """O tipo de aresta (kind) deve aparecer na listagem de conexões."""
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [_make_node(0), _make_node(1)],
            "edges": [_make_edge(0, 1, kind="COAUTHOR")],
        }})
        result = await get_entity_network("Q0", client)
        assert "COAUTHOR" in result

    @pytest.mark.asyncio
    async def test_warning_para_depth2(self):
        """depth=2 deve incluir aviso sobre volume de dados."""
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [_make_node(0)],
            "edges": [],
        }})
        result = await get_entity_network("Q0", client, depth=2)
        assert "depth=2" in result or "aviso" in result.lower() or "⚠️" in result

    @pytest.mark.asyncio
    async def test_node_types_filtra_output(self):
        """node_types='PER' deve mostrar só nós do tipo PER no output."""
        nodes = [_make_node(i, "ORG" if i % 2 == 0 else "PER") for i in range(6)]
        nodes[0]["entityId"] = "Q0"   # centro é ORG
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {"nodes": nodes, "edges": []}})
        result = await get_entity_network("Q0", client, node_types="PER")
        assert "Entidade1" in result   # PER
        assert "Entidade2" not in result   # ORG (excluído)

    @pytest.mark.asyncio
    async def test_cap_de_50_nos_no_output(self):
        """Mais de 50 nós: output deve conter aviso de truncamento."""
        nodes = [_make_node(i) for i in range(60)]
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {"nodes": nodes, "edges": []}})
        result = await get_entity_network("Q0", client)
        assert "omitidos" in result or "truncad" in result.lower()
