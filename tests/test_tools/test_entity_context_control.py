import re
from datetime import date

from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from tests.conftest import route_catalog


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


def _route_profile(client, coverage: list[dict], related: list[dict]) -> None:
    route_catalog(client)
    client.route("EntitySearch", {"entitySearch": [_ENTITY_SEARCH_HIT]})
    client.route("EntityCoverage", {"entityCoverage": coverage})
    client.route("RelatedEntities", {"relatedEntities": related})
    client.route("EntityDedupCounts", {"all": {"found": 0}, "distinct": {"found": 0}})


class TestSummaryOnly:
    async def test_summary_only_omite_serie_temporal(self, fake_client):
        _route_profile(fake_client, [_COVERAGE_ROW] * 12, [_RELATED_ROW] * 5)
        result = await get_entity_profile(
            "Saúde", fake_client, summary_only=True, today=date(2026, 10, 21)
        )
        assert "2026-01" not in result
        assert "120 artigos" in result
        assert "SUS" in result

    async def test_summary_only_false_retorna_serie_completa(self, fake_client):
        _route_profile(fake_client, [_COVERAGE_ROW], [])
        result = await get_entity_profile(
            "Saúde", fake_client, summary_only=False, today=date(2026, 10, 21)
        )
        assert "| 2026-01 | 10 | 0 |" in result
