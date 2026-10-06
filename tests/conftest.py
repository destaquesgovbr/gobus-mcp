import inspect
import re
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

_OPERATION_NAME_RE = re.compile(r"^\s*(?:query|mutation|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)")

RouteResponse = dict | BaseException | Callable[[dict | None], dict | Awaitable[dict]]


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
      pode ser um dict, uma exceção (levantada) ou um callable ``f(variables) -> dict``
      (síncrono ou ``async``, para testar concorrência).
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
            result = response(variables)
            return await result if inspect.isawaitable(result) else result
        return response


@pytest.fixture
def fake_client():
    return FakeGraphQLClient()


# ── catálogo de agências fictício (rotas CatalogAgencies / Names / TopAgencies) ──

# (código, republicadora, nome humano). A ordem é a do topAgencies (mais ativas primeiro).
CATALOG_AGENCIES: list[tuple[str, bool, str]] = [
    ("agencia_brasil", True, "Agência Brasil"),
    ("saude", False, "Ministério da Saúde"),
    ("mec", False, "Ministério da Educação"),
    ("secom", False, "Secretaria de Comunicação Social"),
    ("cgu", False, "Controladoria-Geral da União"),
    ("defesa", False, "Ministério da Defesa"),
    ("pf", False, "Polícia Federal"),
    ("trabalho-e-emprego", False, "Ministério do Trabalho e Emprego"),
    ("mds", False, "Ministério do Desenvolvimento e Assistência Social"),
    ("tvbrasil", True, "TV Brasil"),
]


def route_catalog(
    client: FakeGraphQLClient,
    agencies: list[tuple[str, bool, str]] | None = None,
    *,
    active: list[str] | None = None,
) -> FakeGraphQLClient:
    """Registra as 3 operações do ``AgencyCatalog`` no fake.

    ``active`` = ordem do ``topAgencies`` (padrão: a ordem de ``agencies``).
    """
    agencies = CATALOG_AGENCIES if agencies is None else agencies
    ranking = active if active is not None else [code for code, _, _ in agencies]
    names = {code: name for code, _, name in agencies}
    client.route(
        "CatalogAgencies",
        {"agencies": [{"code": c, "isRepublisher": r} for c, r, _ in agencies]},
    )
    client.route(
        "CatalogAgencyNames",
        lambda v: {
            "agencyAnalytics": [
                {"agencyKey": c, "agencyName": names[c]} for c in v["agencies"] if c in names
            ]
        },
    )
    client.route(
        "CatalogTopAgencies",
        lambda v: {
            "topAgencies": [{"name": c, "count": 1000 - i} for i, c in enumerate(ranking)][
                : v["limit"]
            ]
        },
    )
    return client
