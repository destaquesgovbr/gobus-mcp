"""Servidor MCP em memória (fastmcp.Client): registro das tools e formato da resposta.

Toda tool é ``-> str`` sem ``outputSchema``: o host recebe o Markdown cru em ``content``
e nenhum ``structuredContent`` (antes, o fastmcp 3.4 embrulhava em ``{"result": …}``).
"""

import pytest
from fastmcp import Client

from gobus_mcp import server
from gobus_mcp.agency_activity import AgencyActivityService
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from tests.conftest import FakeGraphQLClient
from tests.fixtures.g2 import route_g2

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
    # G2: snapshot de atividade e cache compartilhados pelas tools de anomalia e forecast
    assert isinstance(deps.activity, AgencyActivityService)
    assert deps.activity._client is deps.client
    assert deps.activity._catalog is deps.catalog
    assert isinstance(deps.cache, TTLCache)


def test_deps_sem_activity_cria_o_servico_com_o_cliente_e_o_catalogo():
    fake = FakeGraphQLClient()
    deps = server.Deps(client=fake, catalog=AgencyCatalog(fake))
    assert isinstance(deps.activity, AgencyActivityService)
    assert deps.activity._client is fake


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


async def test_readability_aceita_date_to_e_nao_fixa_benchmark():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    tool = tools["gobus_get_readability_recommendations"]
    assert "date_to" in tool.inputSchema["properties"]
    assert "~33" not in (tool.description or "")


async def test_score_article_documenta_recusa_e_benchmark_ancorado():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    description = tools["gobus_score_article"].description or ""
    assert "indisponível" in description
    assert "90 dias antes" in description


async def test_detect_trends_documenta_razao_sem_sobreposicao():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    description = tools["gobus_detect_trends"].description or ""
    assert "sem sobreposição" in description


async def test_resources_json_declaram_mime_application_json():
    async with Client(server.mcp) as client:
        resources = {str(r.uri): r for r in await client.list_resources()}

    assert resources["gobus://health/pipelines"].mimeType == "application/json"


async def test_readability_report_declara_mime_json():
    async with Client(server.mcp) as client:
        resources = {str(r.uri): r for r in await client.list_resources()}

    assert resources["gobus://readability-report"].mimeType == "application/json"


async def test_detect_anomalies_aceita_domain_filter_e_documenta_dominios_e_classes():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    tool = tools["gobus_detect_anomalies"]
    assert set(tool.inputSchema["properties"]) == {"sensitivity", "domain_filter"}
    description = tool.description or ""
    for text in ("HEALTH", "OTHER", "saude", "defeso", "silêncio coordenado", "rajada",
                 "share-of-voice", "entityCoverage"):  # fmt: skip
        assert text in description, text
    assert "volumeRatio" not in description or "nunca" in description


async def test_forecast_documenta_horizonte_efetivo_e_share_of_voice():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    description = tools["gobus_forecast_trends"].description or ""
    for text in ("1–28", "share-of-voice", "feriado", "recuperação"):
        assert text in description, text
    assert "informativo" not in description


async def test_tools_g2_usam_o_cache_e_o_snapshot_do_conteiner(deps):
    route_g2(deps.client)

    async with Client(server.mcp) as client:
        first = await client.call_tool_mcp("gobus_detect_anomalies", {"domain_filter": "saude"})
        await client.call_tool_mcp("gobus_forecast_trends", {"horizon_days": 7})
        await client.call_tool_mcp("gobus_detect_anomalies", {})

    assert "Detector de Anomalias" in first.content[0].text
    assert "**Domínio:** Saúde" in first.content[0].text
    # o snapshot de atividade é um só (cache de 6 h do serviço do contêiner)
    assert len(deps.client.calls("AgencyActivitySnapshot")) == 1
    # temas: 4 ranges das anomalias + 2 novos do forecast (14 e 84); a 2ª chamada usa o cache
    assert sorted(v["days"] for v in deps.client.calls("ThemeRangeCounts")) == [
        3,
        7,
        14,
        21,
        28,
        84,
    ]


async def test_detect_anomalies_com_dominio_invalido_devolve_opcoes(deps):
    route_g2(deps.client)

    async with Client(server.mcp) as client:
        result = await client.call_tool_mcp("gobus_detect_anomalies", {"domain_filter": "xyz"})

    assert not result.isError
    assert "inválido" in result.content[0].text
    assert "HEALTH" in result.content[0].text


async def test_health_usa_o_snapshot_de_atividade_do_conteiner(deps):
    route_g2(deps.client)

    async with Client(server.mcp) as client:
        await client.call_tool_mcp("gobus_forecast_trends", {})
        contents = await client.read_resource("gobus://health/pipelines")

    import json

    data = json.loads(contents[0].text)
    assert data["pipelines"]["agency_activity"]["status"] == "ok"
    assert len(deps.client.calls("AgencyActivitySnapshot")) == 1
