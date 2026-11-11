"""Rotas do servidor HTTP (Cloud Run): só o ``/mcp`` stateless.

O ``/sse`` legado (spec 2024-11-05) segurava um ``GET`` aberto por até o ``timeout`` do
Cloud Run (3.600 s), e a instância faturava o tempo todo. O ``/mcp`` stateless responde
cada ``POST`` e fecha; o ``GET`` dá 405, então nenhum cliente consegue abrir um stream
longo.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from gobus_mcp import server

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "teste", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


@asynccontextmanager
async def _http() -> AsyncIterator[httpx.AsyncClient]:
    # Context manager, não fixture: o lifespan (task group do session manager) precisa
    # entrar e sair na mesma task.
    app = server.mcp.http_app(stateless_http=True)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def test_so_o_mcp_e_rota_http():
    app = server.mcp.http_app(stateless_http=True)
    paths = [getattr(route, "path", None) for route in app.routes]

    assert "/mcp" in paths
    assert "/sse" not in paths
    assert "/messages" not in paths


async def test_get_em_sse_da_404():
    async with _http() as http:
        # timeout: se a rota legada voltar, o GET abre o stream e nunca termina
        response = await asyncio.wait_for(http.get("/sse"), timeout=5)

        assert response.status_code == 404


async def test_post_em_messages_da_404():
    async with _http() as http:
        response = await http.post("/messages/", json={})

        assert response.status_code == 404


async def test_get_em_mcp_nao_abre_stream():
    async with _http() as http:
        response = await asyncio.wait_for(
            http.get("/mcp", headers={"Accept": "text/event-stream"}), timeout=5
        )

        assert response.status_code == 405


async def test_initialize_em_mcp_responde():
    async with _http() as http:
        response = await http.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)

        assert response.status_code == 200
        assert '"serverInfo"' in response.text
