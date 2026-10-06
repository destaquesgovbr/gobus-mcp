"""Comportamento comum de todo MCP App do gobus no mini-host: skeleton com os parâmetros
no ``tool-input``, ``tool-cancelled``, resultado com ``isError``, resultado sem
``structuredContent`` e payload de versão desconhecida (cache de HTML antigo no host)."""

import copy

import pytest

from gobus_mcp.ui import render_app
from tests.browser.conftest import load_fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="session")]

# app → fixture de referência (estado ok)
APPS = {
    "readability_dashboard": "ok",
    "article_scorecard": "scored",
    "anomaly_radar": "ok",
}


def _base(app: str) -> dict:
    return copy.deepcopy(load_fixture(app, APPS[app]))


async def _text(run) -> str:
    return await run.eval("() => document.getElementById('app').textContent")


@pytest.mark.parametrize("app", list(APPS))
async def test_tool_input_mostra_carregando_e_tool_cancelled_avisa(open_host, app):
    fixture = _base(app)
    fixture["result"] = None  # o host só manda o tool-input
    run = await open_host(render_app(app), fixture=fixture)

    await run.app.locator('#app[data-state="loading"] [data-testid="skeleton"]').wait_for()
    await run.notify("ui/notifications/tool-cancelled", {"reason": "user action"})
    await run.app.locator('#app[data-state="cancelled"]').wait_for()

    assert "cancelada" in (await _text(run)).lower()
    assert run.problems == []


@pytest.mark.parametrize("app", list(APPS))
async def test_resultado_com_is_error_mostra_o_texto(open_host, app):
    fixture = _base(app)
    fixture["result"] = {
        "content": [{"type": "text", "text": "Erro: graphql-api fora do ar"}],
        "isError": True,
    }
    run = await open_host(render_app(app), fixture=fixture)

    assert await run.wait_rendered() == "error"
    assert "graphql-api fora do ar" in await _text(run)
    assert run.problems == []


@pytest.mark.parametrize("app", list(APPS))
async def test_resultado_sem_structured_content_mostra_o_texto(open_host, app):
    fixture = _base(app)
    fixture["result"] = {"content": [{"type": "text", "text": "Artigo não encontrado"}]}
    run = await open_host(render_app(app), fixture=fixture)

    assert await run.wait_rendered() == "text"
    assert "Artigo não encontrado" in await _text(run)
    assert run.problems == []


@pytest.mark.parametrize("app", list(APPS))
@pytest.mark.parametrize("change", [{"schemaVersion": 2}, {"kind": "gobus.outro"}])
async def test_payload_de_versao_desconhecida_avisa(open_host, app, change):
    fixture = _base(app)
    fixture["result"]["structuredContent"].update(change)
    run = await open_host(render_app(app), fixture=fixture)

    assert await run.wait_rendered() == "incompatible"
    assert "incompatível" in await _text(run)
    assert run.problems == []
