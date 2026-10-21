"""Perfil completo de entidade: série mensal inteira, agências, cópias e relacionadas."""

import asyncio
import re
from datetime import date

from gobus_mcp.tools.get_entity_profile import get_entity_profile
from tests.conftest import route_catalog

TODAY = date(2026, 10, 21)
ID = "dgb_pe-de-meia"

HIT = {
    "entityId": ID,
    "canonicalName": "Pé-de-Meia",
    "type": "POLICY",
    "description": "Poupança para estudantes do ensino médio",
    "wikidataUrl": None,
    "agencyKey": None,
    "aliases": ["Programa Pé-de-Meia", "Pé de Meia"],
    "articleCount": 1234,
    "confidence": 1.0,
    "matchType": "alias_exact",
}
NODE = {
    "entityId": ID,
    "canonicalName": "Pé-de-Meia",
    "type": "POLICY",
    "aliases": ["Programa Pé-de-Meia"],
    "wikidataId": None,
    "wikidataUrl": None,
    "description": None,
    "agencyKey": None,
}


def _cov(period: str, agency: str, name: str, count: int, mentions: int) -> dict:
    return {
        "period": f"{period}-01 00:00:00+00",
        "agencyKey": agency,
        "agencyName": name,
        "articleCount": count,
        "totalMentions": mentions,
        "avgSentimentScore": None,
    }


# 13 artigos próprios (mec 12, saude 1) + 3 republicações; 20 menções
COVERAGE = [
    _cov("2026-01", "mec", "Ministério da Educação", 3, 5),
    _cov("2026-01", "saude", "Ministério da Saúde", 1, 1),
    _cov("2026-01", "agencia_brasil", "Agência Brasil", 2, 2),
    _cov("2026-04", "mec", "Ministério da Educação", 7, 8),
    _cov("2026-04", "tvbrasil", "TV Brasil", 1, 1),
    _cov("2026-10", "mec", "Ministério da Educação", 2, 3),
]


def _rel(cid: str, name: str, weight: int, kind: str = "ORG") -> dict:
    return {
        "canonicalId": cid,
        "canonicalName": name,
        "type": kind,
        "wikidataId": None,
        "weight": weight,
        "kind": "co_mention",
    }


RELATED = [
    _rel("Q4294522", "Ministério da Educação (MEC)", 650),
    _rel("Q155", "República Federativa do Brasil", 341, "LOC"),
    _rel("Q5419278", "Enem", 306, "EVENT"),
    _rel("Q6041403", "Inep", 295),
    _rel("dgb_portal-gov-br", "Portal Gov.br", 139, "PRODUCT"),
    _rel("Q18242106", "Camilo Santana", 170, "PER"),
    _rel("dgb_saude", "Ministério da Saúde", 4),
]

DEDUP = {"all": {"found": 120}, "distinct": {"found": 104}}


def _route(client, **overrides):
    route_catalog(client)
    routes = {
        "EntitySearch": {"entitySearch": [HIT]},
        "EntityNode": {"entity": NODE},
        "EntityCoverage": {"entityCoverage": COVERAGE},
        "RelatedEntities": {"relatedEntities": RELATED},
        "EntityDedupCounts": DEDUP,
        **overrides,
    }
    for name, response in routes.items():
        client.route(name, response)
    return client


def _header_numbers(text: str) -> tuple[int, int, int]:
    match = re.search(
        r"\*\*([\d.]+) artigos? de (\d+) agências? \+ ([\d.]+) republicaç(?:ão|ões)", text
    )
    assert match, text
    return tuple(int(g.replace(".", "")) for g in match.groups())


def _table(text: str) -> list[tuple[str, int, int]]:
    rows = re.findall(r"^\| (\d{4}[^|]*?) \| (\d+) \| (\d+) \|$", text, flags=re.MULTILINE)
    return [(label, int(own), int(rep)) for label, own, rep in rows]


async def _profile(client, name=ID, **kwargs):
    kwargs.setdefault("today", TODAY)
    return await get_entity_profile(name, client, **kwargs)


# ── cabeçalho e série ───────────────────────────────────────────────────────


async def test_cabecalho_soma_todas_as_linhas(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia", date_from="2026-01-01", date_to="2026-10-20")
    own, agencies, rep = _header_numbers(text)
    assert (own, agencies, rep) == (13, 2, 3)
    assert own + rep == sum(r["articleCount"] for r in COVERAGE)
    assert "20 menções" in text
    assert "**Período:** 01/01/2026 a 20/10/2026" in text


async def test_serie_mensal_inteira_com_zeros_e_mes_parcial(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia", date_from="2026-01-01", date_to="2026-10-20")
    table = _table(text)
    assert [label for label, _, _ in table] == [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
        "2026-06", "2026-07", "2026-08", "2026-09", "2026-10 (parcial)",
    ]  # fmt: skip
    assert table[0] == ("2026-01", 4, 2)
    assert table[1] == ("2026-02", 0, 0)
    assert table[3] == ("2026-04", 7, 1)
    assert sum(own + rep for _, own, rep in table) == sum(_header_numbers(text)[::2])


async def test_entity_coverage_recebe_date_to_mais_um_dia(fake_client):
    _route(fake_client)
    await _profile(fake_client, "Pé-de-Meia", date_from="2026-01-01", date_to="2026-10-20")
    assert fake_client.calls("EntityCoverage") == [
        {"entityId": ID, "granularity": "MONTH", "dateFrom": "2026-01-01", "dateTo": "2026-10-21"}
    ]


async def test_sem_datas_cobre_todo_o_acervo_ate_o_mes_corrente(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia")
    assert fake_client.calls("EntityCoverage") == [{"entityId": ID, "granularity": "MONTH"}]
    table = _table(text)
    assert table[0][0] == "2026-01"
    assert table[-1][0] == "2026-10 (parcial)"
    assert "**Período:** todo o acervo" in text


async def test_mais_de_24_meses_agrega_os_anos_anteriores(fake_client):
    rows = [
        _cov(f"{y}-{m:02d}", "mec", "Ministério da Educação", 1, 1)
        for y in (2023, 2024, 2025, 2026)
        for m in range(1, 13)
        if (y, m) <= (2026, 10)
    ]
    _route(fake_client, EntityCoverage={"entityCoverage": rows})
    text = await _profile(fake_client, "Pé-de-Meia")
    labels = [label for label, _, _ in _table(text)]
    assert labels[:3] == ["2023", "2024 (jan–out)", "2024-11"]
    assert len(labels) == 2 + 24
    assert _header_numbers(text)[0] == len(rows)


async def test_sem_cobertura_no_periodo(fake_client):
    _route(fake_client, EntityCoverage={"entityCoverage": []})
    text = await _profile(fake_client, "Pé-de-Meia", date_from="2026-01-01", date_to="2026-03-31")
    assert "Nenhum artigo no período" in text
    assert "| Mês |" not in text


# ── agências, relacionadas e cópias ─────────────────────────────────────────


async def test_agencias_que_mais_publicaram_sem_republicadoras(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia")
    section = text.split("## Agências que mais publicaram", 1)[1].split("##", 1)[0]
    assert "1. Ministério da Educação (`mec`) — 12 artigos (92%)" in section
    assert "2. Ministério da Saúde (`saude`) — 1 artigo (8%)" in section
    assert "Agência Brasil" not in section


async def test_relacionadas_sem_genericas_rotuladas_todo_o_acervo(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia")
    section = text.split("## Entidades relacionadas", 1)[1]
    assert section.startswith(" (co-menção, todo o acervo)")
    names = re.findall(r"^- \*\*(.+?)\*\*", section, flags=re.MULTILINE)
    assert names == ["Ministério da Educação (MEC)", "Enem", "Inep", "Camilo Santana"]
    hidden = next(line for line in section.splitlines() if line.startswith("Ocultas como"))
    assert "República Federativa do Brasil (341)" in hidden
    assert "Ministério da Saúde (4)" in hidden  # dgb_saude: agência do catálogo
    assert fake_client.calls("RelatedEntities") == [{"id": ID, "limit": 40}]


async def test_copias_identicas_desde_o_indice(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia")
    assert (
        "Desde 20/05/2026 (índice de busca): 120 artigos → 104 textos distintos "
        "(16 cópias idênticas entre agências; só conteúdo idêntico, por hash)"
    ) in text
    (call,) = fake_client.calls("EntityDedupCounts")
    assert call["all"] == {"entityCanonical": [ID], "startDate": "2026-05-20T00:00:00+00:00"}
    assert call["dedup"] == {**call["all"], "dedup": True}


async def test_copias_com_janela_dentro_do_indice(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia", date_from="2026-08-01", date_to="2026-10-20")
    assert "De 01/08/2026 a 20/10/2026 (índice de busca): 120 artigos" in text
    (call,) = fake_client.calls("EntityDedupCounts")
    assert call["all"] == {
        "entityCanonical": [ID],
        "startDate": "2026-08-01T00:00:00+00:00",
        "endDate": "2026-10-21T00:00:00+00:00",
    }


async def test_janela_antes_do_indice_nao_conta_copias(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia", date_from="2026-01-01", date_to="2026-04-30")
    assert fake_client.calls("EntityDedupCounts") == []
    assert "20/05/2026" in text
    assert "não medidas" in text


async def test_sem_copias(fake_client):
    _route(fake_client, EntityDedupCounts={"all": {"found": 7}, "distinct": {"found": 7}})
    text = await _profile(fake_client, "Pé-de-Meia")
    assert "7 artigos → 7 textos distintos (nenhuma cópia idêntica" in text


# ── entrada e degradação ────────────────────────────────────────────────────


async def test_id_vai_direto_ao_no_sem_busca_fuzzy(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, ID)
    assert fake_client.calls("EntitySearch") == []
    assert fake_client.calls("EntityNode") == [{"id": ID}]
    assert text.startswith("# Pé-de-Meia (POLICY)")


async def test_id_inexistente(fake_client):
    _route(fake_client, EntityNode={"entity": None})
    text = await _profile(fake_client, "Q999999999")
    assert "Entidade não encontrada" in text


async def test_nome_nao_encontrado_nao_consulta_o_resto(fake_client):
    _route(fake_client, EntitySearch={"entitySearch": []})
    text = await _profile(fake_client, "xyz_inexistente")
    assert "Entidade não encontrada: **xyz_inexistente**" in text
    assert fake_client.calls("EntityCoverage") == []


async def test_entity_type_vai_para_a_busca(fake_client):
    _route(fake_client)
    await _profile(fake_client, "Pé-de-Meia", entity_type="policy")
    assert fake_client.calls("EntitySearch") == [{"query": "Pé-de-Meia", "entityType": "POLICY"}]


async def test_falha_nas_relacionadas_vira_nota(fake_client):
    _route(fake_client, RelatedEntities=RuntimeError("timeout"))
    text = await _profile(fake_client, "Pé-de-Meia")
    assert "Entidades relacionadas indisponíveis (timeout)" in text
    assert _header_numbers(text)[0] == 13


async def test_falha_na_cobertura_vira_nota(fake_client):
    _route(fake_client, EntityCoverage=RuntimeError("asyncpg"))
    text = await _profile(fake_client, "Pé-de-Meia")
    assert "Cobertura indisponível (asyncpg)" in text
    assert "## Entidades relacionadas" in text


async def test_falha_nas_copias_vira_nota(fake_client):
    _route(fake_client, EntityDedupCounts=RuntimeError("typesense"))
    text = await _profile(fake_client, "Pé-de-Meia")
    assert "Contagem de cópias idênticas indisponível (typesense)" in text
    assert _header_numbers(text)[0] == 13


async def test_catalogo_fora_do_ar_usa_republicadoras_fixas(fake_client):
    _route(fake_client)
    fake_client.route("CatalogAgencies", RuntimeError("graphql fora do ar"))
    text = await _profile(fake_client, "Pé-de-Meia")
    assert "Catálogo indisponível" in text
    assert _header_numbers(text) == (13, 2, 3)  # agencia_brasil e tvbrasil na lista fixa


async def test_data_invalida(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia", date_from="2026-13-01")
    assert "Data inválida" in text
    assert fake_client.calls("EntitySearch") == []


async def test_consultas_em_paralelo(fake_client):
    expected = {"EntityCoverage", "RelatedEntities", "EntityDedupCounts"}
    started: set[str] = set()
    all_started = asyncio.Event()

    def waiting(name, response):
        async def handler(_variables):
            started.add(name)
            if started == expected:
                all_started.set()
            # em série, a primeira consulta esperaria para sempre pelas outras
            await asyncio.wait_for(all_started.wait(), timeout=1.0)
            return response

        return handler

    _route(
        fake_client,
        EntityCoverage=waiting("EntityCoverage", {"entityCoverage": COVERAGE}),
        RelatedEntities=waiting("RelatedEntities", {"relatedEntities": RELATED}),
        EntityDedupCounts=waiting("EntityDedupCounts", DEDUP),
    )
    text = await _profile(fake_client, "Pé-de-Meia")
    assert started == expected
    assert "indisponíve" not in text


async def test_summary_only_traz_totais_e_top3_sem_genericas(fake_client):
    _route(fake_client)
    text = await _profile(fake_client, "Pé-de-Meia", summary_only=True)
    assert _header_numbers(text) == (13, 2, 3)
    assert "| Mês |" not in text
    assert (
        "**Top relacionadas:** Ministério da Educação (MEC) (ORG), Enem (EVENT), Inep (ORG)"
    ) in text
    assert fake_client.calls("EntityDedupCounts") == []
