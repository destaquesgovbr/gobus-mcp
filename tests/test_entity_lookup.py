"""Consulta compartilhada de entidades: id canônico, ``entity(id)`` e ``relatedEntities``
ranqueado por associação (peso × log2 do lift, GQL-1), com o peso bruto de reserva."""

import math

import pytest

from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.entity_lookup import (
    association_score,
    fetch_entity,
    fetch_neighbors,
    looks_like_id,
)
from gobus_mcp.schema_compat import COMPAT, RELATED_LIFT
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


def _row(
    cid: str, name: str | None, weight: int, kind: str = "ORG", lift: float | None = None
) -> dict:
    row = {
        "canonicalId": cid,
        "canonicalName": name,
        "type": kind,
        "wikidataId": None,
        "weight": weight,
        "kind": "co_mention",
    }
    if lift is not None:
        row["lift"] = lift
        row["articleCount"] = 1000
    return row


NO_LIFT = GobusGraphQLError(
    [{"message": "Unknown argument 'orderBy' on field 'Query.relatedEntities'."}]
)

# Pé-de-Meia em 21/10/2026 (entity_edges × news_entities, N = 202.608): o MEC é o 65º por lift
# e o 1º por associação; a Lei 14.818 só entra pelo pool de lift; Brasil tem lift ~1.
MEC = _row("Q4294522", "MEC", 650, lift=14.58)
ENEM = _row("Q5419278", "Enem", 306, "EVENT", lift=68.58)
INEP = _row("Q6041403", "Inep", 295, lift=23.25)
BRASIL = _row("Q155", "Brasil", 341, "LOC", lift=1.05)
LEI = _row("dgb_lei-14818", "Lei nº 14.818/2024", 64, "LAW", lift=153.39)
RARA = _row("dgb_rara", "Rara", 2, lift=900.0)  # w < 3: fora do ranking por associação


def _pools(v: dict) -> dict:
    by_weight = [MEC, BRASIL, ENEM, INEP]
    by_lift = [RARA, LEI, ENEM, INEP]
    rows = by_lift if v["orderBy"] == "LIFT" else by_weight
    return {"relatedEntities": rows[: v["limit"]]}


@pytest.mark.parametrize(
    ("weight", "lift", "expected"),
    [
        (650, 14.58, 650 * math.log2(14.58)),
        (3, 8.0, 9.0),
        (2, 900.0, 0.0),  # w < 3
        (500, 0.8, 0.0),  # abaixo do esperado
        (500, 1.0, 0.0),
        (500, None, None),  # sem estatística
    ],
)
def test_association_score(weight, lift, expected):
    row = {"weight": weight, "lift": lift}
    if expected is None:
        assert association_score(row) is None
    else:
        assert association_score(row) == pytest.approx(expected)


async def test_pede_os_pools_por_peso_e_por_lift(fake_client):
    fake_client.route("RelatedEntities", _pools)

    await fetch_neighbors(fake_client, "dgb_pe-de-meia", 40)

    calls = fake_client.calls("RelatedEntities")
    assert {"id": "dgb_pe-de-meia", "limit": 40, "orderBy": "WEIGHT", "minWeight": 2} in calls
    assert {"id": "dgb_pe-de-meia", "limit": 40, "orderBy": "LIFT", "minWeight": 3} in calls
    assert len(calls) == 2


async def test_ranking_por_associacao_une_os_pools(fake_client):
    fake_client.route("RelatedEntities", _pools)

    result = await fetch_neighbors(fake_client, "dgb_pe-de-meia", 40)

    assert result.ranking == "lift"
    assert [r["canonicalId"] for r in result.rows] == [
        "Q4294522",  # 650 × log2(14,6) ≈ 2.513
        "Q5419278",  # 306 × log2(68,6) ≈ 1.866
        "Q6041403",  # 295 × log2(23,3) ≈ 1.339
        "dgb_lei-14818",  # 64 × log2(153) ≈ 465 (só no pool de lift)
        "Q155",  # lift ≈ 1: associação ≈ 24
        "dgb_rara",  # w = 2: score 0
    ]
    assert result.note is None


async def test_lift_pool_false_faz_so_a_consulta_por_peso(fake_client):
    fake_client.route("RelatedEntities", _pools)

    result = await fetch_neighbors(fake_client, "Q0", 25, lift_pool=False)

    assert [c["orderBy"] for c in fake_client.calls("RelatedEntities")] == ["WEIGHT"]
    assert result.ranking == "lift"
    assert result.rows[0]["canonicalId"] == "Q4294522"


async def test_sem_lift_nos_dados_ordena_por_peso_e_avisa(fake_client):
    fake_client.route(
        "RelatedEntities",
        {"relatedEntities": [_row("Q2", "Bravo", 10), _row("Q1", "Alfa", 10), _row("Q3", "C", 99)]},
    )

    result = await fetch_neighbors(fake_client, "Q0", 25)

    assert result.ranking == "weight"
    assert [r["canonicalId"] for r in result.rows] == ["Q3", "Q1", "Q2"]
    assert "lift" in result.note


async def test_api_sem_lift_usa_a_query_antiga_por_uma_hora(fake_client):
    fake_client.route("RelatedEntities", NO_LIFT)
    fake_client.route(
        "RelatedEntitiesLegacy",
        {
            "relatedEntities": [
                _row("Q2", "Bravo", 10),
                _row("Q1", "Alfa", 10),
                _row("Q3", "Charlie", 99),
                _row("Q4", None, 10),  # sem nome: ordena pelo id
            ]
        },
    )

    first = await fetch_neighbors(fake_client, "Q0", 25)
    await fetch_neighbors(fake_client, "Q0", 25)

    assert first.ranking == "weight"
    assert [r["canonicalId"] for r in first.rows] == ["Q3", "Q1", "Q2", "Q4"]
    assert "API" in first.note
    assert fake_client.calls("RelatedEntitiesLegacy")[0] == {"id": "Q0", "limit": 25}
    assert len(fake_client.calls("RelatedEntitiesLegacy")) == 2
    assert len(fake_client.calls("RelatedEntities")) <= 2  # 1ª chamada (os 2 pools); depois, direto
    assert not COMPAT.available(RELATED_LIFT)


async def test_falha_so_no_pool_de_lift_mantem_o_ranking(fake_client):
    def related(v):
        if v["orderBy"] == "LIFT":
            raise RuntimeError("timeout")
        return _pools(v)

    fake_client.route("RelatedEntities", related)

    result = await fetch_neighbors(fake_client, "Q0", 40)

    assert result.ranking == "lift"
    assert "dgb_lei-14818" not in [r["canonicalId"] for r in result.rows]
    assert result.rows[0]["canonicalId"] == "Q4294522"


async def test_falha_no_pool_de_peso_propaga(fake_client):
    def related(v):
        if v["orderBy"] == "WEIGHT":
            raise RuntimeError("timeout")
        return _pools(v)

    fake_client.route("RelatedEntities", related)

    with pytest.raises(RuntimeError, match="timeout"):
        await fetch_neighbors(fake_client, "Q0", 40)
    assert COMPAT.available(RELATED_LIFT)


async def test_descarta_a_propria_entidade_e_linhas_sem_id(fake_client):
    fake_client.route(
        "RelatedEntities",
        {"relatedEntities": [_row("Q0", "Foco", 50), _row("", "Sem id", 9), _row("Q1", "A", 3)]},
    )
    result = await fetch_neighbors(fake_client, "Q0", 10)
    assert [r["canonicalId"] for r in result.rows] == ["Q1"]


async def test_vazio_quando_a_api_nao_traz_nada(fake_client):
    fake_client.route("RelatedEntities", {})
    result = await fetch_neighbors(fake_client, "Q0", 10)
    assert result.rows == []
    assert result.truncated is False


async def test_truncado_quando_o_pool_por_peso_bate_no_limite(fake_client):
    fake_client.route("RelatedEntities", _pools)
    result = await fetch_neighbors(fake_client, "Q0", 3)
    assert result.truncated is True
    assert result.floor_weight == 306  # o menor peso do pool por peso (MEC, Brasil, Enem)


async def test_usa_o_cache_por_id_limite_e_pool():
    client = FakeGraphQLClient()
    client.route("RelatedEntities", _pools)
    cache = TTLCache()
    await fetch_neighbors(client, "Q0", 10, cache=cache)
    await fetch_neighbors(client, "Q0", 10, cache=cache)
    await fetch_neighbors(client, "Q0", 20, cache=cache)
    assert len(client.calls("RelatedEntities")) == 4  # 2 pools × 2 limites


async def test_nao_cacheia_falha():
    client = FakeGraphQLClient()
    client.route("RelatedEntities", RuntimeError("timeout"))
    cache = TTLCache()
    with pytest.raises(RuntimeError):
        await fetch_neighbors(client, "Q0", 10, cache=cache)
    client.route("RelatedEntities", _pools)
    assert len((await fetch_neighbors(client, "Q0", 10, cache=cache)).rows) == 6


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
