import pytest
from unittest.mock import AsyncMock
from gobus_mcp.client import GobusGraphQLClient


class FakeGraphQLClient:
    """Mock de GobusGraphQLClient para testes — retorna dados pré-configurados."""

    def __init__(self):
        self.execute = AsyncMock(return_value={})

    def set_response(self, data: dict):
        self.execute = AsyncMock(return_value=data)


@pytest.fixture
def fake_client():
    return FakeGraphQLClient()
