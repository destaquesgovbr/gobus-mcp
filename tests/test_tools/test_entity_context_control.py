import re

import pytest

from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from tests.conftest import FakeGraphQLClient, route_catalog


def _route_network(client, n_neighbors: int) -> None:
    rows = [
        {
            "canonicalId": f"Q{i}",
            "canonicalName": f"Ent{i}",
            "type": "ORG",
            "wikidataId": None,
            "weight": 1000 - i,
            "kind": "co_mention",
        }
        for i in range(1, n_neighbors + 1)
    ]
    route_catalog(client)
    client.route("EntityNode", {"entity": {"entityId": "Q0", "canonicalName": "Ent0"}})
    client.route("RelatedEntities", lambda v: {"relatedEntities": rows[: v["limit"]]})


def _ranked_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if re.match(r"^\d+\. \*\*", line)]


class TestMaxNodes:
    async def test_max_nodes_limita_output(self, fake_client):
        _route_network(fake_client, 40)
        result = await get_entity_network("Q0", fake_client, depth=1, max_nodes=5)
        assert len(_ranked_lines(result)) == 5
        assert "Mostrando 5 de 40 vizinhos diretos" in result

    async def test_max_nodes_default_e_20(self, fake_client):
        _route_network(fake_client, 40)
        result = await get_entity_network("Q0", fake_client, depth=1)
        assert len(_ranked_lines(result)) == 20


_ENTITY_SEARCH_HIT = {
    "entityId": "Q123",
    "canonicalName": "Saúde",
    "type": "ORG",
    "description": None,
    "wikidataUrl": None,
    "agencyKey": None,
    "aliases": [],
    "articleCount": 100,
    "confidence": 0.9,
    "matchType": "exact",
}
_COVERAGE_ROW = {
    "period": "2026-01",
    "agencyKey": "saude",
    "agencyName": "Saúde",
    "articleCount": 10,
    "totalMentions": 20,
    "avgSentimentScore": None,
}
_RELATED_ROW = {"canonicalId": "Q456", "canonicalName": "SUS", "type": "ORG", "weight": 5}


class TestSummaryOnly:
    @pytest.mark.asyncio
    async def test_summary_only_omite_serie_temporal(self):
        client = FakeGraphQLClient()
        client.set_responses(
            [
                {"entitySearch": [_ENTITY_SEARCH_HIT]},
                {"entityCoverage": [_COVERAGE_ROW] * 12},
                {"relatedEntities": [_RELATED_ROW] * 5},
            ]
        )
        result = await get_entity_profile("Saúde", client, summary_only=True)
        assert "2026-01" not in result
        assert "100" in result or "artigos" in result.lower()
        assert "SUS" in result

    @pytest.mark.asyncio
    async def test_summary_only_false_retorna_serie_completa(self):
        client = FakeGraphQLClient()
        client.set_responses(
            [
                {"entitySearch": [_ENTITY_SEARCH_HIT]},
                {"entityCoverage": [_COVERAGE_ROW]},
                {"relatedEntities": []},
            ]
        )
        result = await get_entity_profile("Saúde", client, summary_only=False)
        assert "2026-01" in result
