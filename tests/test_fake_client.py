"""Testes do FakeGraphQLClient (infra de teste): despacho por nome de operação."""

import asyncio

import pytest

from tests.conftest import FakeGraphQLClient, operation_name

_Q_A = """
query AlphaQuery($x: Int!) {
  alpha(x: $x) { value }
}
"""

_Q_B = """
query BetaQuery {
  beta { value }
}
"""

_Q_ANON = """
{
  gamma { value }
}
"""


def test_operation_name_extrai_nome_ou_none():
    assert operation_name(_Q_A) == "AlphaQuery"
    assert operation_name(_Q_B) == "BetaQuery"
    assert operation_name(_Q_ANON) is None


async def test_route_despacha_por_nome_de_operacao_em_gather():
    client = FakeGraphQLClient()
    client.route("AlphaQuery", {"alpha": {"value": 1}})
    client.route("BetaQuery", {"beta": {"value": 2}})

    b, a = await asyncio.gather(client.execute(_Q_B), client.execute(_Q_A, {"x": 1}))

    assert a == {"alpha": {"value": 1}}
    assert b == {"beta": {"value": 2}}


async def test_route_aceita_callable_com_variaveis():
    client = FakeGraphQLClient()
    client.route("AlphaQuery", lambda variables: {"alpha": {"value": variables["x"] * 10}})

    assert await client.execute(_Q_A, {"x": 3}) == {"alpha": {"value": 30}}
    assert await client.execute(_Q_A, {"x": 4}) == {"alpha": {"value": 40}}


async def test_route_com_excecao_levanta():
    client = FakeGraphQLClient()
    client.route("AlphaQuery", RuntimeError("upstream caiu"))

    with pytest.raises(RuntimeError, match="upstream caiu"):
        await client.execute(_Q_A, {"x": 1})


async def test_operacao_sem_rota_falha_com_mensagem_clara():
    client = FakeGraphQLClient()
    client.route("AlphaQuery", {"alpha": {}})

    with pytest.raises(AssertionError, match="BetaQuery"):
        await client.execute(_Q_B)


async def test_calls_registra_variaveis_por_operacao():
    client = FakeGraphQLClient()
    client.route("AlphaQuery", {"alpha": {}})
    client.route("BetaQuery", {"beta": {}})

    await client.execute(_Q_A, {"x": 1})
    await client.execute(_Q_B)
    await client.execute(_Q_A, {"x": 2})

    assert client.calls("AlphaQuery") == [{"x": 1}, {"x": 2}]
    assert client.calls("BetaQuery") == [None]
    assert client.execute.await_count == 3


async def test_set_response_e_set_responses_continuam_compativeis():
    client = FakeGraphQLClient()
    assert await client.execute(_Q_A) == {}

    client.set_response({"alpha": 1})
    assert await client.execute(_Q_B) == {"alpha": 1}

    client.set_responses([{"r": 1}, {"r": 2}])
    assert await client.execute(_Q_A) == {"r": 1}
    assert await client.execute(_Q_B) == {"r": 2}
