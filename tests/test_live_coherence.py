"""Smoke ao vivo do F5 contra a graphql-api de produção (só queries de leitura).

Fora do CI: ``pytest -m live tests/test_live_coherence.py -s`` (o ``-s`` imprime o
Markdown). ``GOBUS_LIVE_URL`` troca o endpoint. Critério de aceite do F5 (plano §11):
``Q575545`` (Bolsa Família) em 01/08–30/09/2026 em ≤ 3 s, saída ≤ 5 KB, índice 1–5 com a
tabela de dimensões e republicadoras em seção separada.
"""

import os
import time

import pytest

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.payloads.coherence import CoherenceReport
from gobus_mcp.payloads.common import MAX_PAYLOAD_BYTES, payload_size
from gobus_mcp.tools.get_message_coherence import build_coherence_output
from tests.fixtures.refresh_schema import DEFAULT_URL

pytestmark = pytest.mark.live


@pytest.fixture
def live():
    client = GobusGraphQLClient(os.environ.get("GOBUS_LIVE_URL") or DEFAULT_URL, timeout=30.0)
    return client, AgencyCatalog(client)


async def test_bolsa_familia_ago_set_ao_vivo(live):
    client, catalog = live

    start = time.perf_counter()
    report, markdown = await build_coherence_output(
        client, entity_id="Q575545", date_from="2026-08-01", date_to="2026-09-30", catalog=catalog
    )
    elapsed = time.perf_counter() - start
    size = len(markdown.encode())
    print(f"\n[coerência] {elapsed:.2f} s · {size} B · payload {payload_size(report)} B")
    print(markdown)

    CoherenceReport.model_validate(report.model_dump(mode="json"))
    assert elapsed <= 3.0
    assert size <= 5_120
    assert payload_size(report) <= MAX_PAYLOAD_BYTES
    assert report.subject.label == "Bolsa Família"
    assert report.sample.found > 0
    assert report.index_status in ("scored", "insufficient")
    if report.index_status == "scored":
        assert 1 <= report.index.level <= 5
        assert "| Dimensão | Valor | Peso | Leitura |" in markdown
    republishers = {"agencia_brasil", "tvbrasil", "ebc", "radioagencia_nacional"}
    assert not republishers & {a.agency_key for a in report.agencies}
    assert "### Republicadoras" in markdown


async def test_tema_em_junho_ao_vivo(live):
    client, catalog = live

    report, markdown = await build_coherence_output(
        client,
        theme="Defesa e Forças Armadas",
        date_from="2026-06-01",
        date_to="2026-06-30",
        catalog=catalog,
    )
    print(f"\n{markdown}")

    assert report.subject.kind == "theme"
    assert report.sample.found > 0
    # junho/2026 está classificado: sem aviso de tema
    assert "THEMES_UNCLASSIFIED" not in {n.code for n in report.notices}
