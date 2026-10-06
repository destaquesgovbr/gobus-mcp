"""``ui://anomaly-radar`` no mini-host: todas as fixtures × claro/escuro × 320/760 px e as
interações (fullscreen com a lista, toggle local pico/silêncio/outros, sensibilidade e
domínio por ``tools/call``, "investigar" por ``ui/message``, contexto do modelo)."""

import pytest

from gobus_mcp.ui import render_app
from tests.browser.conftest import fixture_names, host_context, load_fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="session")]

APP = "anomaly_radar"
TOOL = "gobus_detect_anomalies"
STATES = [state for app, state in fixture_names() if app == APP]
DOMAINS = ["HEALTH", "EDUCATION", "SOCIAL", "ECONOMIC", "SECURITY", "ENVIRONMENT", "GOVERNANCE", "OTHER"]  # fmt: skip


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


def _signal(sc: dict, kind: str) -> dict:
    return next(s for s in sc["entities"]["signals"] if s["kind"] == kind)


async def _app_text(run) -> str:
    return await run.eval("() => document.getElementById('app').textContent")


async def test_ha_fixtures_dos_estados_principais():
    expected = {"ok", "partial", "unavailable", "quiet", "empty", "recovery", "xss", "max"}
    assert expected <= set(STATES)


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
@pytest.mark.parametrize("state", ["ok", "max", "xss"])
async def test_fullscreen_renderiza_limpo(open_host, state, width):
    run, _ = await _fullscreen(open_host, state, width=width)

    assert await run.app.get_by_test_id("signals").count() == 1
    assert await run.no_horizontal_overflow()
    gb = await run.gb()
    assert 100 <= gb["sizes"][-1]["height"] <= 2000
    assert run.problems == [] and run.dialogs == []
    await run.screenshot(f"{APP}-{state}-fullscreen-{width}")


async def test_card_inline_8_gauges_em_ordem_fixa_com_faixas_do_payload(open_host):
    run, fixture = await _open(open_host, "ok")
    sc = _sc(fixture)

    gauges = run.app.locator('[data-testid^="gauge-"]')
    assert await gauges.count() == 8
    ids = [await gauges.nth(i).get_attribute("data-testid") for i in range(8)]
    assert ids == [f"gauge-{d}" for d in DOMAINS]
    for summary in sc["domains"]:
        gauge = run.app.get_by_test_id(f"gauge-{summary['domain']}")
        assert await gauge.get_attribute("data-spike-band") == summary["spikeBand"]
        assert await gauge.get_attribute("data-silence-band") == summary["silenceBand"]
        assert summary["label"] in await gauge.text_content()
    # marcas das faixas nos limiares do payload (o JS não fixa 0,33/0,66)
    ticks = run.app.locator('[data-testid="gauge-HEALTH"] [data-tick]')
    values = {await ticks.nth(i).get_attribute("data-tick") for i in range(await ticks.count())}
    bands = sc["severityBands"]
    assert values == {str(bands["watch"]), str(bands["alert"])}
    # card inline: sem a lista (fica no fullscreen), com o total e as ações
    assert await run.app.get_by_test_id("signals").count() == 0
    totals = await run.app.get_by_test_id("totals").text_content()
    assert "pico" in totals and "silêncio" in totals
    assert await run.app.get_by_test_id("action-expand").count() == 1
    assert await run.app.get_by_test_id("table").count() == 1
    assert run.problems == []


async def test_chips_do_defeso_e_dos_temas_vem_do_payload(open_host):
    run, fixture = await _open(open_host, "partial")
    sc = _sc(fixture)

    # dado faltando: nada de "nada fora do padrão"; o porquê aparece no card
    assert await run.app.get_by_test_id("quiet").count() == 0
    assert await run.app.get_by_test_id("no-signals").count() == 1
    assert sc["themes"]["note"] in await _app_text(run)

    calendar = await run.app.get_by_test_id("chip-calendar").text_content()
    assert sc["calendar"]["label"] in calendar
    assert str(sc["calendar"]["daysToEnd"]) in calendar
    themes = await run.app.get_by_test_id("chip-themes").text_content()
    assert "indisponíve" in themes.lower()
    assert "26/09/2026" in themes  # since do aviso THEMES_UNCLASSIFIED
    assert await run.app.get_by_test_id("chip-entities").count() == 1
    assert run.problems == []


async def test_expandir_mostra_a_lista_e_o_toggle_e_local(open_host):
    run, fixture = await _open(open_host, "ok")
    sc = _sc(fixture)

    await run.app.get_by_test_id("action-expand").click()
    await run.app.locator('html[data-mode="fullscreen"]').wait_for(state="attached")
    await run.wait_testid("signals")

    silence = _signal(sc, "coordinated_silence")
    spike = next(t for t in sc["themes"]["signals"] if t["kind"] == "sustained_spike")
    assert await run.app.get_by_test_id(f"signal-theme-{spike['label']}").count() == 1
    assert await run.app.get_by_test_id(f"signal-{silence['entityId']}").count() == 0

    await run.app.get_by_test_id("tab-silences").click()
    await run.wait_testid(f"signal-{silence['entityId']}")
    assert await run.app.get_by_test_id("tab-silences").get_attribute("aria-pressed") == "true"
    assert await run.app.get_by_test_id(f"spark-{silence['entityId']}").count() == 1

    await run.app.get_by_test_id("tab-others").click()
    burst = _signal(sc, "burst")
    await run.wait_testid(f"signal-{burst['entityId']}")
    assert (await run.gb())["toolCalls"] == []  # o toggle não consulta de novo
    assert run.problems == []


async def test_sensibilidade_e_dominio_pela_mesma_tool(open_host):
    run, fixture = await _fullscreen(open_host, "ok")
    calls = {tuple(sorted(c["arguments"].items())): c for c in fixture["toolCalls"]}

    await run.app.get_by_test_id("sens-high").click()
    await run.app.locator('[data-testid="sens-high"][aria-pressed="true"]').wait_for()
    gb = await run.gb()
    assert gb["toolCalls"] == [{"name": TOOL, "arguments": {"sensitivity": "high"}}]
    assert (("sensitivity", "high"),) in calls

    await run.app.get_by_test_id("sens-medium").click()
    await run.app.locator('[data-testid="sens-medium"][aria-pressed="true"]').wait_for()
    await run.app.get_by_test_id("domain-HEALTH").click()
    await run.app.locator('[data-testid="domain-HEALTH"][aria-pressed="true"]').wait_for()
    gb = await run.gb()
    assert gb["toolCalls"][-1] == {
        "name": TOOL,
        "arguments": {"sensitivity": "medium", "domain_filter": "HEALTH"},
    }
    assert "Saúde" in await run.app.get_by_test_id("chip-domain").text_content()
    # os 8 gauges continuam (o payload resume todos os domínios mesmo com filtro)
    assert await run.app.locator('[data-testid^="gauge-"]').count() == 8
    assert run.problems == []


async def test_investigar_pede_ao_chat_e_selecao_avisa_o_modelo(open_host):
    run, fixture = await _fullscreen(open_host, "ok")
    sc = _sc(fixture)
    concentrated = _signal(sc, "concentrated_coverage")

    await run.app.get_by_test_id(f"select-{concentrated['entityId']}").click()
    await run.wait_host("gb.ctx.length === 1")
    await run.app.get_by_test_id(f"investigate-{concentrated['entityId']}").click()
    await run.wait_host("gb.messages.length === 1")

    gb = await run.gb()
    assert concentrated["name"] in gb["ctx"][0]["content"][0]["text"]
    (message,) = gb["messages"]
    assert message["role"] == "user"
    assert isinstance(message["content"], list) and message["content"][0]["type"] == "text"
    text = message["content"][0]["text"]
    assert concentrated["name"] in text and concentrated["entityId"] in text
    assert "gobus_get_entity_profile" in text
    assert run.problems == []


async def test_investigar_no_card_resume_os_principais_sinais(open_host):
    run, fixture = await _open(open_host, "ok")

    await run.app.get_by_test_id("action-investigate").click()
    await run.wait_host("gb.messages.length === 1")

    text = (await run.gb())["messages"][0]["content"][0]["text"]
    assert _signal(_sc(fixture), "coordinated_silence")["name"] in text
    assert run.problems == []


async def test_host_sem_fullscreen_mostra_a_lista_no_card(open_host):
    context = host_context("light", availableDisplayModes=["inline"])
    run, _ = await _open(open_host, "ok", context=context)

    assert await run.app.get_by_test_id("action-expand").count() == 0
    assert await run.app.get_by_test_id("signals").count() == 1
    assert await run.app.get_by_test_id("sens-high").count() == 1
    assert run.problems == []


async def test_sem_capacidades_do_host_nao_oferece_acoes(open_host):
    run, _ = await _fullscreen(open_host, "ok", capabilities={})

    for testid in ("sens-high", "domain-HEALTH", "action-investigate"):
        assert await run.app.get_by_test_id(testid).count() == 0, testid
    assert await run.app.locator('[data-testid^="investigate-"]').count() == 0
    assert await run.app.get_by_test_id("signals").count() == 1  # a lista local continua
    assert run.problems == []


async def test_host_que_recusa_ui_message_esconde_o_botao_sem_erro(open_host):
    run, _ = await _open(open_host, "ok", fail_methods=("ui/message",))

    await run.app.get_by_test_id("action-investigate").click()
    await run.app.locator('[data-testid="action-investigate"][hidden]').wait_for(state="attached")

    assert await run.eval("() => document.getElementById('app').dataset.state") == "ok"
    assert run.problems == []


async def test_indisponivel_mostra_o_motivo_sem_gauges_zerados(open_host):
    run, fixture = await _open(open_host, "unavailable")

    assert await run.app.get_by_test_id("state-unavailable").count() == 1
    assert await run.app.locator('[data-testid^="gauge-"]').count() == 0
    assert "fora do ar" in await _app_text(run)
    assert run.problems == []


async def test_sem_anomalias_diz_que_nada_saiu_do_padrao(open_host):
    run, _ = await _open(open_host, "quiet")

    assert await run.app.get_by_test_id("quiet").count() == 1
    assert await run.app.locator('[data-testid^="gauge-"]').count() == 8
    assert await run.app.get_by_test_id("action-investigate").count() == 0

    run2, _ = await _open(open_host, "empty")
    assert await run2.app.get_by_test_id("state-empty").count() == 1
    assert "Meio ambiente" in await run2.app.get_by_test_id("chip-domain").text_content()
    assert run.problems == [] and run2.problems == []


async def test_recuperacao_mostra_o_banner_do_calendario(open_host):
    run, fixture = await _open(open_host, "recovery")
    sc = _sc(fixture)

    banner = await run.app.get_by_test_id("banner-calendar").text_content()
    assert "29/11/2026" in banner  # recoveryUntil do payload
    assert sc["calendar"]["phase"] == "recovery"
    assert run.problems == []


async def test_payload_compactado_avisa_os_omitidos(open_host):
    run, fixture = await _fullscreen(open_host, "max")
    omitted = sum(_sc(fixture)["entities"]["omitted"].values())

    assert omitted > 0
    assert str(omitted) in await run.app.get_by_test_id("omitted").text_content()
    assert run.problems == []


async def test_xss_nos_nomes_vira_texto(open_host):
    run, _ = await _fullscreen(open_host, "xss", width=320)

    for tab in ("tab-spikes", "tab-silences", "tab-others"):
        await run.app.get_by_test_id(tab).click()
        text = await _app_text(run)
        assert "<img src=x onerror=alert(1)>" in text or "</script>" in text
    assert await run.eval("() => document.querySelectorAll('img, script:not([type])').length") == 0
    assert run.dialogs == []
    assert run.problems == []
