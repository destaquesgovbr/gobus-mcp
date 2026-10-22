"""Rede de entidades centrada no foco (``relatedEntities``), com filtro de genéricas.

O grafo fictício imita o Pé-de-Meia de 21/10/2026: o MEC é o vizinho mais forte; Brasil,
Brasília, Governo Federal e Portal Gov.br são genéricas; ``dgb_saude`` (entidade da própria
agência ``saude``) é um vizinho comum: na rede, ministérios não são ruído.
"""

import asyncio
import re

from gobus_mcp.cache import TTLCache
from gobus_mcp.tools import get_entity_network as network_module
from gobus_mcp.tools.get_entity_network import get_entity_network

FOCUS = "dgb_pe-de-meia"


def _rel(cid: str, name: str, weight: int, kind: str = "ORG") -> dict:
    return {
        "canonicalId": cid,
        "canonicalName": name,
        "type": kind,
        "wikidataId": cid if cid.startswith("Q") else None,
        "weight": weight,
        "kind": "co_mention",
    }


MEC = _rel("Q4294522", "Ministério da Educação (MEC)", 650)
ENEM = _rel("Q5419278", "Enem", 306, "EVENT")
INEP = _rel("Q6041403", "Inep", 295)
ESCOLA = _rel("dgb_escola-em-tempo-integral", "Escola em Tempo Integral", 180, "POLICY")
CAMILO = _rel("Q18242106", "Camilo Santana", 170, "PER")
BOLSA = _rel("Q575545", "Bolsa Família", 115, "POLICY")
BRASIL = _rel("Q155", "República Federativa do Brasil", 341, "LOC")
PORTAL = _rel("dgb_portal-gov-br", "Portal Gov.br", 139, "PRODUCT")
BRASILIA = _rel("Q2844", "Brasília", 77, "LOC")
GOVERNO = _rel("Q5440531", "Governo Federal do Brasil", 69)
SAUDE = _rel("dgb_saude", "Ministério da Saúde", 4)
PLACES = [
    _rel("Q119158", "Distrito Federal", 70, "LOC"),
    _rel("dgb_ceara", "Ceará", 30, "LOC"),
    _rel("dgb_piaui", "Piauí", 26, "LOC"),
    _rel("dgb_amazonas", "Amazonas", 20, "LOC"),
    _rel("dgb_pernambuco", "Pernambuco", 17, "LOC"),
    _rel("dgb_roraima", "Roraima", 16, "LOC"),
    _rel("dgb_sergipe", "Sergipe", 15, "LOC"),
]

# Em ordem alfabética de propósito: a tool ordena pelo peso.
FIRST_HOP = sorted(
    [MEC, ENEM, INEP, ESCOLA, CAMILO, BOLSA, BRASIL, PORTAL, BRASILIA, GOVERNO, SAUDE, *PLACES],
    key=lambda r: r["canonicalName"],
)

SISU = _rel("Q3", "Sisu", 152, "POLICY")
PROUNI = _rel("Q8", "Prouni", 146, "POLICY")
SEB = _rel("Q4", "Secretaria de Educação Básica", 891)
FOCUS_ROW = _rel(FOCUS, "Pé-de-Meia", 650, "POLICY")

SECOND_HOP: dict[str, list[dict]] = {
    MEC["canonicalId"]: [
        _rel("Q155", "República Federativa do Brasil", 4135, "LOC"),
        _rel("Q2844", "Brasília", 1891, "LOC"),
        _rel("Q6041403", "Inep", 1564),
        _rel("Q1", "FNDE", 1300),
        _rel("Q2", "Capes", 1030),
        SEB,
        FOCUS_ROW,
        _rel("Q5", "Fies", 599, "POLICY"),
        _rel("Q6", "Sesu", 400),
        _rel("Q7", "Ebserh", 300),
        SISU,
    ],
    ENEM["canonicalId"]: [
        _rel("Q4294522", "Ministério da Educação (MEC)", 724),
        _rel("Q6041403", "Inep", 417),
        _rel("dgb_portal-gov-br", "Portal Gov.br", 205, "PRODUCT"),
        SISU,
        PROUNI,
        FOCUS_ROW,
    ],
    INEP["canonicalId"]: [
        _rel("Q4294522", "Ministério da Educação (MEC)", 1564),
        _rel("Q9", "Diário Oficial da União", 281),
        _rel("Q3", "Sisu", 202, "POLICY"),
        _rel("Q8", "Prouni", 190, "POLICY"),
    ],
    ESCOLA["canonicalId"]: [
        _rel("Q4294522", "Ministério da Educação (MEC)", 700),
        _rel("Q4", "Secretaria de Educação Básica", 252),
    ],
    CAMILO["canonicalId"]: [
        _rel("Q4294522", "Ministério da Educação (MEC)", 1351),
        _rel("Q37181", "Lula", 775, "PER"),
    ],
    BOLSA["canonicalId"]: [_rel("Q10", "MDS", 900)],
}

NODES = {FOCUS: {"entityId": FOCUS, "canonicalName": "Pé-de-Meia", "type": "POLICY"}}


def _related(v: dict) -> dict:
    rows = FIRST_HOP if v["id"] == FOCUS else SECOND_HOP.get(v["id"], [])
    return {"relatedEntities": rows[: v["limit"]]}


def _route(client, *, related=_related):
    client.route("EntityNode", lambda v: {"entity": NODES.get(v["id"])})
    client.route("RelatedEntities", related)
    return client


def _ranked(text: str) -> list[str]:
    """Nomes da lista numerada de vizinhos diretos, na ordem."""
    return re.findall(r"^\d+\. \*\*(.+?)\*\*", text, flags=re.MULTILINE)


def _line(text: str, prefix: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(prefix))


# ── depth=1 ─────────────────────────────────────────────────────────────────


async def test_ranking_por_peso_e_nao_por_nome(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client)
    assert _ranked(text) == [
        "Ministério da Educação (MEC)",
        "Enem",
        "Inep",
        "Escola em Tempo Integral",
        "Camilo Santana",
        "Bolsa Família",
        "Ministério da Saúde",
    ]
    assert "# Rede de entidades: Pé-de-Meia" in text
    assert "1. **Ministério da Educação (MEC)** (ORG) · 650 artigos em co-menção · `Q4294522`" in (
        text
    )


async def test_cabecalho_honesto_mostrados_de_total(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, max_nodes=3)
    # 7 não-lugares + 7 lugares visíveis = 14; mostra 3 da lista + 5 lugares
    assert "Mostrando 8 de 14 vizinhos diretos" in text
    assert "pesos = artigos em co-menção em todo o acervo, inclui republicações" in text
    assert _ranked(text) == ["Ministério da Educação (MEC)", "Enem", "Inep"]


async def test_genericas_ocultas_por_padrao_com_linha_de_aviso(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client)
    ranked = _ranked(text)
    for name in ("República Federativa do Brasil", "Portal Gov.br", "Governo Federal do Brasil"):
        assert name not in ranked
    hidden = _line(text, "Ocultas como genéricas:")
    assert hidden.startswith(
        "Ocultas como genéricas: República Federativa do Brasil (341), Portal Gov.br (139), "
        "Brasília (77), Governo Federal do Brasil (69) — "
    )
    assert "include_generic=true" in hidden
    assert "Brasília" not in _line(text, "**Lugares:**")


async def test_dou_fica_oculto_como_generico_sem_perder_a_contagem(fake_client):
    # INSS em 21/10/2026: o DOU era o 10º vizinho (195) com lift 0,90 (< 1, sem associação)
    dou = _rel("Q3712237", "Diário Oficial da União (DOU)", 200)

    def related(v):
        rows = [*FIRST_HOP, dou] if v["id"] == FOCUS else SECOND_HOP.get(v["id"], [])
        return {"relatedEntities": rows[: v["limit"]]}

    _route(fake_client, related=related)
    text = await get_entity_network(FOCUS, fake_client)

    assert "Diário Oficial da União (DOU)" not in _ranked(text)
    assert "Diário Oficial da União (DOU) (200)" in _line(text, "Ocultas como genéricas:")
    shown = await get_entity_network(FOCUS, fake_client, include_generic=True)
    assert "Diário Oficial da União (DOU)" in _ranked(shown)


async def test_depth2_dou_nao_vira_ponte(fake_client):
    dou = _rel("Q3712237", "Diário Oficial da União (DOU)", 500)
    second = {k: [*rows, dou] for k, rows in SECOND_HOP.items()}

    def related(v):
        rows = FIRST_HOP if v["id"] == FOCUS else second.get(v["id"], [])
        return {"relatedEntities": rows[: v["limit"]]}

    _route(fake_client, related=related)
    text = await get_entity_network(FOCUS, fake_client, depth=2)

    assert "Diário Oficial da União (DOU)" not in _line(text, "**Pontes**")
    via = [line for line in text.splitlines() if line.startswith("- via **")]
    assert via and not any("`Q3712237`" in line for line in via)


async def test_include_generic_mostra_as_genericas(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, include_generic=True)
    ranked = _ranked(text)
    assert ranked[:2] == ["Ministério da Educação (MEC)", "Enem"]
    assert "Portal Gov.br" in ranked
    assert "Governo Federal do Brasil" in ranked
    assert "Ministério da Saúde" in ranked
    assert "República Federativa do Brasil (341" in _line(text, "**Lugares:**")
    assert "Ocultas como genéricas" not in text


async def test_entidade_da_agencia_e_vizinho_comum(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client)
    assert "Ministério da Saúde" in _ranked(text)
    assert "Ministério da Saúde" not in _line(text, "Ocultas como genéricas:")


async def test_nao_consulta_o_catalogo_de_agencias(fake_client):
    _route(fake_client)
    fake_client.route("CatalogAgencies", {"agencies": [{"code": "saude"}]})
    await get_entity_network(FOCUS, fake_client, depth=2)
    assert fake_client.calls("CatalogAgencies") == []


async def test_lugares_em_linha_separada_limitados_a_5(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client)
    places = _line(text, "**Lugares:**")
    assert "Distrito Federal (70" in places
    assert "Pernambuco (17" in places
    assert "Roraima" not in places
    assert places.rstrip().endswith("+2 lugares")
    for name in ("Distrito Federal", "Ceará"):
        assert name not in _ranked(text)


async def test_node_types_filtra_a_lista(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, node_types="PER, policy")
    assert _ranked(text) == ["Escola em Tempo Integral", "Camilo Santana", "Bolsa Família"]
    assert "**Lugares:**" not in text
    assert "Mostrando 3 de 3 vizinhos diretos" in text


async def test_node_types_loc_lista_lugares_sem_teto(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, node_types="LOC")
    assert _ranked(text) == [p["canonicalName"] for p in PLACES]
    assert "**Lugares:**" not in text


async def test_limit_e_vizinhos_considerados_ate_200(fake_client):
    _route(fake_client)
    await get_entity_network(FOCUS, fake_client, limit=500)
    assert fake_client.calls("RelatedEntities") == [{"id": FOCUS, "limit": 200}]


async def test_limite_atingido_vira_mais(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, limit=5)
    # top 5 por peso no upstream (aqui o fake corta a lista alfabética: só importa o "+")
    assert re.search(r"Mostrando \d+ de \d+\+ vizinhos diretos", text)
    assert "limite de 5 vizinhos" in text


async def test_nunca_usa_entity_network(fake_client):
    _route(fake_client)
    fake_client.route("EntityNetwork", {"entityNetwork": {"nodes": [], "edges": []}})
    await get_entity_network(FOCUS, fake_client, depth=2)
    assert fake_client.calls("EntityNetwork") == []
    sources = [v for k, v in vars(network_module).items() if k.endswith("_QUERY")]
    assert all("entityNetwork" not in q for q in sources)


async def test_rede_vazia(fake_client):
    _route(fake_client, related=lambda v: {"relatedEntities": []})
    text = await get_entity_network("Q_inexistente", fake_client)
    assert "Nenhuma rede encontrada" in text


async def test_resposta_vazia_da_api_nao_quebra(fake_client):
    text = await get_entity_network("Q1", fake_client)  # AsyncMock devolve {}
    assert "Nenhuma rede encontrada" in text


async def test_falha_nos_vizinhos_vira_mensagem(fake_client):
    _route(fake_client, related=RuntimeError("timeout"))
    text = await get_entity_network(FOCUS, fake_client)
    assert "indisponível" in text
    assert "timeout" in text


async def test_sem_no_canonico_usa_o_id_no_titulo(fake_client):
    _route(fake_client)
    fake_client.route("EntityNode", RuntimeError("falhou"))
    text = await get_entity_network(FOCUS, fake_client)
    assert f"# Rede de entidades: {FOCUS}" in text
    assert _ranked(text)[0] == "Ministério da Educação (MEC)"


async def test_usa_o_cache_entre_chamadas(fake_client):
    _route(fake_client)
    cache = TTLCache()
    await get_entity_network(FOCUS, fake_client, depth=2, cache=cache)
    first = len(fake_client.calls("RelatedEntities"))
    await get_entity_network(FOCUS, fake_client, depth=2, cache=cache)
    assert len(fake_client.calls("RelatedEntities")) == first


# ── depth=2 ─────────────────────────────────────────────────────────────────


async def test_depth2_expande_so_os_5_vizinhos_mais_fortes(fake_client):
    _route(fake_client)
    await get_entity_network(FOCUS, fake_client, depth=2)
    calls = fake_client.calls("RelatedEntities")
    assert calls[0] == {"id": FOCUS, "limit": 50}
    assert sorted(c["id"] for c in calls[1:]) == sorted(
        r["canonicalId"] for r in (MEC, ENEM, INEP, ESCOLA, CAMILO)
    )
    assert all(c["limit"] == 25 for c in calls[1:])  # top 25 de cada vizinho


async def test_depth2_expande_no_maximo_os_exibidos(fake_client):
    _route(fake_client)
    await get_entity_network(FOCUS, fake_client, depth=2, max_nodes=2)
    ids = [c["id"] for c in fake_client.calls("RelatedEntities")[1:]]
    assert sorted(ids) == sorted([MEC["canonicalId"], ENEM["canonicalId"]])


async def test_depth2_lista_segundo_grau_sem_foco_genericas_nem_primeiro_grau(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, depth=2)
    via_mec = _line(text, "- via **Ministério da Educação (MEC)** (650):")
    assert "FNDE (1.300" in via_mec
    assert via_mec.index("FNDE") < via_mec.index("Capes") < via_mec.index("Secretaria")
    for excluded in ("Brasil", "Brasília", "Inep", "Pé-de-Meia"):
        assert excluded not in via_mec
    assert len(re.findall(r"`[^`]+`", via_mec)) == 5  # top 5 do segundo grau, com id
    via_enem = _line(text, "- via **Enem** (306):")
    assert "Portal Gov.br" not in via_enem
    assert "Sisu" in via_enem and "Prouni" in via_enem


async def test_depth2_pontes_alcancadas_por_dois_vizinhos(fake_client):
    _route(fake_client)
    text = await get_entity_network(FOCUS, fake_client, depth=2)
    bridges = _line(text, "**Pontes**")
    assert bridges.index("Sisu") < bridges.index("Prouni")  # 3 vizinhos antes de 2
    assert "Sisu (via Ministério da Educação (MEC), Enem, Inep)" in bridges
    assert "Secretaria de Educação Básica (via Ministério da Educação (MEC), " in bridges
    assert "Lula" not in bridges


async def test_depth2_falha_parcial_vira_nota(fake_client):
    def related(v):
        if v["id"] == INEP["canonicalId"]:
            raise RuntimeError("timeout no Inep")
        return _related(v)

    _route(fake_client, related=related)
    text = await get_entity_network(FOCUS, fake_client, depth=2)
    assert "Não foi possível expandir **Inep**" in text
    assert "- via **Ministério da Educação (MEC)** (650):" in text
    assert "- via **Inep**" not in text


async def test_depth2_expansoes_em_paralelo(fake_client):
    started: list[str] = []
    all_started = asyncio.Event()

    async def related(v):
        if v["id"] == FOCUS:
            return _related(v)
        started.append(v["id"])
        if len(started) == 5:
            all_started.set()
        # em série, a primeira expansão esperaria para sempre pelas outras quatro
        await asyncio.wait_for(all_started.wait(), timeout=1.0)
        return _related(v)

    _route(fake_client, related=related)
    text = await get_entity_network(FOCUS, fake_client, depth=2)
    assert "Não foi possível expandir" not in text
    assert len(started) == 5


async def test_depth_fora_da_faixa_e_ajustado(fake_client):
    _route(fake_client)
    await get_entity_network(FOCUS, fake_client, depth=7)
    assert len(fake_client.calls("RelatedEntities")) == 6  # 1 + 5 (depth=2)
