"""Consulta compartilhada de entidades: id canônico, ``entity(id)`` e ``relatedEntities``."""

import pytest

from gobus_mcp.cache import TTLCache
from gobus_mcp.entity_lookup import fetch_entity, fetch_related, looks_like_id
from tests.conftest import FakeGraphQLClient


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Q4294522", True),
        ("dgb_pe-de-meia", True),
        ("dgb_saude", True),
        ("Pé-de-Meia", False),
        ("q155", False),
        ("Q155 Brasil", False),
        ("", False),
    ],
)
def test_looks_like_id(value, expected):
    assert looks_like_id(value) is expected


def _row(cid: str, name: str | None, weight: int, kind: str = "ORG") -> dict:
    return {
        "canonicalId": cid,
        "canonicalName": name,
        "type": kind,
        "wikidataId": None,
        "weight": weight,
        "kind": "co_mention",
    }


async def test_fetch_related_ordena_por_peso_e_depois_nome(fake_client):
    fake_client.route(
        "RelatedEntities",
        {
            "relatedEntities": [
                _row("Q2", "Bravo", 10),
                _row("Q1", "Alfa", 10),
                _row("Q3", "Charlie", 99),
                _row("Q4", None, 10),  # sem nome: ordena pelo id
            ]
        },
    )
    rows = await fetch_related(fake_client, "Q0", 25)
    assert [r["canonicalId"] for r in rows] == ["Q3", "Q1", "Q2", "Q4"]
    assert fake_client.calls("RelatedEntities") == [{"id": "Q0", "limit": 25}]


async def test_fetch_related_descarta_a_propria_entidade_e_linhas_sem_id(fake_client):
    fake_client.route(
        "RelatedEntities",
        {"relatedEntities": [_row("Q0", "Foco", 50), _row("", "Sem id", 9), _row("Q1", "A", 3)]},
    )
    rows = await fetch_related(fake_client, "Q0", 10)
    assert [r["canonicalId"] for r in rows] == ["Q1"]


async def test_fetch_related_vazio_quando_a_api_nao_traz_nada(fake_client):
    fake_client.route("RelatedEntities", {})
    assert await fetch_related(fake_client, "Q0", 10) == []


async def test_fetch_related_usa_o_cache_por_id_e_limite():
    client = FakeGraphQLClient()
    client.route("RelatedEntities", {"relatedEntities": [_row("Q1", "A", 3)]})
    cache = TTLCache()
    await fetch_related(client, "Q0", 10, cache=cache)
    await fetch_related(client, "Q0", 10, cache=cache)
    await fetch_related(client, "Q0", 20, cache=cache)
    assert len(client.calls("RelatedEntities")) == 2


async def test_fetch_related_nao_cacheia_falha():
    client = FakeGraphQLClient()
    client.route("RelatedEntities", RuntimeError("timeout"))
    cache = TTLCache()
    with pytest.raises(RuntimeError):
        await fetch_related(client, "Q0", 10, cache=cache)
    client.route("RelatedEntities", {"relatedEntities": [_row("Q1", "A", 3)]})
    assert len(await fetch_related(client, "Q0", 10, cache=cache)) == 1


async def test_fetch_entity_devolve_o_no_ou_none(fake_client):
    fake_client.route(
        "EntityNode",
        lambda v: {
            "entity": {"entityId": v["id"], "canonicalName": "Pé-de-Meia", "type": "POLICY"}
            if v["id"] == "dgb_pe-de-meia"
            else None
        },
    )
    node = await fetch_entity(fake_client, "dgb_pe-de-meia")
    assert node["canonicalName"] == "Pé-de-Meia"
    assert await fetch_entity(fake_client, "Q999") is None
