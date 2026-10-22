"""Smoke ao vivo do PR-E (links, ranking por associação e Flesch pt-BR) contra a graphql-api de
produção (só queries de leitura).

Fora do CI: ``pytest -m live tests/test_live_links_lift_flesch.py -s``. ``GOBUS_LIVE_URL``
troca o endpoint. Antes do deploy do GQL-1 (graphql-api#32), os testes conferem a reserva
(queries ``*Legacy`` válidas no SDL ao vivo, peso bruto, Flesch inglês com aviso); depois,
os campos novos (links, lift, Flesch pt-BR com mediana ≈ 15).
"""

import importlib
import os
import pkgutil
import re
import statistics

import pytest
from graphql import build_schema, parse, validate

import gobus_mcp
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.schema_compat import ARTICLE_SUMMARY_URL, COMPAT, FLESCH_PTBR, RELATED_LIFT
from gobus_mcp.tools.detect_trends import detect_trends
from gobus_mcp.tools.get_entity_network import get_entity_network
from tests.fixtures.refresh_schema import DEFAULT_URL, fetch_sdl

pytestmark = pytest.mark.live

PE_DE_MEIA = "dgb_pe-de-meia"
MEC = "Q4294522"

_FLESCH_SAMPLE_QUERY = """
query LiveFleschSample($limit: Int!) {
  articles(page: 1, limit: $limit, sort: DATE) {
    articles { uniqueId features { readabilityFlesch readabilityFleschPtbr wordCount } }
  }
}
"""


@pytest.fixture
def client():
    return GobusGraphQLClient(os.environ.get("GOBUS_LIVE_URL") or DEFAULT_URL, timeout=30.0)


@pytest.fixture(scope="module")
def live_schema():
    return build_schema(fetch_sdl(os.environ.get("GOBUS_LIVE_URL") or DEFAULT_URL))


def _queries() -> dict[str, str]:
    found: dict[str, str] = {}
    for info in pkgutil.walk_packages(gobus_mcp.__path__, prefix="gobus_mcp."):
        if info.name.endswith("__main__"):
            continue
        module = importlib.import_module(info.name)
        for attr, value in vars(module).items():
            if attr.endswith("_QUERY") and isinstance(value, str):
                found[f"{info.name}.{attr}"] = value
    return found


def test_toda_query_ou_a_sua_reserva_vale_no_sdl_ao_vivo(live_schema):
    queries = _queries()
    broken = []
    for name, query in queries.items():
        if not validate(live_schema, parse(query)):
            continue
        legacy = re.sub(r"_QUERY$", "_LEGACY_QUERY", name)
        if legacy == name or legacy not in queries or validate(live_schema, parse(queries[legacy])):
            broken.append(name)
    assert broken == [], f"sem reserva válida em produção: {broken}"


async def test_rede_pe_de_meia_mec_primeiro_e_cabecalho_do_ranking(client):
    markdown = await get_entity_network(PE_DE_MEIA, client)
    print(markdown)

    first = re.search(r"^1\. \*\*.+?\*\* .* · `([^`]+)`$", markdown, flags=re.MULTILINE)
    assert first and first.group(1) == MEC
    ranking = next(line for line in markdown.splitlines() if line.startswith("**Ranking:**"))
    if COMPAT.available(RELATED_LIFT) and "associação" in ranking:
        assert "o esperado" in markdown
    else:
        assert "peso bruto" in ranking
    assert "**Para explorar:**" in markdown


async def test_temas_em_alta_com_link_quando_a_api_traz_url(client):
    markdown = await detect_trends(client, window_days=7, baseline_days=28, growth_threshold=1.0)
    print(markdown)

    articles = [line for line in markdown.splitlines() if line.startswith("   - ")]
    if not articles:
        pytest.skip("nenhum tema em alta com artigos na janela")
    if COMPAT.available(ARTICLE_SUMMARY_URL):
        assert any("](http" in line for line in articles)
    else:
        assert all(re.search(r"`[^`]+`$", line) for line in articles)  # id para o get_article


async def test_flesch_ptbr_mediana_perto_de_15_e_nao_40_acima_do_ingles(client):
    from gobus_mcp.client import GobusGraphQLError
    from gobus_mcp.schema_compat import is_schema_mismatch

    try:
        data = await client.execute(_FLESCH_SAMPLE_QUERY, {"limit": 250})
    except GobusGraphQLError as exc:
        if is_schema_mismatch(exc):
            pytest.skip("a API ainda não expõe readabilityFleschPtbr (GQL-1)")
        raise
    feats = [a.get("features") or {} for a in (data.get("articles") or {}).get("articles") or []]
    ptbr = [f["readabilityFleschPtbr"] for f in feats if f.get("readabilityFleschPtbr") is not None]
    if len(ptbr) < 20:
        pytest.skip(f"só {len(ptbr)} artigos recentes com Flesch pt-BR (backfill 033 pendente?)")
    median = statistics.median(ptbr)
    pairs = [
        f["readabilityFleschPtbr"] - f["readabilityFlesch"]
        for f in feats
        if f.get("readabilityFleschPtbr") is not None and f.get("readabilityFlesch") is not None
    ]
    print(f"\n[Flesch pt-BR] n={len(ptbr)} mediana={median:.1f}; pares={len(pairs)}")
    assert 0 <= median <= 40  # notícia de governo: ≈ 15 ("muito difícil")
    if len(pairs) >= 20:
        assert abs(statistics.median(pairs)) < 15  # ≈ +2, não os +42 da constante de Martins
    assert FLESCH_PTBR  # a feature existe no compat
