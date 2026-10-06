"""``GobusGraphQLClient``: timeout padrão e por chamada."""

import pytest

from gobus_mcp import client as client_module
from gobus_mcp.client import GobusGraphQLClient, GobusGraphQLError


class _Response:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _FakeAsyncClient:
    instances: list["_FakeAsyncClient"] = []
    body: dict = {"data": {"ok": True}}

    def __init__(self, *, timeout):
        self.timeout = timeout
        self.posts: list[dict] = []
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, json, headers):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _Response(self.body)


@pytest.fixture
def fake_http(monkeypatch):
    _FakeAsyncClient.instances = []
    _FakeAsyncClient.body = {"data": {"ok": True}}
    monkeypatch.setattr(client_module.httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


async def test_usa_o_timeout_padrao(fake_http):
    gql = GobusGraphQLClient("http://api/graphql", timeout=10.0)
    assert await gql.execute("query Q { x }") == {"ok": True}
    assert fake_http.instances[0].timeout == 10.0


async def test_timeout_por_chamada(fake_http):
    gql = GobusGraphQLClient("http://api/graphql", api_key="k", timeout=10.0)
    await gql.execute("query Q($a: Int!) { x }", {"a": 1}, timeout=30.0)
    http = fake_http.instances[0]
    assert http.timeout == 30.0
    assert http.posts[0]["json"] == {"query": "query Q($a: Int!) { x }", "variables": {"a": 1}}
    assert http.posts[0]["headers"] == {"X-API-Key": "k"}


async def test_erros_graphql_levantam(fake_http):
    fake_http.body = {"errors": [{"message": "boom"}]}
    with pytest.raises(GobusGraphQLError, match="boom"):
        await GobusGraphQLClient("http://api/graphql").execute("query Q { x }")
