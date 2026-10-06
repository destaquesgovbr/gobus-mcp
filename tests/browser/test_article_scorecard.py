"""``ui://article-scorecard`` no mini-host: todas as fixtures × claro/escuro × 320/760 px,
semáforos com ícone e texto, comparação pela mesma tool (``compare_with``), pedido de
reescrita por ``ui/message`` e estados scored/partial/refused."""

import pytest

from gobus_mcp.ui import render_app
from tests.browser.conftest import fixture_names, load_fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="session")]

APP = "article_scorecard"
TOOL = "gobus_score_article"
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


async def test_ha_fixtures_dos_estados_principais():
    assert {"scored", "compare", "partial", "refused", "xss"} <= set(STATES)


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
    assert run.problems == [] and run.dialogs == []
    await run.screenshot(f"{APP}-{state}-{theme}-{width}")


async def test_nota_com_tres_semaforos_de_icone_e_texto(open_host):
    run, fixture = await _open(open_host, "scored")
    sc = _sc(fixture)

    overall = await run.app.get_by_test_id("overall").text_content()
    assert f"{sc['overall']:.1f}".replace(".", ",") in overall
    for dim in sc["dimensions"]:
        item = run.app.get_by_test_id(f"dim-{dim['key']}")
        assert await item.locator(".gb-light").get_attribute("data-light") == dim["light"]
        icon = (await item.locator(".gb-light").text_content()).strip()
        assert icon  # não só cor: ícone…
        assert dim["label"] in await item.text_content()  # …e texto
    text = await _app_text(run)
    assert "Agência Brasil" in text  # benchmark de referência
    assert await run.app.locator('[data-testid="table"] tbody tr').count() == 3
    assert run.problems == []


async def test_comparar_chama_a_mesma_tool_com_compare_with(open_host):
    run, fixture = await _open(open_host, "scored")
    expected = fixture["toolCalls"][0]

    await run.app.get_by_test_id("action-compare").click()
    await run.wait_testid("compare")

    gb = await run.gb()
    assert gb["toolCalls"] == [{"name": TOOL, "arguments": expected["arguments"]}]
    columns = run.app.locator('[data-testid="compare"] [data-testid^="side-"]')
    assert await columns.count() == 2
    other = expected["result"]["structuredContent"]["comparison"]["article"]["title"]
    assert other in await _app_text(run)
    assert gb["ctx"] and "compar" in gb["ctx"][-1]["content"][0]["text"].lower()
    assert run.problems == []


async def test_comparacao_lado_a_lado_empilha_em_320(open_host):
    run, _ = await _open(open_host, "compare", width=320)

    boxes = await run.eval(
        """() => [...document.querySelectorAll('[data-testid^="side-"]')]
                 .map(e => e.getBoundingClientRect().top)"""
    )
    assert len(boxes) == 2 and boxes[1] > boxes[0]  # um embaixo do outro
    run2, _ = await _open(open_host, "compare", width=760)
    tops = await run2.eval(
        """() => [...document.querySelectorAll('[data-testid^="side-"]')]
                 .map(e => e.getBoundingClientRect().top)"""
    )
    assert tops[0] == tops[1]  # lado a lado
    assert run.problems == [] and run2.problems == []


async def test_pedir_reescrita_e_abrir_o_artigo_pelo_host(open_host):
    run, fixture = await _open(open_host, "scored")
    art = _sc(fixture)["article"]

    await run.app.get_by_test_id("article-link").click()
    await run.app.get_by_test_id("action-rewrite").click()
    await run.wait_host("gb.messages.length === 1")

    gb = await run.gb()
    assert gb["links"] == [art["url"]]
    (message,) = gb["messages"]
    assert message["role"] == "user"
    assert art["title"] in message["content"][0]["text"]
    assert art["uniqueId"] in message["content"][0]["text"]
    assert run.problems == []


async def test_parcial_avisa_e_mostra_a_nota_renormalizada(open_host):
    run, fixture = await _open(open_host, "partial")

    assert "parcial" in (await run.app.get_by_test_id("chip-status").text_content()).lower()
    dim = run.app.get_by_test_id("dim-conciseness")
    assert await dim.locator(".gb-light").get_attribute("data-light") == "gray"
    assert "indisponível" in await dim.text_content()
    assert _sc(fixture)["overall"] is not None
    assert run.problems == []


async def test_recusada_nao_inventa_nota(open_host):
    run, fixture = await _open(open_host, "refused")
    sc = _sc(fixture)

    assert "—" in await run.app.get_by_test_id("overall").text_content()
    assert "recusada" in (await run.app.get_by_test_id("chip-status").text_content()).lower()
    assert sc["refusalReason"][:30] in await _app_text(run)
    lights = run.app.locator(".gb-light")
    assert {
        await lights.nth(i).get_attribute("data-light") for i in range(await lights.count())
    } == {"gray"}
    assert await run.app.get_by_test_id("action-rewrite").count() == 0
    assert "5,6" not in await _app_text(run)
    assert run.problems == []


async def test_xss_no_titulo_e_na_agencia_vira_texto(open_host):
    run, _ = await _open(open_host, "xss", width=320)

    text = await _app_text(run)
    assert "<img src=x onerror=alert(1)>" in text
    assert "</script><script>alert(2)</script>" in text
    assert await run.eval("() => document.querySelectorAll('img, script:not([type])').length") == 0
    assert run.dialogs == [] and run.problems == []


async def test_sem_capacidades_do_host_nao_oferece_acoes(open_host):
    run, _ = await _open(open_host, "scored", capabilities={})

    for testid in ("action-compare", "action-rewrite"):
        assert await run.app.get_by_test_id(testid).count() == 0, testid
    assert await run.app.locator('button[data-testid="article-link"]').count() == 0
    assert run.problems == []
