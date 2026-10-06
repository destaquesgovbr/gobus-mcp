"""``ui://forecast-radar`` no mini-host: todas as fixtures × claro/escuro × 320/760 px e as
interações (radar em escala log2 com o anel 1×, top-3 com momentum, horizonte por
``tools/call``, "explicar" por ``ui/message``, contexto do modelo)."""

import math

import pytest

from gobus_mcp.ui import render_app
from tests.browser.conftest import fixture_names, host_context, load_fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="session")]

APP = "forecast_radar"
TOOL = "gobus_forecast_trends"
STATES = [state for app, state in fixture_names() if app == APP]


async def _open(open_host, state: str, **kwargs):
    fixture = load_fixture(APP, state)
    run = await open_host(render_app(APP), fixture=fixture, **kwargs)
    await run.wait_rendered()
    return run, fixture


async def _fullscreen(open_host, state: str, **kwargs):
    context = host_context(kwargs.pop("theme", "light"), display_mode="fullscreen")
    return await _open(open_host, state, context=context, **kwargs)


def _sc(fixture: dict) -> dict:
    return fixture["result"]["structuredContent"]


async def _app_text(run) -> str:
    return await run.eval("() => document.getElementById('app').textContent")


async def _attr(run, testid: str, name: str) -> float:
    return float(await run.app.get_by_test_id(testid).get_attribute(name))


async def test_ha_fixtures_dos_estados_principais():
    assert {"ok", "partial", "unavailable", "empty", "recovery", "xss"} <= set(STATES)


@pytest.mark.parametrize("width", [320, 760])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("state", STATES)
async def test_fixture_renderiza_limpa(open_host, state, theme, width):
    fixture = load_fixture(APP, state)
    run = await open_host(render_app(APP), fixture=fixture, theme=theme, width=width)

    rendered = await run.wait_rendered()

    assert rendered == _sc(fixture)["status"]
    gb = await run.gb()
    assert 100 <= gb["sizes"][-1]["height"] <= 2000
    assert await run.no_horizontal_overflow()
    assert await run.eval("() => document.documentElement.dataset.theme") == theme
    assert run.problems == [] and run.dialogs == []
    await run.screenshot(f"{APP}-{state}-{theme}-{width}")


@pytest.mark.parametrize("width", [320, 760])
@pytest.mark.parametrize("state", ["ok", "partial", "xss"])
async def test_fullscreen_renderiza_limpo(open_host, state, width):
    run, _ = await _fullscreen(open_host, state, width=width)

    assert await run.app.get_by_test_id("table-windows").count() == 1
    assert await run.no_horizontal_overflow()
    gb = await run.gb()
    assert 100 <= gb["sizes"][-1]["height"] <= 2000
    assert run.problems == [] and run.dialogs == []
    await run.screenshot(f"{APP}-{state}-fullscreen-{width}")


async def test_radar_nao_amplia_alem_do_desenho_em_tela_larga(open_host):
    # em host largo o SVG (viewBox de até 600 px) não pode crescer e engordar os rótulos
    run, _ = await _fullscreen(open_host, "ok", width=1280)

    box = await run.app.get_by_test_id("radar").bounding_box()
    view_box = await run.app.get_by_test_id("radar").get_attribute("viewBox")
    assert box["width"] <= float(view_box.split()[2]) + 1
    assert run.problems == []


async def test_radar_log2_com_anel_1x_um_eixo_por_tema(open_host):
    run, fixture = await _open(open_host, "ok")
    themes = _sc(fixture)["themes"]

    assert await run.app.get_by_test_id("radar").count() == 1
    assert await run.app.locator('[data-testid^="axis-"]').count() == len(themes)
    cx, cy = await _attr(run, "ring-1x", "cx"), await _attr(run, "ring-1x", "cy")
    ring = await _attr(run, "ring-1x", "r")
    for i, theme in enumerate(themes):
        point = f"point-{i}"
        assert await run.app.get_by_test_id(point).get_attribute("data-label") == theme["label"]
        x, y = await _attr(run, point, "cx"), await _attr(run, point, "cy")
        distance = math.hypot(x - cx, y - cy)
        multiplier = theme["weeklyMultiplier"]
        # log2: acima de 1× fica fora do anel, abaixo fica dentro
        if multiplier > 1.05:
            assert distance > ring + 1, theme["label"]
        elif multiplier < 0.95:
            assert distance < ring - 1, theme["label"]
    assert run.problems == []


async def test_top_3_com_momentum_e_artigos_esperados(open_host):
    run, fixture = await _open(open_host, "ok")
    themes = _sc(fixture)["themes"]

    items = run.app.locator('[data-testid^="top-"]')
    assert await items.count() == 3
    for i, theme in enumerate(themes[:3]):
        item = run.app.get_by_test_id(f"top-{i}")
        assert theme["label"] in await item.text_content()
        badge = run.app.get_by_test_id(f"momentum-{i}")
        assert await badge.get_attribute("data-momentum") == theme["momentum"]
    first = await run.app.get_by_test_id("top-0").text_content()
    assert "acelerando" in first and "×/semana" in first
    expected = themes[0]["projection"]["expectedArticles"]
    assert f"{expected:.0f}" in first
    assert run.problems == []


async def test_horizonte_pela_mesma_tool(open_host):
    run, fixture = await _fullscreen(open_host, "ok")
    limit = _sc(fixture)["params"]["limit"]

    assert await run.app.get_by_test_id("horizon-21").get_attribute("aria-pressed") == "true"
    await run.app.get_by_test_id("horizon-7").click()
    await run.app.locator('[data-testid="horizon-7"][aria-pressed="true"]').wait_for()

    gb = await run.gb()
    assert gb["toolCalls"] == [{"name": TOOL, "arguments": {"horizon_days": 7, "limit": limit}}]
    assert "7 dias" in await run.app.get_by_test_id("chip-horizon").text_content()
    await run.app.get_by_test_id("horizon-28").click()
    await run.app.locator('[data-testid="horizon-28"][aria-pressed="true"]').wait_for()
    assert (await run.gb())["toolCalls"][-1]["arguments"]["horizon_days"] == 28
    assert run.problems == []


async def test_card_inline_sem_controles_e_com_expandir(open_host):
    run, _ = await _open(open_host, "ok")

    assert await run.app.get_by_test_id("horizon-7").count() == 0
    assert await run.app.get_by_test_id("table-windows").count() == 0
    assert await run.app.get_by_test_id("action-expand").count() == 1
    await run.app.get_by_test_id("action-expand").click()
    await run.wait_testid("horizon-7")
    assert (await run.gb())["displayModes"] == ["fullscreen"]
    assert run.problems == []


async def test_host_sem_fullscreen_mostra_o_horizonte_no_card(open_host):
    context = host_context("light", availableDisplayModes=["inline"])
    run, _ = await _open(open_host, "ok", context=context)

    assert await run.app.get_by_test_id("action-expand").count() == 0
    assert await run.app.get_by_test_id("horizon-7").count() == 1
    assert run.problems == []


async def test_explicar_pede_ao_chat_e_selecao_avisa_o_modelo(open_host):
    run, fixture = await _open(open_host, "ok")
    top = _sc(fixture)["themes"][0]

    await run.app.get_by_test_id("select-0").click()
    await run.wait_host("gb.ctx.length === 1")
    await run.app.get_by_test_id("action-explain").click()
    await run.wait_host("gb.messages.length === 1")

    gb = await run.gb()
    assert top["label"] in gb["ctx"][0]["content"][0]["text"]
    (message,) = gb["messages"]
    assert message["role"] == "user" and message["content"][0]["type"] == "text"
    assert top["label"] in message["content"][0]["text"]
    assert run.problems == []


async def test_sem_capacidades_do_host_nao_oferece_acoes(open_host):
    run, _ = await _fullscreen(open_host, "ok", capabilities={})

    for testid in ("horizon-7", "action-explain"):
        assert await run.app.get_by_test_id(testid).count() == 0, testid
    assert await run.app.get_by_test_id("radar").count() == 1
    assert run.problems == []


async def test_host_que_recusa_ui_message_esconde_o_botao_sem_erro(open_host):
    run, _ = await _open(open_host, "ok", fail_methods=("ui/message",))

    await run.app.get_by_test_id("action-explain").click()
    await run.app.locator('[data-testid="action-explain"][hidden]').wait_for(state="attached")

    assert await run.eval("() => document.getElementById('app').dataset.state") == "ok"
    assert run.problems == []


async def test_janelas_sem_classificacao_viram_chips(open_host):
    run, fixture = await _open(open_host, "partial")
    windows = _sc(fixture)["windows"]

    for key in ("3d", "7d"):
        assert windows[key]["status"] == "unavailable"
        assert "indisponível" in await run.app.get_by_test_id(f"chip-window-{key}").text_content()
    assert "degradada" in await run.app.get_by_test_id("chip-window-21d").text_content()
    assert await run.app.get_by_test_id("radar").count() == 1
    assert run.problems == []


async def test_indisponivel_e_vazio_sem_radar(open_host):
    run, _ = await _open(open_host, "unavailable")
    assert await run.app.get_by_test_id("state-unavailable").count() == 1
    assert await run.app.get_by_test_id("radar").count() == 0
    assert "fora do ar" in await _app_text(run)

    run2, _ = await _open(open_host, "empty")
    assert await run2.app.get_by_test_id("state-empty").count() == 1
    assert await run2.app.get_by_test_id("radar").count() == 0
    assert run.problems == [] and run2.problems == []


async def test_calendario_no_card(open_host):
    run, fixture = await _open(open_host, "ok")
    assert "faltam" in await run.app.get_by_test_id("chip-calendar").text_content()
    # horizonte de 21 dias a partir de 05/10 cruza o fim do defeso (25/10)
    banner = await run.app.get_by_test_id("banner-calendar").text_content()
    assert "25/10/2026" in banner

    run2, _ = await _open(open_host, "recovery")
    assert "29/11/2026" in await run2.app.get_by_test_id("chip-calendar").text_content()
    assert run.problems == [] and run2.problems == []


async def test_xss_nos_rotulos_vira_texto(open_host):
    run, _ = await _fullscreen(open_host, "xss", width=320)

    text = await _app_text(run)
    assert "<img src=x onerror=alert(1)>" in text
    assert await run.eval("() => document.querySelectorAll('img, script:not([type])').length") == 0
    assert run.dialogs == []
    assert run.problems == []
