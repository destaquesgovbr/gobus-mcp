"""Bridge JSON-RPC raw (``_bridge.js``) contra o mini-host: handshake, contexto, altura,
requests do host e a API do app condicionada às ``hostCapabilities``.

Usa um app de sonda (``probe_app.js``) montado com ``assemble_app``: o mesmo núcleo
(bridge, dom, svg) dos apps reais.
"""

from pathlib import Path

import pytest

import gobus_mcp
from gobus_mcp.ui import assemble_app
from tests.browser.conftest import THEMES, host_context

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="session")]

PROBE_HTML = assemble_app(
    name="probe",
    title="Probe",
    css="",
    js=(Path(__file__).parent / "probe_app.js").read_text(),
)

FIXTURE = {
    "toolName": "gobus_probe",
    "toolInput": {"a": 1},
    "result": {
        "content": [{"type": "text", "text": "md"}],
        "structuredContent": {"summary": "md", "x": 1},
        "isError": False,
    },
    "toolCalls": [
        {
            "name": "gobus_probe",
            "arguments": {"x": 1},
            "result": {
                "content": [{"type": "text", "text": "ok"}],
                "structuredContent": {"y": 2},
                "isError": False,
            },
        }
    ],
}


async def _probe(open_host, **kwargs):
    run = await open_host(PROBE_HTML, fixture=FIXTURE, **kwargs)
    await run.wait_testid("result")
    await run.wait_rendered()
    return run


async def _click(run, testid: str) -> str:
    await run.app.locator(f'[data-testid="{testid}"]').click()
    out = run.app.locator(f'[data-testid="{testid}-out"]')
    await out.wait_for()
    return await out.text_content()


async def test_handshake_na_ordem_da_spec(open_host):
    run = await _probe(open_host)
    gb = await run.gb()

    # o app só fala depois do initialize: primeiro a request, depois a notificação
    assert gb["log"][:2] == ["ui/initialize", "ui/notifications/initialized"]
    init = gb["init"]
    assert init["protocolVersion"] == "2026-01-26"
    assert init["appInfo"] == {"name": "gobus-probe", "version": gobus_mcp.__version__}
    assert init["appCapabilities"]["availableDisplayModes"] == ["inline", "fullscreen"]
    # o host responde, e só depois do initialized manda tool-input e tool-result
    assert gb["sent"][:3] == [
        "response:1",
        "ui/notifications/tool-input",
        "ui/notifications/tool-result",
    ]
    assert await run.app.get_by_test_id("input").text_content() == '{"a":1}'
    result = await run.app.get_by_test_id("result").text_content()
    assert '"structuredContent":{"summary":"md","x":1}' in result
    assert run.problems == [] and run.dialogs == []


async def test_aplica_tema_variaveis_e_modo_do_host_context(open_host):
    run = await _probe(open_host, theme="dark")

    root = await run.eval(
        """() => ({
          theme: document.documentElement.dataset.theme,
          mode: document.documentElement.dataset.mode,
          scheme: document.documentElement.style.colorScheme,
          bg: getComputedStyle(document.documentElement)
                .getPropertyValue('--color-background-primary').trim(),
        })"""
    )
    assert root == {
        "theme": "dark",
        "mode": "inline",
        "scheme": "dark",
        "bg": THEMES["dark"]["--color-background-primary"],
    }
    assert await run.app.get_by_test_id("context-theme").text_content() == "dark"
    assert run.problems == []


async def test_host_context_changed_mescla_o_contexto(open_host):
    run = await _probe(open_host, theme="dark")

    await run.notify("ui/notifications/host-context-changed", {"theme": "light"})
    await run.app.locator('[data-testid="context-theme"]:text-is("light")').wait_for()

    theme, bg = await run.eval(
        """() => [document.documentElement.dataset.theme,
                  getComputedStyle(document.documentElement)
                    .getPropertyValue('--color-background-primary').trim()]"""
    )
    assert theme == "light"
    assert bg == THEMES["dark"]["--color-background-primary"]  # variáveis não reenviadas ficam
    assert run.problems == []


async def test_ignora_variaveis_com_url(open_host):
    ctx = host_context("light")
    ctx["styles"]["variables"]["--color-background-primary"] = "url(https://x.example/a.png)"
    run = await _probe(open_host, context=ctx)

    bg = await run.eval(
        "() => document.documentElement.style.getPropertyValue('--color-background-primary')"
    )
    assert bg == ""
    assert run.problems == []


async def test_size_changed_com_altura_do_conteudo(open_host):
    run = await _probe(open_host)
    gb = await run.gb()

    first = gb["sizes"][-1]
    assert 100 <= first["height"] <= 2000
    assert first["width"] > 0

    assert await _click(run, "grow") == "ok"
    await run.wait_host(
        f"gb.sizes.length && gb.sizes[gb.sizes.length - 1].height > {first['height'] + 500}"
    )
    iframe_height = await run.page.evaluate("document.getElementById('app').offsetHeight")
    assert iframe_height > first["height"] + 500
    assert run.problems == []


async def test_resource_teardown_responde_resultado_vazio(open_host):
    run = await _probe(open_host)

    response = await run.request("ui/resource-teardown", {})

    assert response["result"] == {}
    await run.wait_testid("teardown")
    assert run.problems == []


async def test_request_desconhecido_responde_method_not_found(open_host):
    run = await _probe(open_host)

    response = await run.request("ui/nao-existe", {})

    assert response["error"]["code"] == -32601
    assert run.problems == []


async def test_tool_cancelled_chega_ao_app(open_host):
    run = await _probe(open_host)

    await run.notify("ui/notifications/tool-cancelled", {"reason": "user action"})

    await run.wait_testid("cancelled")
    assert await run.app.get_by_test_id("cancelled").text_content() == "user action"


async def test_ignora_mensagem_que_nao_e_jsonrpc(open_host):
    run = await _probe(open_host)

    await run.page.evaluate(
        """() => document.getElementById('app').contentWindow.postMessage(
             {method: 'ui/notifications/tool-input', params: {arguments: {evil: 1}}}, '*')"""
    )
    await run.page.wait_for_timeout(100)

    assert await run.app.get_by_test_id("input").text_content() == '{"a":1}'


async def test_call_tool_passa_pelo_host(open_host):
    run = await _probe(open_host)

    out = await _click(run, "call")

    gb = await run.gb()
    assert gb["toolCalls"] == [{"name": "gobus_probe", "arguments": {"x": 1}}]
    assert '"structuredContent":{"y":2}' in out
    assert run.problems == []


async def test_send_message_e_update_model_context_com_content_array(open_host):
    run = await _probe(open_host)

    await _click(run, "message")
    await _click(run, "context")

    gb = await run.gb()
    assert gb["messages"] == [{"role": "user", "content": [{"type": "text", "text": "olá"}]}]
    assert gb["ctx"] == [{"content": [{"type": "text", "text": "contexto"}]}]
    assert run.problems == []


async def test_open_link_so_https(open_host):
    run = await _probe(open_host)

    assert (await _click(run, "link-http")).startswith("erro")
    await _click(run, "link-https")

    gb = await run.gb()
    assert gb["links"] == ["https://www.gov.br/x"]
    assert run.problems == []


async def test_api_condicionada_as_capacidades_do_host(open_host):
    run = await _probe(open_host, capabilities={})

    for testid in ("call", "message", "context", "link-https"):
        assert (await _click(run, testid)).startswith("erro"), testid

    gb = await run.gb()
    assert gb["toolCalls"] == [] and gb["messages"] == [] and gb["ctx"] == []
    assert gb["links"] == []
    assert await _click(run, "caps") == '{"tools":false,"full":true}'
    assert run.problems == []


async def test_request_display_mode_quando_disponivel(open_host):
    run = await _probe(open_host)

    out = await _click(run, "fullscreen")

    gb = await run.gb()
    assert gb["displayModes"] == ["fullscreen"]
    assert '"mode":"fullscreen"' in out
    await run.app.locator('html[data-mode="fullscreen"]').wait_for(state="attached")
    assert run.problems == []


async def test_request_display_mode_indisponivel_nao_pede_ao_host(open_host):
    ctx = host_context("light", availableDisplayModes=["inline"])
    run = await _probe(open_host, context=ctx)

    assert (await _click(run, "fullscreen")).startswith("erro")

    gb = await run.gb()
    assert gb["displayModes"] == []
    assert run.problems == []
