"""Tools de preview dev dos MCP Apps (``gobus_dev_preview_<app>``). DEV — dados fictícios.

Para validar o render nos hosts reais (Claude Desktop, claude.ai via túnel, basic-host)
enquanto os dados de produção não voltam. Cada tool devolve uma fixture de
``tests/fixtures/ui/<app>/<estado>.json`` pelo mesmo resource ``ui://`` da tool de
verdade, com o aviso "DEV — dados fictícios" no começo do texto e do ``summary`` (o modelo
não pode tratar a fixture como dado real).

- Só são registradas com ``GOBUS_DEV_PREVIEW=1`` (nunca no Cloud Run; o Terraform não
  define a variável). As fixtures vêm do clone (``GOBUS_DEV_FIXTURES`` troca o diretório).
- As interações dentro do app (``tools/call``) chamam a tool **real** (o nome é fixo no
  JS): no preview, só o render inicial é fictício.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastmcp.tools import ToolResult

from gobus_mcp.analytics.render import fit_summary
from gobus_mcp.ui import APPS, app_tool_kwargs

logger = logging.getLogger(__name__)

DEV_NOTE = "DEV — dados fictícios"
PREVIEW_PREFIX = "gobus_dev_preview_"
# src/gobus_mcp/ui/preview.py → raiz do clone → tests/fixtures/ui
DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ui"


def fixtures_dir(configured: str = "") -> Path:
    """Diretório das fixtures: ``GOBUS_DEV_FIXTURES`` ou o ``tests/fixtures/ui`` do clone."""
    return Path(configured) if configured.strip() else DEFAULT_FIXTURES


def preview_states(directory: Path, app: str) -> list[str]:
    """Estados com fixture de ``app`` (nomes dos JSON), ``ok`` primeiro."""
    states = sorted(p.stem for p in (directory / app).glob("*.json"))
    return sorted(states, key=lambda s: s != "ok")


def _banner(app: str, state: str) -> str:
    return f"**{DEV_NOTE}** — preview de `{APPS[app].uri}` (fixture `{app}/{state}`)."


def preview_result(directory: Path, app: str, state: str) -> ToolResult:
    """A fixture como resultado de tool, com o aviso no texto e no ``summary``."""
    states = preview_states(directory, app)
    if state not in states:
        return ToolResult(
            content=f"{_banner(app, state)}\n\nEstado inexistente. Opções: {', '.join(states)}."
        )
    fixture = json.loads((directory / app / f"{state}.json").read_text(encoding="utf-8"))
    result = fixture["result"]
    text = "\n\n".join(c["text"] for c in result.get("content", []) if c.get("type") == "text")
    banner = _banner(app, state)
    structured = result.get("structuredContent")
    if structured is not None:
        rest = {k: v for k, v in structured.items() if k != "summary"}
        summary = fit_summary(f"{banner}\n\n{structured.get('summary', '')}")
        structured = {"summary": summary, **rest}
    return ToolResult(content=f"{banner}\n\n{text}", structured_content=structured)


def register_dev_previews(mcp, directory: Path) -> list[str]:
    """Registra ``gobus_dev_preview_<app>(state="ok")`` para cada app com fixtures em
    ``directory``. Devolve os nomes registrados (nenhum se o diretório não existe)."""
    if not directory.is_dir():
        logger.warning("preview dev: diretório de fixtures inexistente (%s)", directory)
        return []
    names = []
    for app, spec in APPS.items():
        states = preview_states(directory, app)
        if not states:
            continue
        name = f"{PREVIEW_PREFIX}{app}"
        description = (
            f"{DEV_NOTE}. Preview do MCP App {spec.uri} (o mesmo de {spec.tool}) com uma "
            f"fixture de teste, para validar o render no host. Estados: {', '.join(states)}. "
            "Não use para análise: os números são fictícios. As interações dentro do app "
            f"chamam a tool real ({spec.tool})."
        )
        mcp.tool(name=name, description=description, **app_tool_kwargs(app))(
            _preview_fn(directory, app)
        )
        names.append(name)
    logger.warning("preview dev ligado (%s): %s", directory, ", ".join(names))
    return names


def _preview_fn(directory: Path, app: str):
    async def preview(state: str = "ok") -> ToolResult:
        return preview_result(directory, app, state)

    preview.__name__ = f"{PREVIEW_PREFIX}{app}"
    return preview
