"""gobus_get_policy_lifecycle: série MENSAL (somando agências), pico real, artigos da janela
do pico (filtro de data) e período formatado AAAA-MM."""

from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.tools.get_policy_lifecycle import get_policy_lifecycle

ENTITY = {
    "entitySearch": [
        {
            "entityId": "dgb_pe-de-meia",
            "canonicalName": "Pé-de-Meia",
            "type": "POLICY",
            "description": "Programa de poupança para estudantes",
            "wikidataUrl": None,
            "agencyKey": "mec",
            "aliases": ["Pe-de-Meia"],
            "articleCount": 247,
            "confidence": 0.95,
            "matchType": "exact",
        }
    ]
}


def _point(month, key, name, count):
    return {
        "period": f"{month}-01 00:00:00+00",
        "agencyKey": key,
        "agencyName": name,
        "articleCount": count,
        "totalMentions": count * 2,
        "avgSentimentScore": None,
    }


# O maior ponto isolado é MEC 2023-08 (45), mas o mês de pico é 2024-03 (20+25+15 = 60).
COVERAGE = {
    "entityCoverage": [
        _point("2023-08", "mec", "MEC", 45),
        _point("2023-09", "mec", "MEC", 32),
        _point("2024-03", "mec", "MEC", 20),
        _point("2024-03", "caixa", "CAIXA", 25),
        _point("2024-03", "tvbrasil", "TV Brasil", 15),
        _point("2024-06", "mec", "MEC", 15),
        _point("2026-01", "mec", "MEC", 8),
    ]
}

POLICY = {
    "policyDetails": {
        "domain": "SOCIAL",
        "lifecyclePhase": "ROUTINE",
        "enablingLaws": [],
        "responsibleAgencies": [],
        "targetPopulation": ["estudantes"],
        "firstMentionedDate": "2023-08-01",
    }
}

PEAK_ARTICLES = {
    "articles": {
        "found": 2,
        "articles": [
            {
                "uniqueId": "p1",
                "title": "Pé-de-Meia paga primeira parcela",
                "agencyName": "CAIXA",
                "agency": "caixa",
                "publishedAt": "2024-03-12T10:00:00Z",
                "url": "https://www.gov.br/p1",
            }
        ],
    }
}


def _route(client, *, coverage=COVERAGE, policy=POLICY, peak=PEAK_ARTICLES):
    client.route("EntitySearch", ENTITY)
    client.route("EntityCoverage", coverage)
    client.route("PolicyDetails", policy)
    client.route("PolicyPeakArticles", peak)
    return client


def _table_rows(result):
    return [line for line in result.splitlines() if line.startswith("| 20")]


async def test_agrega_por_mes_somando_agencias(fake_client):
    _route(fake_client)

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    rows = _table_rows(result)
    months = [row.split("|")[1].strip() for row in rows]
    assert len(months) == len(set(months))  # um período por mês, não mês × agência
    assert "| 2024-03 | 60 | ANNOUNCED | CAIXA |" in result
    assert "00:00:00" not in result


async def test_preenche_meses_sem_cobertura(fake_client):
    _route(fake_client)

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    months = [row.split("|")[1].strip() for row in _table_rows(result)]
    assert months[0] == "2023-08" and months[-1] == "2026-01"
    assert "2025-05" in months  # mês sem artigos entra como 0 (ROUTINE)
    assert "| 2025-05 | 0 | ROUTINE |" in result


async def test_fase_atual_e_pico_real(fake_client):
    _route(fake_client)

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    assert "**Fase atual:** ROUTINE" in result
    assert "**Pico:** 2024-03 (60 artigos)" in result


async def test_artigos_vem_da_janela_do_pico(fake_client):
    _route(fake_client)

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    (call,) = fake_client.calls("PolicyPeakArticles")
    assert call["entities"] == ["dgb_pe-de-meia"]
    assert call["startDate"] == "2024-03-01T00:00:00+00:00"
    assert call["endDate"] == "2024-04-01T00:00:00+00:00"
    assert "Pé-de-Meia paga primeira parcela" in result
    assert "2024-03" in result.split("Artigos Representativos")[1]


async def test_sem_artigo_marcado_busca_pelo_nome_na_janela_do_pico(fake_client):
    _route(fake_client, peak={"articles": {"found": 0, "articles": []}})
    fake_client.route(
        "PolicyPeakSearch",
        {
            "search": {
                "found": 1,
                "page": 1,
                "articles": [
                    {
                        "uniqueId": "s1",
                        "title": "Inscrições no Pé-de-Meia",
                        "agencyName": "MEC",
                        "agency": "mec",
                        "publishedAt": "2024-03-02T10:00:00Z",
                        "url": "https://www.gov.br/s1",
                    }
                ],
            }
        },
    )

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    (search,) = fake_client.calls("PolicyPeakSearch")
    assert search["query"] == "Pé-de-Meia"
    assert search["filter"]["startDate"] == "2024-03-01T00:00:00+00:00"
    assert "Inscrições no Pé-de-Meia" in result


async def test_ancoras_por_fase_somam_os_meses(fake_client):
    _route(fake_client)

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    anchors = result.split("Âncoras Narrativos por Fase")[1].split("##")[0]
    assert "**ANNOUNCED:** CAIXA" in anchors
    assert "**IMPLEMENTATION:** MEC" in anchors


async def test_policy_details_opcional(fake_client):
    _route(fake_client, policy=GobusGraphQLError([{"message": "boom"}]))

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    assert "Pé-de-Meia" in result and "GobusGraphQLError" not in result


async def test_politica_nao_encontrada(fake_client):
    fake_client.route("EntitySearch", {"entitySearch": []})

    result = await get_policy_lifecycle("Política Inexistente", fake_client)

    assert "não encontrada" in result.lower()


async def test_sem_cobertura_avisa(fake_client):
    _route(fake_client, coverage={"entityCoverage": []})

    result = await get_policy_lifecycle("Pé-de-Meia", fake_client)

    assert "insuficientes" in result.lower()


async def test_passa_date_from(fake_client):
    _route(fake_client)

    await get_policy_lifecycle("Pé-de-Meia", fake_client, date_from="2023-01-01")

    (call,) = fake_client.calls("EntityCoverage")
    assert call["dateFrom"] == "2023-01-01"
    assert call["granularity"] == "MONTH"
