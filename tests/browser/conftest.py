"""Mini-host Playwright para os MCP Apps (marker ``ui``; rodar com ``pytest -m ui``).

O ``minihost.html`` faz o papel do host (Claude, basic-host): carrega o HTML do app num
``<iframe sandbox="allow-scripts" srcdoc>`` com a CSP padrão da spec (SEP-1865) injetada
por ``<meta http-equiv>``, responde ``ui/initialize`` com um ``hostContext`` claro ou escuro
e, só depois de ``ui/notifications/initialized``, envia ``tool-input`` e ``tool-result`` da
fixture (``tests/fixtures/ui/<app>/<estado>.json``).

Cada execução registra erros de console, ``pageerror``, violações de CSP
(``securitypolicyviolation``), ``alert()`` ignorado pelo sandbox e diálogos: um app limpo
termina com ``run.problems == []``.

Usa a API ``async`` do Playwright (a ``sync`` não roda dentro do loop do pytest-asyncio).
Um browser por sessão; uma página por teste. ``GOBUS_UI_ARTIFACTS=<dir>`` grava screenshots.
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")

import pytest_asyncio  # noqa: E402
from playwright.async_api import Browser, Frame, FrameLocator, Page, async_playwright  # noqa: E402

HERE = Path(__file__).parent
MINIHOST_HTML = (HERE / "minihost.html").read_text()
FIXTURES_DIR = HERE.parent / "fixtures" / "ui"

# CSP padrão da spec quando o resource não declara ``_meta.ui.csp``.
SPEC_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "media-src 'self' data:; connect-src 'none'"
)

# Subconjunto das variáveis que o Claude envia em ``hostContext.styles.variables``.
THEMES: dict[str, dict] = {
    "light": {
        "--color-background-primary": "rgb(255, 255, 255)",
        "--color-background-secondary": "rgb(245, 244, 239)",
        "--color-text-primary": "rgb(20, 20, 19)",
        "--color-text-secondary": "rgb(61, 61, 58)",
        "--color-border-primary": "rgba(31, 30, 29, 0.15)",
        "--font-sans": "system-ui, sans-serif",
        "--border-radius-md": "8px",
    },
    "dark": {
        "--color-background-primary": "rgb(38, 38, 36)",
        "--color-background-secondary": "rgb(31, 30, 29)",
        "--color-text-primary": "rgb(250, 249, 245)",
        "--color-text-secondary": "rgb(194, 192, 182)",
        "--color-border-primary": "rgba(255, 255, 255, 0.15)",
        "--font-sans": "system-ui, sans-serif",
        "--border-radius-md": "8px",
    },
}

ALL_CAPABILITIES = {
    "serverTools": {},
    "openLinks": {},
    "message": {"text": {}},
    "updateModelContext": {"text": {}},
}

# Mensagens de console que denunciam problema mesmo sem ser do tipo "error".
_BAD_CONSOLE = ("Refused to", "Content Security Policy", "Ignored call to 'alert()'")

# Repassa as violações de CSP do iframe para o console (o init script roda em todo frame).
_CSP_LISTENER = (
    "document.addEventListener('securitypolicyviolation', e => "
    "console.error('CSP-VIOLATION ' + e.violatedDirective + ' ' + e.blockedURI));"
)


def host_context(theme: str = "light", *, display_mode: str = "inline", **extra) -> dict:
    ctx = {
        "theme": theme,
        "styles": {"variables": dict(THEMES[theme])},
        "displayMode": display_mode,
        "availableDisplayModes": ["inline", "fullscreen"],
        "locale": "pt-BR",
        "timeZone": "America/Sao_Paulo",
        "platform": "web",
    }
    ctx.update(extra)
    return ctx


def load_fixture(app: str, state: str) -> dict:
    return json.loads((FIXTURES_DIR / app / f"{state}.json").read_text())


def fixture_names() -> list[tuple[str, str]]:
    """``(app, estado)`` de toda fixture JSON."""
    return sorted(
        (path.parent.name, path.stem) for path in FIXTURES_DIR.glob("*/*.json") if path.is_file()
    )


@dataclass
class HostRun:
    """Uma página com o mini-host e o app carregado no iframe ``#app``."""

    page: Page
    problems: list[str] = field(default_factory=list)
    dialogs: list[str] = field(default_factory=list)

    @property
    def app(self) -> FrameLocator:
        return self.page.frame_locator("#app")

    def frame(self) -> Frame:
        return next(f for f in self.page.frames if f is not self.page.main_frame)

    async def gb(self) -> dict:
        return await self.page.evaluate("window.__gb")

    async def eval(self, script: str, arg=None):
        return await self.frame().evaluate(script, arg)

    async def wait_testid(self, testid: str, timeout: float = 5_000) -> None:
        await self.app.locator(f'[data-testid="{testid}"]').first.wait_for(timeout=timeout)

    async def wait_host(self, predicate: str, timeout: float = 5_000) -> None:
        """Espera uma condição sobre ``window.__gb`` (expressão JS com ``gb``)."""
        await self.page.wait_for_function(
            f"(() => {{ const gb = window.__gb; return {predicate}; }})()", timeout=timeout
        )

    async def wait_rendered(self, timeout: float = 5_000) -> str:
        """Espera o app sair do skeleton/carregando e devolve o ``data-state`` do root."""
        root = self.app.locator('#app[data-state]:not([data-state="loading"])')
        await root.wait_for(timeout=timeout)
        await self.wait_host("gb.sizes.length > 0", timeout=timeout)
        return await root.get_attribute("data-state")

    async def notify(self, method: str, params: dict | None = None) -> None:
        await self.page.evaluate("([m, p]) => window.__gbNotify(m, p)", [method, params or {}])

    async def request(self, method: str, params: dict | None = None) -> dict:
        """Request host → app; devolve a resposta (``result`` ou ``error``)."""
        rid = await self.page.evaluate("([m, p]) => window.__gbRequest(m, p)", [method, params])
        await self.wait_host(f"gb.responses.some(r => r.id === {rid})")
        gb = await self.gb()
        return next(r for r in gb["responses"] if r["id"] == rid)

    async def no_horizontal_overflow(self) -> bool:
        return await self.eval(
            "() => document.documentElement.scrollWidth <= window.innerWidth + 1"
        )

    async def screenshot(self, name: str) -> None:
        target = os.environ.get("GOBUS_UI_ARTIFACTS")
        if target:
            Path(target).mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=str(Path(target) / f"{name}.png"), full_page=True)


OpenHost = Callable[..., Awaitable[HostRun]]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def browser() -> AsyncIterator[Browser]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        yield browser
        await browser.close()


@pytest_asyncio.fixture(loop_scope="session")
async def open_host(browser: Browser) -> AsyncIterator[OpenHost]:
    pages: list[Page] = []

    async def _open(
        html: str,
        *,
        fixture: dict | None = None,
        theme: str = "light",
        width: int = 760,
        capabilities: dict | None = None,
        context: dict | None = None,
    ) -> HostRun:
        page = await browser.new_page(viewport={"width": width, "height": 900})
        pages.append(page)
        run = HostRun(page)

        def on_console(msg) -> None:
            if msg.type == "error" or any(bad in msg.text for bad in _BAD_CONSOLE):
                run.problems.append(f"console.{msg.type}: {msg.text}")

        async def on_dialog(dialog) -> None:
            run.dialogs.append(dialog.message)
            await dialog.dismiss()

        page.on("console", on_console)
        page.on("pageerror", lambda exc: run.problems.append(f"pageerror: {exc}"))
        page.on("dialog", on_dialog)
        await page.add_init_script(_CSP_LISTENER)
        await page.set_content(MINIHOST_HTML)
        config = {
            "html": html,
            "csp": SPEC_CSP,
            "fixture": copy.deepcopy(fixture),
            "hostCapabilities": ALL_CAPABILITIES if capabilities is None else capabilities,
            "hostContext": context or host_context(theme),
        }
        # como JSON (igual ao fio): o serializador do Playwright manda 0.0 como -0
        await page.evaluate("cfg => window.__gbStart(JSON.parse(cfg))", json.dumps(config))
        return run

    yield _open
    for page in pages:
        await page.close()
