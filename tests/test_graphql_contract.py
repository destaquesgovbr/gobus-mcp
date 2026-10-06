"""Contrato GraphQL: toda constante ``*_QUERY`` do gobus é nomeada, só de leitura e
válida contra o SDL da graphql-api.

O SDL vem de ``tests/fixtures/schema.graphql``, snapshot obtido por introspecção
(``python tests/fixtures/refresh_schema.py``). ``GOBUS_SCHEMA_SDL=<arquivo>`` troca o
SDL, por exemplo para pré-validar contra o schema de um PR da graphql-api.
"""

import importlib
import os
import pkgutil
from pathlib import Path

import pytest
from graphql import (
    GraphQLSchema,
    OperationDefinitionNode,
    OperationType,
    build_schema,
    parse,
    validate,
)

import gobus_mcp

SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "schema.graphql"

# Bugs conhecidos ainda não consertados (constante → motivo). O xfail é estrito: quando o
# conserto entrar, o teste passa a "XPASS" e falha, lembrando de tirar daqui.
KNOWN_BROKEN: dict[str, str] = {}


def _collect_queries() -> list[tuple[str, str]]:
    """Toda constante de módulo ``*_QUERY`` (str) dos pacotes de ``gobus_mcp``."""
    found: list[tuple[str, str]] = []
    seen: set[int] = set()
    for info in pkgutil.walk_packages(gobus_mcp.__path__, prefix="gobus_mcp."):
        if info.name.endswith("__main__"):  # importar o __main__ sobe o servidor
            continue
        module = importlib.import_module(info.name)
        for attr, value in sorted(vars(module).items()):
            if attr.endswith("_QUERY") and isinstance(value, str) and id(value) not in seen:
                seen.add(id(value))
                found.append((f"{info.name}.{attr}", value))
    return found


QUERIES = _collect_queries()


def _params(*, mark_known_broken: bool) -> list:
    params = []
    for name, query in QUERIES:
        marks = []
        if mark_known_broken and name in KNOWN_BROKEN:
            marks.append(pytest.mark.xfail(reason=KNOWN_BROKEN[name], strict=True))
        params.append(pytest.param(query, id=name, marks=marks))
    return params


@pytest.fixture(scope="module")
def schema() -> GraphQLSchema:
    path = Path(os.environ.get("GOBUS_SCHEMA_SDL") or SNAPSHOT_PATH)
    return build_schema(path.read_text(encoding="utf-8"))


def _operations(query: str) -> list[OperationDefinitionNode]:
    return [d for d in parse(query).definitions if isinstance(d, OperationDefinitionNode)]


def test_coleta_encontra_as_queries_do_pacote():
    names = {name for name, _ in QUERIES}
    assert len(QUERIES) >= 20
    assert "gobus_mcp.tools.search_news._SEARCH_QUERY" in names
    assert "gobus_mcp.agency_catalog._AGENCIES_QUERY" in names
    assert set(KNOWN_BROKEN) <= names, "KNOWN_BROKEN cita constante que não existe mais"


@pytest.mark.parametrize("query", _params(mark_known_broken=False))
def test_query_e_operacao_nomeada_de_leitura(query: str):
    operations = _operations(query)
    assert len(operations) == 1, "uma operação por constante"
    (operation,) = operations
    assert operation.operation is OperationType.QUERY, "só queries de leitura (nunca mutation)"
    assert operation.name is not None, "operação anônima: nomeie (query NomeDaOperacao ...)"


@pytest.mark.parametrize("query", _params(mark_known_broken=True))
def test_query_valida_contra_o_sdl(query: str, schema: GraphQLSchema):
    errors = validate(schema, parse(query))
    assert not errors, "\n".join(e.message for e in errors)


@pytest.mark.live
def test_snapshot_igual_a_introspeccao_ao_vivo():
    from tests.fixtures.refresh_schema import fetch_sdl

    assert fetch_sdl() == SNAPSHOT_PATH.read_text(encoding="utf-8"), (
        "SDL ao vivo divergiu do snapshot: rode python tests/fixtures/refresh_schema.py"
    )
