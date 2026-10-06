"""MCP Apps do gobus (SEP-1865, protocolo ``2026-01-26``): HTML estático e binding das tools.

Cada app é um único documento HTML, montado a partir de ``assets/``:

- ``_base.html`` com um ``<style>`` (``_tokens.css`` + ``<app>.css``) e um único
  ``<script type="module">`` (``_bridge.js`` + ``_dom.js`` + ``_svg.js`` + ``<app>.js``,
  concatenados, sem ``import``; os nomes de topo usam o prefixo do arquivo);
- **nenhum dado no HTML e nenhum I/O** no ``resources/read``: os dados chegam pelo
  ``structuredContent`` do ``tool-result`` (o host pode fazer cache do resource);
- sem SDK ext-apps e sem biblioteca de gráficos: bridge JSON-RPC raw e SVG à mão.

Os guards de ``assemble_app`` recusam o que a CSP padrão da spec bloquearia (URL externa
em ``src=``/``href=``/``url(``/``import``; o namespace SVG fica liberado) e o que abriria
XSS ou quebraria no sandbox sem same-origin (``innerHTML``, ``eval``, ``localStorage``…).
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult

from gobus_mcp import __version__
from gobus_mcp.analytics.render import SUMMARY_MAX_BYTES, fit_summary
from gobus_mcp.payloads.common import MAX_PAYLOAD_BYTES, ReportBase

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 60 * 1024  # teto por app (meta: 25 KB)
COMMON_CSS = ("_tokens.css",)
COMMON_JS = ("_bridge.js", "_dom.js", "_svg.js")

_CLOSING_TAG_RE = re.compile(r"</\s*(script|style)", re.IGNORECASE)
# URL absoluta (http, https ou protocolo-relativa) logo depois de src=, href=, url(,
# @import ou import (estático ou dinâmico). Texto solto com https:// fica liberado
# (ex.: o namespace SVG em createElementNS).
_EXTERNAL_RE = re.compile(
    r"""(?:\bsrc\s*=|\bhref\s*=|\burl\s*\(|@import|\bimport\s*\(|\bimport\b[^;\n]*?\bfrom)"""
    r"""\s*\\?["']?\s*(?:https?:)?//""",
    re.IGNORECASE,
)
_FORBIDDEN_RE = re.compile(
    r"\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write|localStorage|sessionStorage)\b"
    r"|\beval\s*\(|\bnew\s+Function\s*\("
)


class AppAssetError(ValueError):
    """Asset ou HTML de app fora das regras (CSP, XSS, orçamento)."""


@dataclass(frozen=True)
class AppSpec:
    """Um MCP App: resource ``ui://`` estável, a tool que o abre e o ``kind`` do payload."""

    name: str  # base dos assets: assets/<name>.js e assets/<name>.css
    uri: str
    title: str
    description: str
    tool: str
    kind: str


# URIs estáveis: a versão do contrato fica em ``schemaVersion`` do payload; a URI só muda
# (``…-v2``) numa quebra de compatibilidade.
APPS: dict[str, AppSpec] = {
    spec.name: spec
    for spec in (
        AppSpec(
            name="readability_dashboard",
            uri="ui://readability-dashboard",
            title="Legibilidade por agência",
            description=(
                "MCP App de gobus_get_readability_recommendations: ranking do Flesch por "
                "agência com as metas e diagnóstico da agência. Template estático: os dados "
                "chegam pelo structuredContent da tool (lido direto, é uma casca vazia)."
            ),
            tool="gobus_get_readability_recommendations",
            kind="gobus.readability",
        ),
        AppSpec(
            name="article_scorecard",
            uri="ui://article-scorecard",
            title="Score editorial",
            description=(
                "MCP App de gobus_score_article: nota 0–10 com semáforos por dimensão, "
                "benchmark da agência e da Agência Brasil e comparação lado a lado "
                "(compare_with). Template estático: os dados chegam pelo structuredContent."
            ),
            tool="gobus_score_article",
            kind="gobus.scorecard",
        ),
        AppSpec(
            name="anomaly_radar",
            uri="ui://anomaly-radar",
            title="Radar de anomalias",
            description=(
                "MCP App de gobus_detect_anomalies: 8 gauges por domínio (picos e silêncios), "
                "chips do defeso e dos temas e, no fullscreen, a lista de sinais com "
                "sensibilidade e domínio. Template estático: os dados chegam pelo "
                "structuredContent da tool."
            ),
            tool="gobus_detect_anomalies",
            kind="gobus.anomalies",
        ),
        AppSpec(
            name="forecast_radar",
            uri="ui://forecast-radar",
            title="Radar de tendências",
            description=(
                "MCP App de gobus_forecast_trends: radar do ritmo semanal dos temas em escala "
                "log2 com o anel 1× (baseline), top-3 com momentum e artigos esperados e, no "
                "fullscreen, o horizonte 7/14/21/28 e as razões por janela. Template "
                "estático: os dados chegam pelo structuredContent da tool."
            ),
            tool="gobus_forecast_trends",
            kind="gobus.forecast",
        ),
    )
}


def read_asset(filename: str) -> str:
    """Conteúdo de ``assets/<filename>`` (``importlib.resources``: editável, wheel ou
    ``PYTHONPATH`` da imagem)."""
    return (files("gobus_mcp.ui") / "assets" / filename).read_text(encoding="utf-8")


def _check_asset(filename: str, text: str) -> None:
    if _CLOSING_TAG_RE.search(text):
        raise AppAssetError(f"{filename}: contém </script ou </style (fecharia o bloco inline)")
    if filename.endswith(".js") and "`" in text:
        raise AppAssetError(f"{filename}: template literal (a compactação mexe em linhas)")


def _compact_js(text: str) -> str:
    """Tira indentação, linhas vazias e linhas só de comentário ``//`` (seguro sem
    template literal, que ``_check_asset`` recusa)."""
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line and not line.startswith("//"))


def _compact_css(text: str) -> str:
    """Tira comentários e espaços redundantes (nunca antes de ``:``, que separa seletor)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\s*([{};,>])\s*|:\s+", lambda m: m.group(1) or ":", text).strip()


def _check_html(name: str, document: str) -> None:
    external = _EXTERNAL_RE.search(document)
    if external:
        raise AppAssetError(
            f"app {name!r}: referência externa {external.group(0)!r} "
            "(a CSP padrão da spec bloqueia; use só recursos inline)"
        )
    forbidden = _FORBIDDEN_RE.search(document)
    if forbidden:
        raise AppAssetError(
            f"app {name!r}: API proibida {forbidden.group(0)!r} "
            "(DOM só com createElement/textContent; sem storage no sandbox)"
        )
    size = len(document.encode("utf-8"))
    if size > MAX_HTML_BYTES:
        raise AppAssetError(
            f"app {name!r}: HTML com {size / 1024:.1f} KB (teto {MAX_HTML_BYTES // 1024} KB)"
        )


def assemble_app(*, name: str, title: str, css: str, js: str, version: str = __version__) -> str:
    """Monta o HTML único de um app a partir do núcleo comum e do CSS/JS do app (puro).

    ``name`` vira ``appInfo.name = "gobus-<name>"`` (com ``-`` no lugar de ``_``).
    Levanta ``AppAssetError`` se algum asset ou o HTML final quebrar as regras.
    """
    parts_css = [(f, read_asset(f)) for f in COMMON_CSS] + [(f"{name}.css", css)]
    parts_js = [(f, read_asset(f)) for f in COMMON_JS] + [(f"{name}.js", js)]
    for filename, text in parts_css + parts_js:
        _check_asset(filename, text)

    app_name = "gobus-" + name.replace("_", "-")
    script = "\n".join(_compact_js(text) for _, text in parts_js)
    script = script.replace("__APP_NAME__", json.dumps(app_name)).replace(
        "__APP_VERSION__", json.dumps(version)
    )
    style = "\n".join(_compact_css(text) for _, text in parts_css)
    document = (
        read_asset("_base.html")
        .replace("__APP_TITLE__", html_lib.escape(title))
        .replace("/*__CSS__*/", style)
        .replace("/*__JS__*/", script)
    )
    _check_html(name, document)
    return document


@lru_cache(maxsize=None)
def render_app(name: str) -> str:
    """HTML do app ``name`` (estático, cacheado no processo). ``KeyError`` se não existe."""
    spec = APPS[name]
    return assemble_app(
        name=spec.name,
        title=spec.title,
        css=read_asset(f"{spec.name}.css"),
        js=read_asset(f"{spec.name}.js"),
    )


def app_tool_kwargs(name: str) -> dict:
    """Kwargs de ``@mcp.tool`` de uma tool de app.

    ``meta["ui/resourceUri"]`` é a chave legada (deprecada na spec, mas o ``registerAppTool``
    oficial ainda grava as duas); ``-> ToolResult`` na tool suprime o ``outputSchema``.
    """
    uri = APPS[name].uri
    return {
        "app": AppConfig(resource_uri=uri),
        "meta": {"ui/resourceUri": uri},
        "annotations": {"readOnlyHint": True},
    }


def register_ui_resources(mcp) -> None:
    """Registra um resource ``ui://`` por app (MIME ``text/html;profile=mcp-app``)."""
    for spec in APPS.values():
        mcp.resource(
            spec.uri,
            name=spec.name,
            title=spec.title,
            description=spec.description,
            app=AppConfig(prefers_border=True),
        )(_resource_fn(spec))


def _resource_fn(spec: AppSpec):
    def resource() -> str:
        return render_app(spec.name)

    resource.__name__ = f"{spec.name}_resource"
    resource.__doc__ = spec.description
    return resource


def app_result(report: ReportBase, *, content: str | None = None) -> ToolResult:
    """Resultado de uma tool de app.

    - ``content``: o Markdown completo (``content``; sem ele, ``report.summary``), para o
      modelo e para hosts sem UI;
    - ``structuredContent``: o payload em camelCase com ``summary`` como **primeiro** campo
      (o mesmo Markdown até 6 KB; o Claude Code mostra o ``structuredContent``, então o
      modelo lê o resumo antes dos dados).
    """
    markdown = report.summary if content is None else content
    summary = fit_summary(report.summary, SUMMARY_MAX_BYTES)
    data = report.model_copy(update={"summary": summary}).model_dump(mode="json", by_alias=True)
    data = {"summary": data.pop("summary"), **data}
    size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        logger.warning(
            "payload de %s com %d bytes (orçamento %d)", report.tool, size, MAX_PAYLOAD_BYTES
        )
    return ToolResult(content=markdown, structured_content=data)
