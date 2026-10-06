"""Formato no fio dos MCP Apps (``fastmcp.Client`` em memória, sem browser).

- ``tools/list``: as tools de app declaram o resource em ``_meta.ui.resourceUri`` e na
  chave legada ``_meta["ui/resourceUri"]``; nenhuma tem ``outputSchema``;
- ``resources/list`` e ``resources/read``: MIME ``text/html;profile=mcp-app``,
  ``prefersBorder``, HTML estático (o handshake está no JS) e **zero** chamadas GraphQL;
- ``tools/call``: ``content`` = o Markdown completo e ``summary`` = o mesmo texto até 6 KB
  (primeiro campo do ``structuredContent``; idênticos quando cabe), payload válido no
  pydantic e ≤ 20 KB;
- os radares degradam por bloco: GraphQL fora do ar dá ``status: unavailable``, não erro;
- a extensão ``io.modelcontextprotocol/ui`` é anunciada.
"""

import json

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.analytics.render import fit_summary
from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.payloads.anomalies import AnomalyReport
from gobus_mcp.payloads.forecast import ForecastReport
from gobus_mcp.payloads.readability import ReadabilityReport
from gobus_mcp.payloads.scorecard import ScoreReport
from tests.conftest import FakeGraphQLClient
from tests.fixtures.g2 import (
    ACTIVITY_0510,
    NOW_0510,
    many_candidates,
    route_g2,
    scenario_0510,
    theme_ranges_0510,
    trending_rows_0510,
)
from tests.fixtures.ui.build import (
    READABILITY_BASE,
    readability_articles,
    readability_rows,
    route_readability,
    route_score,
)

MIME = "text/html;profile=mcp-app"
SUMMARY_MAX = 6 * 1024
PAYLOAD_MAX = 20_000
HTML_MAX = 60 * 1024

# tool de app → (URI do resource, modelo do payload)
APP_TOOLS = {
    "gobus_get_readability_recommendations": ("ui://readability-dashboard", ReadabilityReport),
    "gobus_score_article": ("ui://article-scorecard", ScoreReport),
    "gobus_detect_anomalies": ("ui://anomaly-radar", AnomalyReport),
    "gobus_forecast_trends": ("ui://forecast-radar", ForecastReport),
}
# tools de app cujo builder propaga a falha da GraphQL (os radares degradam por bloco)
RAISING_TOOLS = ("gobus_get_readability_recommendations", "gobus_score_article")


def _route_readability(client):
    route_readability(client, readability_rows(READABILITY_BASE), articles=readability_articles())


def _route_anomalies(client):
    rows, contexts = scenario_0510()
    route_g2(client, trending=rows, contexts=contexts, activity=ACTIVITY_0510)


def _route_anomalies_0510(client):
    route_g2(client, themes=theme_ranges_0510(), trending=trending_rows_0510())


# cenários de chamada: (argumentos, rotas do fake)
APP_CALLS = {
    "gobus_get_readability_recommendations": [
        ({"days": 90, "date_to": "2026-06-30"}, _route_readability),
        ({"agency_key": "saude", "days": 90, "date_to": "2026-06-30"}, _route_readability),
        ({}, _route_readability),
    ],
    "gobus_score_article": [
        ({"unique_id": "pf-operacao-desarticula-quadrilha"}, route_score),
        (
            {
                "unique_id": "pf-operacao-desarticula-quadrilha",
                "compare_with": "saude-campanha-gripe",
            },
            route_score,
        ),
        ({"unique_id": "pf-operacao-outubro"}, route_score),
    ],
    "gobus_detect_anomalies": [
        ({}, _route_anomalies),
        ({"sensitivity": "high", "domain_filter": "saude"}, _route_anomalies),
        ({}, _route_anomalies_0510),
    ],
    "gobus_forecast_trends": [
        ({}, route_g2),
        ({"horizon_days": 7, "limit": 8}, route_g2),
        ({"horizon_days": 28, "limit": 10}, route_g2),
        ({}, lambda client: route_g2(client, themes=theme_ranges_0510())),
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
    # relógio dos radares no dia dos cenários do G2 (as janelas dependem de "agora")
    monkeypatch.setattr("gobus_mcp.tools.detect_anomalies.now_brt", lambda: NOW_0510)
    monkeypatch.setattr("gobus_mcp.tools.forecast_trends.now_brt", lambda: NOW_0510)
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
    assert sc["summary"] == fit_summary(block.text)  # idênticos quando cabe em 6 KB
    assert next(iter(sc)) == "summary"  # o Claude Code mostra o structuredContent
    assert len(sc["summary"].encode()) <= SUMMARY_MAX
    assert len(json.dumps(sc, ensure_ascii=False).encode()) <= PAYLOAD_MAX
    _, model = APP_TOOLS[name]
    report = model.model_validate(sc)
    assert report.schema_version == 1
    assert sc["schemaVersion"] == 1 and sc["tool"] == name


@pytest.mark.parametrize("name", RAISING_TOOLS)
async def test_call_tool_com_graphql_falhando_devolve_is_error(deps, name):
    deps.client.execute.side_effect = GobusGraphQLError([{"message": "graphql-api fora do ar"}])
    args = APP_CALLS[name][0][0]

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp(name, args)

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text.strip()


async def test_score_article_sem_artigo_devolve_so_texto(deps):
    route_score(deps.client)

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp("gobus_score_article", {"unique_id": "nao-existe"})

    assert result.isError is False
    assert result.structuredContent is None  # o app mostra o texto
    assert "não encontrado" in result.content[0].text


async def test_score_article_aceita_compare_with():
    tool = (await _tools())["gobus_score_article"]

    assert set(tool.inputSchema["properties"]) == {"unique_id", "compare_with"}
    assert tool.inputSchema["properties"]["compare_with"]["default"] == ""


async def test_servidor_anuncia_a_extensao_ui():
    async with Client(server.mcp) as client:
        capabilities = client.initialize_result.capabilities

    assert "io.modelcontextprotocol/ui" in (capabilities.extensions or {})


# ── radares ─────────────────────────────────────────────────────────────────

RADARS = [name for name in APP_TOOLS if name not in RAISING_TOOLS]


@pytest.mark.parametrize("name", RADARS)
async def test_radar_com_graphql_fora_do_ar_devolve_unavailable(deps, name):
    deps.client.execute.side_effect = GobusGraphQLError([{"message": "graphql-api fora do ar"}])

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp(name, {})

    assert result.isError is False
    sc = result.structuredContent
    assert sc["status"] == "unavailable"
    _, model = APP_TOOLS[name]
    model.model_validate(sc)
    assert "fora do ar" in result.content[0].text


async def test_detect_anomalies_com_30_candidatos_content_completo_e_payload_compacto(deps):
    rows, contexts = many_candidates()
    route_g2(deps.client, trending=rows, contexts=contexts, activity=ACTIVITY_0510)

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp("gobus_detect_anomalies", {})

    content = result.content[0].text
    sc = result.structuredContent
    assert "truncado" not in content and "### Metodologia" in content
    assert len(content.encode()) > SUMMARY_MAX  # o Markdown inteiro passa de 6 KB
    assert sc["summary"] == fit_summary(content)
    assert len(sc["summary"].encode()) <= SUMMARY_MAX
    assert len(json.dumps(sc, ensure_ascii=False).encode()) <= PAYLOAD_MAX
    assert sum(sc["entities"]["omitted"].values()) == 30 - len(sc["entities"]["signals"])


async def test_detect_anomalies_com_parametro_invalido_devolve_so_texto(deps):
    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp("gobus_detect_anomalies", {"sensitivity": "maxima"})

    assert result.isError is False
    assert result.structuredContent is None  # o app mostra o texto com as opções
    assert "inválido" in result.content[0].text
    assert deps.client.execute.await_count == 0
