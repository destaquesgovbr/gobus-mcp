"""Tools de preview dev dos MCP Apps (``gobus_dev_preview_<app>``).

Servem para validar o render nos hosts reais (Desktop, claude.ai, basic-host) enquanto
os dados de produção não voltam: devolvem as fixtures de ``tests/fixtures/ui`` (marcadas
"DEV — dados fictícios") pelo mesmo resource ``ui://`` da tool de verdade.

- só existem com ``GOBUS_DEV_PREVIEW=1`` (nunca no Cloud Run): por padrão não aparecem;
- o texto e o ``summary`` começam com o aviso, para o modelo não tratar a fixture como dado.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from fastmcp import Client, FastMCP

from gobus_mcp import server
from gobus_mcp.config import Settings
from gobus_mcp.ui import APPS
from gobus_mcp.ui.preview import (
    DEV_NOTE,
    PREVIEW_PREFIX,
    fixtures_dir,
    preview_states,
    register_dev_previews,
)
from tests.fixtures.ui.build import FIXTURES_DIR

ROOT = Path(__file__).parents[2]
EXPECTED = {f"{PREVIEW_PREFIX}{name}": spec.uri for name, spec in APPS.items()}

_LIST_TOOLS = """
import asyncio, json
from fastmcp import Client
from gobus_mcp import server

async def main():
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
    print(json.dumps([
        {"name": t.name, "meta": t.meta, "description": t.description} for t in tools
    ]))

asyncio.run(main())
"""


def _tools_in_subprocess(**env) -> list[dict]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GOBUS_")}
    clean.update(PYTHONPATH=str(ROOT / "src"), GOBUS_LOG_LEVEL="WARNING", **env)
    out = subprocess.run(
        [sys.executable, "-c", _LIST_TOOLS],
        cwd=ROOT,
        env=clean,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


# ── registro ────────────────────────────────────────────────────────────────


def test_settings_sem_preview_por_padrao(monkeypatch):
    monkeypatch.delenv("GOBUS_DEV_PREVIEW", raising=False)
    assert Settings(_env_file=None).dev_preview is False


async def test_previews_nao_aparecem_no_servidor_padrao():
    async with Client(server.mcp) as client:
        names = {t.name for t in await client.list_tools()}

    assert not {n for n in names if n.startswith(PREVIEW_PREFIX)}


def test_processo_sem_a_variavel_nao_registra_previews():
    names = {t["name"] for t in _tools_in_subprocess()}

    assert len(names) == 13
    assert not {n for n in names if n.startswith(PREVIEW_PREFIX)}


def test_processo_com_gobus_dev_preview_1_registra_uma_por_app():
    tools = {t["name"]: t for t in _tools_in_subprocess(GOBUS_DEV_PREVIEW="1")}

    previews = {name: tool for name, tool in tools.items() if name.startswith(PREVIEW_PREFIX)}
    assert {name: tool["meta"]["ui"]["resourceUri"] for name, tool in previews.items()} == EXPECTED
    for tool in previews.values():
        assert tool["description"].startswith(DEV_NOTE)
    assert len(tools) == 13 + len(APPS)


def test_diretorio_padrao_das_fixtures_e_o_do_repositorio(monkeypatch):
    assert fixtures_dir("") == FIXTURES_DIR
    assert fixtures_dir("/tmp/outro") == Path("/tmp/outro")


def test_diretorio_inexistente_nao_registra_nada(tmp_path):
    mcp = FastMCP("teste")

    assert register_dev_previews(mcp, tmp_path / "nao-existe") == []


# ── chamada ─────────────────────────────────────────────────────────────────


def _preview_server() -> FastMCP:
    mcp = FastMCP("teste")
    assert sorted(register_dev_previews(mcp, FIXTURES_DIR)) == sorted(EXPECTED)
    return mcp


async def test_preview_devolve_a_fixture_marcada_como_ficticia():
    fixture = json.loads((FIXTURES_DIR / "anomaly_radar" / "ok.json").read_text())

    async with Client(_preview_server()) as client:
        tools = {t.name: t for t in await client.list_tools()}
        result = await client.call_tool_mcp(f"{PREVIEW_PREFIX}anomaly_radar", {})

    tool = tools[f"{PREVIEW_PREFIX}anomaly_radar"]
    assert tool.meta["ui"]["resourceUri"] == tool.meta["ui/resourceUri"] == "ui://anomaly-radar"
    assert tool.outputSchema is None and tool.annotations.readOnlyHint is True
    assert set(tool.inputSchema["properties"]) == {"state"}
    assert result.isError is False
    text = result.content[0].text
    sc = result.structuredContent
    assert text.startswith(f"**{DEV_NOTE}**")
    assert sc["summary"].startswith(f"**{DEV_NOTE}**")
    assert next(iter(sc)) == "summary"
    assert len(sc["summary"].encode()) <= 6 * 1024
    expected = dict(fixture["result"]["structuredContent"])
    assert {k: v for k, v in sc.items() if k != "summary"} == {
        k: v for k, v in expected.items() if k != "summary"
    }


async def test_preview_aceita_cada_estado_das_fixtures():
    states = preview_states(FIXTURES_DIR, "forecast_radar")
    assert {"ok", "unavailable"} <= set(states)

    async with Client(_preview_server()) as client:
        for state in states:
            result = await client.call_tool_mcp(f"{PREVIEW_PREFIX}forecast_radar", {"state": state})
            assert result.structuredContent["kind"] == "gobus.forecast", state


async def test_preview_com_estado_inexistente_lista_as_opcoes():
    async with Client(_preview_server()) as client:
        result = await client.call_tool_mcp(
            f"{PREVIEW_PREFIX}article_scorecard", {"state": "nao-existe"}
        )

    assert result.structuredContent is None
    text = result.content[0].text
    assert DEV_NOTE in text and "scored" in text and "refused" in text


async def test_preview_sem_estado_usa_o_principal_de_cada_app():
    # o basic-host chama com os defaults da tool: o scorecard não tem fixture "ok"
    async with Client(_preview_server()) as client:
        tools = {t.name: t for t in await client.list_tools()}
        for name in EXPECTED:
            result = await client.call_tool_mcp(name, {})
            assert result.structuredContent is not None, name
            default = tools[name].inputSchema["properties"]["state"].get("default")
            assert default in ("", None), name

    assert preview_states(FIXTURES_DIR, "article_scorecard")[0] == "scored"
