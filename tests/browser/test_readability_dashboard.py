"""``ui://readability-dashboard`` no mini-host: todas as fixtures × claro/escuro × 320/760 px
e as interações (detalhe da agência por ``tools/call``, fullscreen, último período com dado,
links pelo host, ``ui/message``)."""

import pytest

from gobus_mcp.ui import render_app
from tests.browser.conftest import fixture_names, load_fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="session")]

APP = "readability_dashboard"
TOOL = "gobus_get_readability_recommendations"
STATES = [state for app, state in fixture_names() if app == APP]


async def _open(open_host, state: str, **kwargs):
    fixture = load_fixture(APP, state)
    run = await open_host(render_app(APP), fixture=fixture, **kwargs)
    await run.wait_rendered()
    return run, fixture


def _sc(fixture: dict) -> dict:
    return fixture["result"]["structuredContent"]


async def _app_text(run) -> str:
    return await run.eval("() => document.getElementById('app').textContent")


def test_ha_fixtures_dos_estados_principais():
    assert {"ok", "agency_detail", "shifted", "unavailable", "error", "xss"} <= set(STATES)


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


async def test_ranking_inline_top_8_com_metas_e_tabela_completa(open_host):
    run, fixture = await _open(open_host, "ok")
    sc = _sc(fixture)

    bars = run.app.locator('[data-testid^="bar-"]')
    assert await bars.count() == 8
    first = sc["agencies"][0]
    assert await bars.first.get_attribute("data-testid") == f"bar-{first['agencyKey']}"
    rows = run.app.locator('[data-testid="table"] tbody tr')
    assert await rows.count() == len(sc["agencies"]) + len(sc["agenciesWithoutData"])
    text = await _app_text(run)
    assert "52,4" in text  # pt-BR
    assert "Meta" in text and "50" in text
    # sem dado aparece como "—"/"sem dado", nunca 0
    no_data = run.app.locator('[data-testid="no-data-mds"]')
    assert "—" in await no_data.text_content()
    assert run.problems == []


async def test_clique_na_barra_abre_o_detalhe_pela_mesma_tool(open_host):
    run, fixture = await _open(open_host, "ok")
    expected = fixture["toolCalls"][0]

    await run.app.get_by_test_id("bar-saude").click()
    await run.wait_testid("agency-detail")

    gb = await run.gb()
    assert gb["toolCalls"] == [{"name": TOOL, "arguments": expected["arguments"]}]
    assert "Ministério da Saúde" in gb["ctx"][-1]["content"][0]["text"]
    assert "Ministério da Saúde" in await _app_text(run)

    await run.app.get_by_test_id("action-back").click()
    await run.wait_testid("bar-saude")
    assert len((await run.gb())["toolCalls"]) == 1  # voltar não consulta de novo
    assert run.problems == []


async def test_expandir_pede_fullscreen_e_mostra_o_ranking_inteiro(open_host):
    run, fixture = await _open(open_host, "ok")

    await run.app.get_by_test_id("action-expand").click()
    await run.app.locator('html[data-mode="fullscreen"]').wait_for(state="attached")

    gb = await run.gb()
    assert gb["displayModes"] == ["fullscreen"]
    bars = run.app.locator('[data-testid^="bar-"]')
    await run.app.locator('[data-testid="bar-mcti"]').wait_for()
    assert await bars.count() == len(_sc(fixture)["agencies"])
    assert await run.app.get_by_test_id("action-expand").count() == 0
    assert run.problems == []


async def test_janela_deslocada_oferece_o_ultimo_periodo_com_dado(open_host):
    run, fixture = await _open(open_host, "shifted")

    assert "06/2026" in await run.app.get_by_test_id("chip-window").text_content()
    await run.app.get_by_test_id("action-last-period").click()
    await run.app.locator('#app[data-state="ok"]').wait_for()

    gb = await run.gb()
    assert gb["toolCalls"][-1] == {"name": TOOL, "arguments": fixture["toolCalls"][0]["arguments"]}
    assert gb["toolCalls"][-1]["arguments"]["date_to"] == "2026-06-30"
    assert run.problems == []


async def test_indisponivel_mostra_traco_e_aviso_nunca_zero(open_host):
    run, _ = await _open(open_host, "unavailable")

    assert await run.app.locator('[data-testid^="bar-"]').count() == 0
    text = await _app_text(run)
    assert "indisponível" in text.lower()
    assert "0,0" not in text
    assert await run.app.get_by_test_id("notices").count() == 1
    assert run.problems == []


async def test_erro_de_parametro_mostra_a_mensagem_da_tool(open_host):
    run, fixture = await _open(open_host, "error")

    assert _sc(fixture)["error"] in await _app_text(run)
    assert await run.app.get_by_test_id("state-param-error").count() == 1


async def test_xss_nos_nomes_vira_texto(open_host):
    run, _ = await _open(open_host, "xss", width=320)

    text = await _app_text(run)
    assert "<img src=x onerror=alert(1)>" in text
    assert "</script><script>alert(2)</script>" in text
    assert await run.eval("() => document.querySelectorAll('img, script:not([type])').length") == 0
    assert run.dialogs == []
    assert run.problems == []  # inclui "Ignored call to 'alert()'" do sandbox


async def test_detalhe_da_agencia_com_artigos_benchmark_e_pedido_ao_chat(open_host):
    run, fixture = await _open(open_host, "agency_detail")
    sc = _sc(fixture)

    text = await _app_text(run)
    assert "Ministério da Saúde" in text and "Agência Brasil" in text
    assert "−8,3" in text or "-8,3" in text  # bruto do pior artigo, com clamp
    assert await run.app.locator('[data-testid="recommendations"] li').count() == 3
    assert "**" not in text  # negrito do Markdown vira <strong>

    await run.app.get_by_test_id("article-worst").click()
    await run.app.get_by_test_id("action-ask").click()
    await run.wait_host("gb.messages.length === 1")

    gb = await run.gb()
    assert gb["links"] == [sc["worstArticle"]["url"]]
    (message,) = gb["messages"]
    assert message["role"] == "user"
    assert "Ministério da Saúde" in message["content"][0]["text"]
    assert run.problems == []


async def test_sem_capacidades_do_host_nao_oferece_acoes(open_host):
    run, _ = await _open(open_host, "agency_detail", capabilities={})

    assert await run.app.get_by_test_id("action-ask").count() == 0
    assert await run.app.locator('button[data-testid="article-worst"]').count() == 0

    run2, _ = await _open(open_host, "ok", capabilities={})
    await run2.app.get_by_test_id("bar-saude").click()
    await run2.page.wait_for_timeout(100)
    assert (await run2.gb())["toolCalls"] == []
    assert run.problems == [] and run2.problems == []
