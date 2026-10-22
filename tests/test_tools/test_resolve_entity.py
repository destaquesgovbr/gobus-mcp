import pytest

from gobus_mcp.tools.resolve_entity import resolve_entity
from tests.conftest import FakeGraphQLClient


class TestResolveEntity:
    @pytest.mark.asyncio
    async def test_retorna_entidade_encontrada(self):
        client = FakeGraphQLClient()
        client.set_response(
            {
                "entitySearch": [
                    {
                        "entityId": "Q4294522",
                        "canonicalName": "Ministério da Educação",
                        "type": "ORG",
                        "description": "Ministério federal",
                        "wikidataUrl": "https://www.wikidata.org/wiki/Q4294522",
                        "agencyKey": "mec",
                        "aliases": ["MEC"],
                        "articleCount": 1223,
                        "confidence": 1.0,
                        "matchType": "alias_exact",
                    }
                ]
            }
        )
        result = await resolve_entity("MEC", client)
        assert "Q4294522" in result
        assert "Ministério da Educação" in result
        assert "1.00" in result

    @pytest.mark.asyncio
    async def test_sem_resultado_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": []})
        result = await resolve_entity("xyz_inexistente", client)
        assert "Nenhuma" in result

    @pytest.mark.asyncio
    async def test_passa_entity_type_nas_variaveis(self):
        client = FakeGraphQLClient()
        client.set_response({"entitySearch": []})
        await resolve_entity("MEC", client, entity_type="ORG")
        call_args = client.execute.call_args
        variables = call_args[0][1]
        assert variables["entityType"] == "ORG"


# ── dedup por entityId: o entitySearch une alias_exact e trgm_fuzzy e repete o id ──
# (em 21/10: "Enem" volta Q5419278 3× em alias_exact; "Camilo Santana", Q18242106 em
# alias_exact e em trgm_fuzzy)


def _hit(entity_id: str, name: str, confidence: float, match: str = "alias_exact") -> dict:
    return {
        "entityId": entity_id,
        "canonicalName": name,
        "type": "EVENT",
        "description": None,
        "wikidataUrl": None,
        "agencyKey": None,
        "aliases": [],
        "articleCount": 10,
        "confidence": confidence,
        "matchType": match,
    }


async def test_deduplica_por_entity_id_e_mantem_o_de_maior_confianca():
    client = FakeGraphQLClient()
    client.set_response(
        {
            "entitySearch": [
                _hit("Q5419278", "Exame Nacional do Ensino Médio (Enem)", 1.0),
                _hit("Q5419278", "Exame Nacional do Ensino Médio (Enem)", 1.0),
                _hit("Q18242106", "Camilo Sobreira de Santana", 0.58, "trgm_fuzzy"),
                _hit("Q18242106", "Camilo Sobreira de Santana", 1.0),
                _hit("Q5419278", "Exame Nacional do Ensino Médio (Enem)", 1.0),
                _hit("dgb_enem-2026", "Enem 2026", 0.41, "trgm_fuzzy"),
            ]
        }
    )

    result = await resolve_entity("Enem", client)

    assert result.count("`Q5419278`") == 1
    assert result.count("`Q18242106`") == 1
    assert "`dgb_enem-2026`" in result
    assert "1.00 (alias_exact)" in result.split("Camilo")[1].split("##")[0]
    assert result.index("Q5419278") < result.index("Q18242106") < result.index("dgb_enem-2026")


async def test_pede_folga_a_api_e_corta_no_limit_depois_do_dedup():
    client = FakeGraphQLClient()
    client.set_response(
        {
            "entitySearch": [
                _hit("Q1", "Um", 1.0),
                _hit("Q1", "Um", 1.0),
                _hit("Q2", "Dois", 0.9),
                _hit("Q3", "Três", 0.8),
            ]
        }
    )

    result = await resolve_entity("x", client, limit=2)

    variables = client.execute.call_args[0][1]
    assert variables["limit"] > 2  # duplicatas não roubam as vagas
    assert "`Q1`" in result and "`Q2`" in result
    assert "`Q3`" not in result


@pytest.mark.parametrize(("limit", "asked"), [(5, 15), (10, 20), (20, 20)])
async def test_folga_respeita_o_teto_de_20_do_entity_search(limit, asked):
    client = FakeGraphQLClient()
    client.set_response({"entitySearch": []})

    await resolve_entity("x", client, limit=limit)

    assert client.execute.call_args[0][1]["limit"] == asked
