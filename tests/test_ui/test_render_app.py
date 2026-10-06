"""Infra dos MCP Apps (``gobus_mcp.ui``): HTML único, guards e empacotamento dos assets.

O HTML de um app é estático (sem dado e sem I/O): ``_base.html`` + ``_tokens.css`` + o CSS
do app num ``<style>`` e ``_bridge.js`` + ``_dom.js`` + ``_svg.js`` + o JS do app num único
``<script type="module">``. Os guards recusam o que a CSP padrão da spec bloquearia (URL
externa) e o que abriria XSS (``innerHTML``, ``eval``…).
"""

import tomllib
from importlib.resources import files
from pathlib import Path

import pytest

import gobus_mcp
from gobus_mcp.ui import APPS, MAX_HTML_BYTES, AppAssetError, assemble_app, render_app

COMMON_ASSETS = ["_base.html", "_tokens.css", "_bridge.js", "_dom.js", "_svg.js"]
PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def _app(js: str = "bridgeStart({});", css: str = "", **kwargs) -> str:
    return assemble_app(name="teste", title="Teste", css=css, js=js, **kwargs)


# ── empacotamento ───────────────────────────────────────────────────────────


def test_assets_comuns_empacotados_no_pacote():
    # importlib.resources: vale para o install editável, o wheel e o PYTHONPATH do Docker
    root = files("gobus_mcp.ui") / "assets"
    for name in COMMON_ASSETS:
        assert (root / name).is_file(), name


def test_versao_do_pacote_igual_a_do_pyproject():
    # a imagem instala só as dependências (--no-root): a versão não vem do importlib.metadata
    version = tomllib.loads(PYPROJECT.read_text())["tool"]["poetry"]["version"]
    assert gobus_mcp.__version__ == version


# ── montagem ────────────────────────────────────────────────────────────────


def test_html_unico_com_doctype_um_style_e_um_module_script():
    html = _app(js="bridgeStart({}); /* APP-MARK */", css=".x{color:red}")

    assert html.lower().startswith("<!doctype html>")
    assert html.count("<script") == 1
    assert '<script type="module">' in html
    assert html.count("<style>") == 1
    assert '<meta name="color-scheme" content="light dark">' in html
    assert 'name="viewport"' in html
    assert ".x{color:red}" in html
    for placeholder in ("__APP_", "/*__CSS__*/", "/*__JS__*/"):
        assert placeholder not in html


def test_ordem_dos_scripts_bridge_dom_svg_e_app():
    html = _app(js="bridgeStart({}); /* APP-MARK */")

    positions = [
        html.index("ui/initialize"),  # _bridge.js
        html.index("function h("),  # _dom.js
        html.index("SVG_NS"),  # _svg.js
        html.index("APP-MARK"),  # JS do app
    ]
    assert positions == sorted(positions)


def test_tokens_antes_do_css_do_app():
    html = _app(css=".app-mark{}")

    assert html.index("--gb-bg") < html.index(".app-mark")


def test_initialize_com_protocolo_nome_e_versao_do_app():
    html = _app()

    assert "2026-01-26" in html
    assert '"gobus-teste"' in html
    assert f'"{gobus_mcp.__version__}"' in html
    assert "appInfo" in html
    assert "ui/notifications/size-changed" in html


def test_titulo_escapado():
    html = assemble_app(name="teste", title='<b>"x"</b>', css="", js="bridgeStart({});")

    assert "<title>&lt;b&gt;&quot;x&quot;&lt;/b&gt;</title>" in html


def test_nucleo_comum_passa_nos_guards_e_cabe_no_orcamento():
    html = _app()

    # núcleo comum compactado (bridge + dom + svg + tokens): ~24 KB; cada app soma o seu
    # JS/CSS e o teto por app é 60 KB (meta 25 KB)
    assert len(html.encode()) <= 26 * 1024


# ── guards ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("closing", ["</script>", "</SCRIPT >", "</style>"])
@pytest.mark.parametrize("where", ["js", "css"])
def test_recusa_fechamento_de_script_ou_style_nos_assets(closing, where):
    kwargs = {"js": f"bridgeStart({{}}); // {closing}"} if where == "js" else {"css": closing}

    with pytest.raises(AppAssetError, match="</"):
        _app(**kwargs)


@pytest.mark.parametrize(
    "snippet",
    [
        'el.src = "https://cdn.example.com/x.js";',
        "const a = 'src=//cdn.example.com/a.js';",
        "/* url(https://fonts.example.com/f.woff2) */",
        "/* @import 'https://cdn.example.com/a.css'; */",
        'const m = import("https://esm.sh/d3");',
        'import x from "https://esm.sh/d3";',
        "const a = 'href=\"http://example.com\"';",
    ],
)
def test_recusa_url_externa_em_src_href_url_e_import(snippet):
    with pytest.raises(AppAssetError, match="externa"):
        _app(js=f"bridgeStart({{}});\n{snippet}")


def test_recusa_url_externa_no_css():
    with pytest.raises(AppAssetError, match="externa"):
        _app(css="@font-face{src:url(https://fonts.example.com/f.woff2)}")


def test_namespace_svg_e_texto_com_https_sao_permitidos():
    js = (
        'const n = document.createElementNS("http://www.w3.org/2000/svg", "svg");\n'
        'const t = "veja https://www.gov.br no texto";\n'
        "bridgeStart({});"
    )

    assert "http://www.w3.org/2000/svg" in _app(js=js)


@pytest.mark.parametrize(
    "snippet",
    [
        "el.innerHTML = x;",
        "el.outerHTML = x;",
        'el.insertAdjacentHTML("beforeend", x);',
        "document.write(x);",
        "eval(x);",
        'new Function("return 1");',
        'window.localStorage.getItem("k");',
        'sessionStorage.setItem("k", "v");',
    ],
)
def test_recusa_apis_que_abrem_xss_ou_quebram_no_sandbox(snippet):
    with pytest.raises(AppAssetError, match="proibid"):
        _app(js=f"bridgeStart({{}});\n{snippet}")


def test_recusa_html_acima_do_teto():
    with pytest.raises(AppAssetError, match="KB"):
        _app(js="bridgeStart({});\nconst pad = '" + "x" * MAX_HTML_BYTES + "';")


def test_compacta_js_e_css_sem_mudar_o_codigo():
    js = "// comentário de linha\n    const a = 1;  // fim de linha fica\n\n\tbridgeStart({});"
    html = _app(js=js, css="/* sai */\n.a  >  .b {\n  color:  red;\n}")

    assert "comentário de linha" not in html
    assert "const a = 1;  // fim de linha fica\nbridgeStart({});" in html
    assert ".a>.b{color:red;}" in html


def test_recusa_template_literal_no_js():
    with pytest.raises(AppAssetError, match="template"):
        _app(js="const t = `x`; bridgeStart({});")


def test_teto_de_60_kb():
    assert MAX_HTML_BYTES == 60 * 1024


def test_render_app_de_app_desconhecido():
    with pytest.raises(KeyError):
        render_app("nao_existe")


# ── apps registrados ────────────────────────────────────────────────────────

# app → (URI estável, tool, kind do payload)
EXPECTED_APPS = {
    "readability_dashboard": (
        "ui://readability-dashboard",
        "gobus_get_readability_recommendations",
        "gobus.readability",
    ),
    "article_scorecard": ("ui://article-scorecard", "gobus_score_article", "gobus.scorecard"),
    "anomaly_radar": ("ui://anomaly-radar", "gobus_detect_anomalies", "gobus.anomalies"),
}


@pytest.mark.parametrize("name", list(EXPECTED_APPS))
def test_app_registrado_com_uri_tool_e_kind(name):
    spec = APPS[name]
    assert (spec.uri, spec.tool, spec.kind) == EXPECTED_APPS[name]


@pytest.mark.parametrize("name", list(EXPECTED_APPS))
def test_app_renderiza_dentro_do_orcamento_com_o_proprio_kind(name):
    html = render_app(name)

    assert len(html.encode()) <= MAX_HTML_BYTES
    assert f'"gobus-{name.replace("_", "-")}"' in html  # appInfo.name
    assert f'kind: "{EXPECTED_APPS[name][2]}"' in html  # o app recusa outro kind


def test_rotulos_das_flags_do_markdown_tambem_no_radar():
    from gobus_mcp.analytics.render import FLAG_PT

    js = (files("gobus_mcp.ui") / "assets" / "anomaly_radar.js").read_text()
    for label in FLAG_PT.values():
        assert label in js, label
