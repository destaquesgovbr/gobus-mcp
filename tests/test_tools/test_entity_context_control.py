import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile


def _make_network_response(n_nodes: int) -> dict:
    nodes = [
        {"entityId": f"Q{i}", "canonicalName": f"Ent{i}", "type": "ORG", "wikidataId": None}
        for i in range(n_nodes)
    ]
    edges = [{"src": "Q0", "dst": f"Q{i}", "weight": i, "kind": "co_mention"} for i in range(1, n_nodes)]
    return {"entityNetwork": {"nodes": nodes, "edges": edges}}


class TestMaxNodes:
    @pytest.mark.asyncio
    async def test_max_nodes_limita_output(self):
        client = FakeGraphQLClient()
        client.set_response(_make_network_response(40))
        result = await get_entity_network("Q0", client, depth=1, max_nodes=5)
        node_lines = [l for l in result.split("\n") if l.startswith("- `Q")]
        assert len(node_lines) <= 5

    @pytest.mark.asyncio
    async def test_max_nodes_default_e_20(self):
        client = FakeGraphQLClient()
        client.set_response(_make_network_response(40))
        result = await get_entity_network("Q0", client, depth=1)
        node_lines = [l for l in result.split("\n") if l.startswith("- `Q")]
        assert len(node_lines) <= 20


_ENTITY_SEARCH_HIT = {
    "entityId": "Q123", "canonicalName": "Saúde", "type": "ORG",
    "description": None, "wikidataUrl": None, "agencyKey": None,
    "aliases": [], "articleCount": 100, "confidence": 0.9, "matchType": "exact",
}
_COVERAGE_ROW = {
    "period": "2026-01", "agencyKey": "saude", "agencyName": "Saúde",
    "articleCount": 10, "totalMentions": 20, "avgSentimentScore": None,
}
_RELATED_ROW = {"canonicalId": "Q456", "canonicalName": "SUS", "type": "ORG", "weight": 5}


class TestSummaryOnly:
    @pytest.mark.asyncio
    async def test_summary_only_omite_serie_temporal(self):
        client = FakeGraphQLClient()
        client.set_responses([
            {"entitySearch": [_ENTITY_SEARCH_HIT]},
            {"entityCoverage": [_COVERAGE_ROW] * 12},
            {"relatedEntities": [_RELATED_ROW] * 5},
        ])
        result = await get_entity_profile("Saúde", client, summary_only=True)
        assert "2026-01" not in result
        assert "100" in result or "artigos" in result.lower()
        assert "SUS" in result

    @pytest.mark.asyncio
    async def test_summary_only_false_retorna_serie_completa(self):
        client = FakeGraphQLClient()
        client.set_responses([
            {"entitySearch": [_ENTITY_SEARCH_HIT]},
            {"entityCoverage": [_COVERAGE_ROW]},
            {"relatedEntities": []},
        ])
        result = await get_entity_profile("Saúde", client, summary_only=False)
        assert "2026-01" in result
