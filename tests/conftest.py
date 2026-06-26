import pytest
from unittest.mock import AsyncMock
from gobus_mcp.client import GobusGraphQLClient


class FakeGraphQLClient:
    """Mock de GobusGraphQLClient para testes — retorna dados pré-configurados."""

    def __init__(self):
        self.execute = AsyncMock(return_value={})

    def set_response(self, data: dict):
        self.execute = AsyncMock(return_value=data)

    def set_responses(self, responses: list[dict]) -> None:
        self.execute = AsyncMock(side_effect=list(responses))


@pytest.fixture
def fake_client():
    return FakeGraphQLClient()
