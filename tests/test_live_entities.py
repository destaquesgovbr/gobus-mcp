"""Smoke ao vivo da rede e do perfil de entidades contra a graphql-api de produção (só
queries de leitura).

Fora do CI: ``pytest -m live tests/test_live_entities.py -s`` (o ``-s`` imprime o
Markdown). ``GOBUS_LIVE_URL`` troca o endpoint. Critérios do PR-B (roteiro 2.1/2.2):
Pé-de-Meia com o MEC como primeiro vizinho e sem o Brasil (Q155) por padrão; depth=2 em
≤ 3 s; perfil 2026-01-01..2026-10-20 com 10 meses e cabeçalho = soma da série.
"""

import os
import re
import time
from datetime import date

import pytest

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from tests.fixtures.refresh_schema import DEFAULT_URL

pytestmark = pytest.mark.live

PE_DE_MEIA = "dgb_pe-de-meia"
MEC = "Q4294522"


@pytest.fixture
def live():
    client = GobusGraphQLClient(os.environ.get("GOBUS_LIVE_URL") or DEFAULT_URL, timeout=30.0)
    return client, AgencyCatalog(client)


def _ranked_ids(markdown: str) -> list[str]:
    return re.findall(r"^\d+\. \*\*.+?\*\* .* · `([^`]+)`$", markdown, flags=re.MULTILINE)


def _int(text: str) -> int:
    return int(text.replace(".", ""))


async def test_pe_de_meia_depth1_mec_primeiro_e_sem_genericas(live):
    client, _ = live
    markdown = await get_entity_network(PE_DE_MEIA, client, depth=1)
    print(markdown)

    ranked = _ranked_ids(markdown)
    assert ranked[0] == MEC
    assert "`Q155`" not in markdown.split("Ocultas como genéricas", 1)[0]
    assert "República Federativa do Brasil" in markdown.split("Ocultas como genéricas", 1)[1]

    with_generic = await get_entity_network(PE_DE_MEIA, client, depth=1, include_generic=True)
    assert "`Q155`" in with_generic


async def test_pe_de_meia_depth2_em_ate_3s(live):
    client, _ = live

    start = time.perf_counter()
    markdown = await get_entity_network(PE_DE_MEIA, client, depth=2, cache=TTLCache())
    elapsed = time.perf_counter() - start
    print(f"\n[rede depth=2] {elapsed:.2f} s · {len(markdown.encode())} B")
    print(markdown)

    assert elapsed <= 3.0
    assert "## Segundo grau (via os 5 primeiros vizinhos)" in markdown
    assert "Não foi possível expandir" not in markdown
    assert len(markdown.encode()) <= 8_192


async def test_perfil_pe_de_meia_jan_out_soma_a_serie(live):
    client, catalog = live
    markdown = await get_entity_profile(
        PE_DE_MEIA,
        client,
        date_from="2026-01-01",
        date_to="2026-10-20",
        catalog=catalog,
        today=date(2026, 10, 21),
    )
    print(markdown)

    header = re.search(
        r"\*\*([\d.]+) artigos? de \d+ agências? \+ ([\d.]+) republicaç(?:ão|ões)", markdown
    )
    assert header, markdown
    table = re.findall(
        r"^\| (2026-\d\d(?: \(parcial\))?) \| ([\d.]+) \| ([\d.]+) \|$", markdown, re.MULTILINE
    )
    assert [label for label, _, _ in table][0] == "2026-01"
    assert len(table) == 10
    assert table[-1][0] == "2026-10 (parcial)"
    series_total = sum(_int(own) + _int(rep) for _, own, rep in table)
    assert _int(header.group(1)) + _int(header.group(2)) == series_total
    assert "## Cópias idênticas" not in markdown  # no máximo uma linha, e só se houver cópia
    assert "## Entidades relacionadas (co-menção, todo o acervo)" in markdown
