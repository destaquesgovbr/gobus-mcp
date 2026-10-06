"""Servidor MCP em memória (fastmcp.Client): registro das tools e formato da resposta.

Toda tool é ``-> str`` sem ``outputSchema``: o host recebe o Markdown cru em ``content``
e nenhum ``structuredContent`` (antes, o fastmcp 3.4 embrulhava em ``{"result": …}``).
"""

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.agency_catalog import AgencyCatalog
from tests.conftest import FakeGraphQLClient

TOOL_ARGS = {
    "gobus_search_news": {"query": "vacina"},
    "gobus_get_article": {"unique_id": "abc"},
    "gobus_resolve_entity": {"query": "Lula"},
    "gobus_get_entity_profile": {"entity_name": "Lula"},
    "gobus_get_entity_network": {"entity_id": "Q1"},
    "gobus_get_agency_analytics": {
        "agencies": ["saude"],
        "date_from": "2026-09-01",
        "date_to": "2026-09-30",
    },
    "gobus_detect_trends": {},
    "gobus_get_agency_summary": {"agency_key": "saude"},
    "gobus_get_readability_recommendations": {"agency_key": "saude"},
    "gobus_get_policy_lifecycle": {"policy_name": "Pé-de-Meia"},
    "gobus_detect_anomalies": {},
    "gobus_forecast_trends": {},
    "gobus_score_article": {"unique_id": "abc"},
}


@pytest.fixture
def deps(monkeypatch):
    fake = FakeGraphQLClient()
    container = server.Deps(client=fake, catalog=AgencyCatalog(fake))
    monkeypatch.setattr(server, "_deps", container)
    return container


def test_deps_padrao_compartilha_um_cliente():
    deps = server.get_deps()
    assert isinstance(deps, server.Deps)
    assert isinstance(deps.catalog, AgencyCatalog)
    assert deps.catalog._client is deps.client
    assert deps.activity is None  # AgencyActivityService entra no G2


def test_get_deps_le_o_conteiner_trocado_pelos_testes(deps):
    assert server.get_deps() is deps


async def test_lista_13_tools_sem_output_schema_e_somente_leitura():
    async with Client(server.mcp) as client:
        tools = await client.list_tools()

    assert {t.name for t in tools} == set(TOOL_ARGS)
    for tool in tools:
        assert tool.outputSchema is None, tool.name
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is True, tool.name


@pytest.mark.parametrize(("name", "args"), list(TOOL_ARGS.items()), ids=list(TOOL_ARGS))
async def test_call_tool_devolve_markdown_sem_structured_content(deps, name, args):
    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp(name, args)

    assert not result.isError, result.content
    assert result.structuredContent is None
    (block,) = result.content
    assert block.type == "text"
    assert block.text.strip()
    assert not block.text.lstrip().startswith('{"result"')


async def test_tools_usam_o_cliente_do_conteiner(deps):
    deps.client.route(
        "GetArticle",
        {
            "article": {
                "uniqueId": "abc",
                "title": "Título do conteiner",
                "agency": "saude",
                "agencyName": "Ministério da Saúde",
                "publishedAt": "2026-10-01T10:00:00Z",
                "url": "https://www.gov.br/x",
                "content": "Corpo.",
            }
        },
    )
    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp("gobus_get_article", {"unique_id": "abc"})

    assert "Título do conteiner" in result.content[0].text
    assert deps.client.calls("GetArticle") == [{"uniqueId": "abc"}]
