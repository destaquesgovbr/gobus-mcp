"""CORS só para desenvolvimento (``GOBUS_CORS_ORIGINS``).

O basic-host do ext-apps conecta direto do navegador no ``/mcp`` local, então precisa de
CORS. Em produção a variável não existe (o Terraform nunca a define): sem ela, o servidor
HTTP não manda nenhum header ``access-control-*``.
"""

import httpx

from gobus_mcp import server
from gobus_mcp.config import Settings

ORIGIN = "http://localhost:8080"
PREFLIGHT = {
    "Origin": ORIGIN,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type,mcp-protocol-version",
}


async def _preflight(middleware) -> httpx.Response:
    app = server.mcp.http_app(middleware=middleware, stateless_http=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options("/mcp", headers=PREFLIGHT)


def test_settings_sem_cors_por_padrao(monkeypatch):
    monkeypatch.delenv("GOBUS_CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == ""


def test_sem_origens_nao_ha_middleware():
    assert server.http_middleware("") == []
    assert server.http_middleware("  ") == []


async def test_preflight_com_origem_configurada_libera_o_navegador():
    response = await _preflight(server.http_middleware(f"{ORIGIN}, http://localhost:8081"))

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]


async def test_origem_fora_da_lista_nao_e_liberada():
    response = await _preflight(server.http_middleware("http://localhost:9999"))

    assert "access-control-allow-origin" not in response.headers


async def test_sem_a_variavel_nao_ha_header_de_cors():
    response = await _preflight(server.http_middleware(""))

    assert not [h for h in response.headers if h.lower().startswith("access-control-")]
