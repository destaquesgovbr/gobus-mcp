"""Compatibilidade de schema: a query nova primeiro; se a graphql-api ainda não tem o campo
("Cannot query field", argumento ou tipo desconhecido), a feature fica marcada como ausente
por 1 h e a query antiga responde."""

import pytest

from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.schema_compat import (
    COMPAT,
    FEATURE_TTL,
    SchemaCompat,
    execute_compatible,
    is_schema_mismatch,
)
from tests.conftest import FakeGraphQLClient

NEW = "query Nova($x: Int) { nova(x: $x) { a b } }"
OLD = "query NovaLegacy($x: Int) { nova(x: $x) { a } }"
MISSING_FIELD = GobusGraphQLError(
    [{"message": "Cannot query field 'b' on type 'Nova'. Did you mean 'a'?"}]
)


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    "message",
    [
        "Cannot query field 'url' on type 'ArticleSummary'.",
        "Unknown argument 'orderBy' on field 'Query.relatedEntities'.",
        "Unknown type 'RelatedEntityOrder'.",
        "Value 'LIFT' does not exist in 'RelatedEntityOrder' enum.",
    ],
)
def test_reconhece_erros_de_schema(message):
    assert is_schema_mismatch(GobusGraphQLError([{"message": message}]))


@pytest.mark.parametrize(
    "exc",
    [
        GobusGraphQLError([{"message": "timeout ao consultar o Postgres"}]),
        RuntimeError("Cannot query field 'x'"),  # não é erro da GraphQL
        TimeoutError(),
    ],
)
def test_outros_erros_nao_sao_de_schema(exc):
    assert not is_schema_mismatch(exc)


async def test_feature_presente_usa_a_query_nova():
    client = FakeGraphQLClient()
    client.route("Nova", {"nova": {"a": 1, "b": 2}})
    compat = SchemaCompat()

    data, ok = await execute_compatible(client, "feat", NEW, OLD, {"x": 1}, compat=compat)

    assert ok is True
    assert data == {"nova": {"a": 1, "b": 2}}
    assert client.calls("Nova") == [{"x": 1}]
    assert compat.available("feat")


async def test_campo_ausente_cai_na_query_antiga_e_marca_a_feature():
    client = FakeGraphQLClient()
    client.route("Nova", MISSING_FIELD)
    client.route("NovaLegacy", {"nova": {"a": 1}})
    compat = SchemaCompat()

    data, ok = await execute_compatible(client, "feat", NEW, OLD, {"x": 1}, compat=compat)

    assert ok is False
    assert data == {"nova": {"a": 1}}
    assert client.calls("NovaLegacy") == [{"x": 1}]
    assert not compat.available("feat")


async def test_feature_ausente_vai_direto_para_a_query_antiga_por_uma_hora():
    clock = FakeClock()
    client = FakeGraphQLClient()
    client.route("Nova", MISSING_FIELD)
    client.route("NovaLegacy", {"nova": {"a": 1}})
    compat = SchemaCompat(clock=clock)

    await execute_compatible(client, "feat", NEW, OLD, compat=compat)
    clock.now += FEATURE_TTL - 1
    await execute_compatible(client, "feat", NEW, OLD, compat=compat)
    assert len(client.calls("Nova")) == 1  # a 2ª chamada nem tenta a nova
    assert len(client.calls("NovaLegacy")) == 2

    clock.now += 2  # passou 1 h: tenta a nova de novo (o GQL-1 pode ter entrado)
    client.route("Nova", {"nova": {"a": 1, "b": 2}})
    data, ok = await execute_compatible(client, "feat", NEW, OLD, compat=compat)
    assert ok is True
    assert data["nova"]["b"] == 2
    assert compat.available("feat")


async def test_outro_erro_propaga_sem_marcar_a_feature():
    client = FakeGraphQLClient()
    client.route("Nova", GobusGraphQLError([{"message": "boom"}]))
    client.route("NovaLegacy", {"nova": {"a": 1}})
    compat = SchemaCompat()

    with pytest.raises(GobusGraphQLError, match="boom"):
        await execute_compatible(client, "feat", NEW, OLD, compat=compat)
    assert compat.available("feat")
    assert client.calls("NovaLegacy") == []


async def test_features_sao_independentes():
    compat = SchemaCompat()
    compat.mark_absent("a")
    assert not compat.available("a")
    assert compat.available("b")


async def test_compat_padrao_e_o_do_processo_e_e_limpo_entre_testes():
    client = FakeGraphQLClient()
    client.route("Nova", MISSING_FIELD)
    client.route("NovaLegacy", {"nova": {"a": 1}})

    _, ok = await execute_compatible(client, "feat-global", NEW, OLD)

    assert ok is False
    assert not COMPAT.available("feat-global")


def test_compat_do_processo_comeca_limpo():
    # o conftest limpa o COMPAT a cada teste: o teste anterior não vaza
    assert COMPAT.available("feat-global")
