"""search_news ao vivo contra a graphql-api de produção (só query de leitura).

Fora do CI: ``pytest -m live tests/test_live_search_news.py``. ``GOBUS_LIVE_URL`` troca o
endpoint. Regressão do roteiro de testes do Desktop: com ``date_from == date_to`` a busca
voltava vazia (o upstream compara ``published_at <= endDate`` e só a data vira 00:00 UTC).
"""

import os
import re
from datetime import date, datetime, timedelta

import pytest

from gobus_mcp.calendario import BRT, is_holiday, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.search_news import search_news
from tests.fixtures.refresh_schema import DEFAULT_URL

pytestmark = pytest.mark.live


class RecordingClient:
    """Repassa ao cliente real e guarda as respostas (para conferir ``publishedAt``)."""

    def __init__(self, inner: GobusGraphQLClient):
        self._inner = inner
        self.responses: list[dict] = []

    async def execute(self, query: str, variables: dict | None = None) -> dict:
        data = await self._inner.execute(query, variables)
        self.responses.append(data)
        return data


def last_closed_workday(today: date) -> date:
    """Último dia útil fechado antes de ``today`` (sem fim de semana nem feriado)."""
    day = today - timedelta(days=1)
    while day.weekday() >= 5 or is_holiday(day):
        day -= timedelta(days=1)
    return day


async def test_mec_no_ultimo_dia_util_tem_artigos_e_so_daquele_dia():
    inner = GobusGraphQLClient(os.environ.get("GOBUS_LIVE_URL") or DEFAULT_URL, timeout=30.0)
    client = RecordingClient(inner)
    day = last_closed_workday(reference_date())

    result = await search_news(
        "*", client, agency_key="mec", date_from=day.isoformat(), date_to=day.isoformat()
    )

    match = re.search(r"\*\*([\d.]+) artigos encontrados\*\*", result)
    assert match, result
    assert int(match.group(1).replace(".", "")) > 0
    articles = client.responses[-1]["search"]["articles"]
    days = {datetime.fromisoformat(a["publishedAt"]).astimezone(BRT).date() for a in articles}
    assert days == {day}
