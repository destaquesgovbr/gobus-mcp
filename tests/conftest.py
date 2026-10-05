import re
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

_OPERATION_NAME_RE = re.compile(r"^\s*(?:query|mutation|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)")

RouteResponse = dict | BaseException | Callable[[dict | None], dict]


def operation_name(query: str) -> str | None:
    """Nome da operação GraphQL (``query Nome(...)``); ``None`` se anônima."""
    match = _OPERATION_NAME_RE.match(query)
    return match.group(1) if match else None


class FakeGraphQLClient:
    """Mock de GobusGraphQLClient para testes — retorna dados pré-configurados.

    Três modos (o último configurado vale):
    - ``set_response(data)``: toda chamada devolve ``data``;
    - ``set_responses([...])``: devolve em ordem (frágil com gather/semáforo);
    - ``route(op_name, resposta)``: despacha pelo nome da operação GraphQL. A resposta
      pode ser um dict, uma exceção (levantada) ou um callable ``f(variables) -> dict``.
      Preferir ``route`` em todo teste novo.
    """

    def __init__(self):
        self.execute = AsyncMock(return_value={})
        self._routes: dict[str, RouteResponse] = {}
        self._calls: dict[str, list[dict | None]] = {}

    def set_response(self, data: dict):
        self.execute = AsyncMock(return_value=data)

    def set_responses(self, responses: list[dict]) -> None:
        self.execute = AsyncMock(side_effect=list(responses))

    def route(self, op_name: str, response: RouteResponse) -> "FakeGraphQLClient":
        """Registra a resposta para a operação ``op_name`` e liga o despacho por nome."""
        if getattr(self.execute, "side_effect", None) != self._dispatch:
            self.execute = AsyncMock(side_effect=self._dispatch)
        self._routes[op_name] = response
        return self

    def calls(self, op_name: str) -> list[dict | None]:
        """Variáveis de cada chamada roteada para ``op_name``, em ordem."""
        return list(self._calls.get(op_name, []))

    async def _dispatch(self, query: str, variables: dict | None = None, **_: Any) -> dict:
        name = operation_name(query)
        if name is None or name not in self._routes:
            raise AssertionError(
                f"FakeGraphQLClient: sem rota para a operação {name!r}; "
                f"rotas registradas: {sorted(self._routes)}"
            )
        self._calls.setdefault(name, []).append(variables)
        response = self._routes[name]
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response(variables)
        return response


@pytest.fixture
def fake_client():
    return FakeGraphQLClient()
