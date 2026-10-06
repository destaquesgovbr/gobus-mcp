"""Formato no fio dos MCP Apps (``fastmcp.Client`` em memória, sem browser).

- ``tools/list``: as tools de app declaram o resource em ``_meta.ui.resourceUri`` e na
  chave legada ``_meta["ui/resourceUri"]``; nenhuma tem ``outputSchema``;
- ``resources/list`` e ``resources/read``: MIME ``text/html;profile=mcp-app``,
  ``prefersBorder``, HTML estático (o handshake está no JS) e **zero** chamadas GraphQL;
- ``tools/call``: ``content`` = ``summary`` (≤ 6 KB, primeiro campo do
  ``structuredContent``), payload válido no pydantic e ≤ 20 KB;
- a extensão ``io.modelcontextprotocol/ui`` é anunciada.
"""

import json

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.payloads.readability import ReadabilityReport
from tests.conftest import FakeGraphQLClient
from tests.fixtures.ui.build import (
    READABILITY_BASE,
    readability_articles,
    readability_rows,
    route_readability,
)

MIME = "text/html;profile=mcp-app"
SUMMARY_MAX = 6 * 1024
PAYLOAD_MAX = 20_000
HTML_MAX = 60 * 1024

# tool de app → (URI do resource, modelo do payload)
APP_TOOLS = {
    "gobus_get_readability_recommendations": ("ui://readability-dashboard", ReadabilityReport),
}


def _route_readability(client):
    route_readability(client, readability_rows(READABILITY_BASE), articles=readability_articles())


# cenários de chamada: (argumentos, rotas do fake)
APP_CALLS = {
    "gobus_get_readability_recommendations": [
        ({"days": 90, "date_to": "2026-06-30"}, _route_readability),
        ({"agency_key": "saude", "days": 90, "date_to": "2026-06-30"}, _route_readability),
        ({}, _route_readability),
    ],
}
CALL_CASES = [
    pytest.param(name, args, route, id=f"{name}-{i}")
    for name, cases in APP_CALLS.items()
    for i, (args, route) in enumerate(cases)
]


@pytest.fixture
def deps(monkeypatch):
    fake = FakeGraphQLClient()
    container = server.Deps(client=fake, catalog=AgencyCatalog(fake))
    monkeypatch.setattr(server, "_deps", container)
    return container


async def _tools() -> dict:
    async with Client(server.mcp) as client:
        return {t.name: t for t in await client.list_tools()}


# ── tools/list ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(APP_TOOLS))
async def test_tool_de_app_declara_o_resource_nas_duas_chaves(name):
    tool = (await _tools())[name]
    uri, _ = APP_TOOLS[name]

    assert tool.meta["ui"]["resourceUri"] == tool.meta["ui/resourceUri"] == uri
    assert tool.outputSchema is None
    assert tool.annotations.readOnlyHint is True


async def test_tools_sem_app_nao_declaram_ui():
    for name, tool in (await _tools()).items():
        if name in APP_TOOLS:
            continue
        meta = tool.meta or {}
        assert "ui" not in meta and "ui/resourceUri" not in meta, name


# ── resources ───────────────────────────────────────────────────────────────


async def test_resources_de_app_listados_com_mime_e_prefers_border():
    async with Client(server.mcp) as client:
        resources = {str(r.uri): r for r in await client.list_resources()}

    for uri, _ in APP_TOOLS.values():
        resource = resources[uri]
        assert resource.mimeType == MIME
        assert resource.meta["ui"]["prefersBorder"] is True
        assert resource.description


@pytest.mark.parametrize("uri", [uri for uri, _ in APP_TOOLS.values()])
async def test_resources_read_html_estatico_sem_graphql(deps, uri):
    async with Client(server.mcp) as client:
        result = await client.read_resource_mcp(uri)
        again = await client.read_resource_mcp(uri)

    (content,) = result.contents
    assert content.mimeType == MIME
    assert content.meta["ui"]["prefersBorder"] is True
    html = content.text
    assert html.lower().startswith("<!doctype html>")
    for text in ("ui/initialize", "appInfo", "ui/notifications/size-changed", "2026-01-26"):
        assert text in html, text
    assert "innerHTML" not in html
    assert len(html.encode()) <= HTML_MAX
    assert again.contents[0].text == html  # estático: mesmo HTML a cada leitura
    assert deps.client.execute.await_count == 0  # nenhum I/O no resources/read


# ── tools/call ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "args", "route"), CALL_CASES)
async def test_call_tool_devolve_summary_e_payload_valido(deps, name, args, route):
    route(deps.client)

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp(name, args)

    assert result.isError is False, result.content
    sc = result.structuredContent
    (block,) = result.content
    assert block.type == "text"
    assert block.text == sc["summary"]
    assert next(iter(sc)) == "summary"  # o Claude Code mostra o structuredContent
    assert len(sc["summary"].encode()) <= SUMMARY_MAX
    assert len(json.dumps(sc, ensure_ascii=False).encode()) <= PAYLOAD_MAX
    _, model = APP_TOOLS[name]
    report = model.model_validate(sc)
    assert report.schema_version == 1
    assert sc["schemaVersion"] == 1 and sc["tool"] == name


@pytest.mark.parametrize("name", list(APP_TOOLS))
async def test_call_tool_com_graphql_falhando_devolve_is_error(deps, name):
    deps.client.execute.side_effect = GobusGraphQLError([{"message": "graphql-api fora do ar"}])
    args = APP_CALLS[name][0][0]

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp(name, args)

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text.strip()


async def test_servidor_anuncia_a_extensao_ui():
    async with Client(server.mcp) as client:
        capabilities = client.initialize_result.capabilities

    assert "io.modelcontextprotocol/ui" in (capabilities.extensions or {})
