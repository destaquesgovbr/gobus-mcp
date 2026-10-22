import pytest

from gobus_mcp.tools.get_article import get_article
from tests.conftest import FakeGraphQLClient, route_catalog


class TestGetArticle:
    @pytest.mark.asyncio
    async def test_retorna_artigo_completo(self):
        client = FakeGraphQLClient()
        client.set_response(
            {
                "article": {
                    "uniqueId": "abc123",
                    "title": "Título do Artigo",
                    "content": "Conteúdo completo do artigo.",
                    "summary": "Resumo.",
                    "agencyName": "MEC",
                    "publishedAt": "2024-06-01T10:00:00Z",
                    "url": "https://gov.br/abc",
                    "tags": ["educação", "governo"],
                    "features": {
                        "viewCount": 1500,
                        "uniqueSessions": 900,
                        "trendingScore": 2.1,
                        "wordCount": 400,
                        "readabilityFlesch": 61.0,
                        "readabilityFleschPtbr": 65.0,
                        "entities": [
                            {"text": "MEC", "type": "ORG", "count": 3, "canonicalId": "Q4294522"}
                        ],
                    },
                }
            }
        )
        result = await get_article("abc123", client)
        assert "Título do Artigo" in result
        assert "Conteúdo completo" in result
        assert "MEC" in result
        assert "Legibilidade (Flesch pt-BR): 65.0 (fácil)" in result
        assert "Instituições" in result

    @pytest.mark.asyncio
    async def test_artigo_nao_encontrado(self):
        client = FakeGraphQLClient()
        client.set_response({"article": None})
        result = await get_article("inexistente", client)
        assert "não encontrado" in result.lower()


@pytest.mark.asyncio
async def test_exibe_agency_code():
    """O código de agência (ex: 'saude') deve aparecer no artigo."""
    client = FakeGraphQLClient()
    client.set_response(
        {
            "article": {
                "uniqueId": "x1",
                "title": "Artigo Teste",
                "content": "Conteúdo do artigo.",
                "summary": "Resumo.",
                "agencyName": "Ministério da Saúde",
                "agency": "saude",
                "publishedAt": "2026-01-01T00:00:00Z",
                "url": "https://gov.br/saude/artigo",
                "tags": [],
                "features": {},
            }
        }
    )
    result = await get_article("x1", client)
    assert "[saude]" in result


# ── null ≠ 0, Flesch pt-BR nas faixas de Martins e nome do catálogo ─────────


def _art(features, agency="pf", agency_name="pf"):
    return {
        "article": {
            "uniqueId": "x1",
            "title": "Artigo",
            "content": "Corpo.",
            "summary": None,
            "agencyName": agency_name,
            "agency": agency,
            "publishedAt": "2026-06-01T10:00:00Z",
            "url": "https://www.gov.br/x1",
            "tags": [],
            "features": features,
        }
    }


@pytest.mark.parametrize(
    ("flesch", "expected"),
    [
        (0.0, "0.0 (muito difícil)"),
        (-12.3, "0.0 (muito difícil; valor bruto -12.3)"),
        (65.0, "65.0 (fácil)"),
        (72.5, "72.5 (fácil)"),
        (80.0, "80.0 (muito fácil)"),
    ],
)
async def test_flesch_ptbr_zero_e_negativo_nas_faixas_de_martins(fake_client, flesch, expected):
    route_catalog(fake_client)
    fake_client.route(
        "GetArticle",
        _art({"readabilityFleschPtbr": flesch, "readabilityFlesch": 1.0, "wordCount": 400}),
    )

    result = await get_article("x1", fake_client)

    assert expected in result


async def test_flesch_e_word_count_nulos_aparecem_como_indisponiveis(fake_client):
    route_catalog(fake_client)
    fake_client.route(
        "GetArticle",
        _art({"readabilityFleschPtbr": None, "readabilityFlesch": None, "wordCount": None}),
    )

    result = await get_article("x1", fake_client)

    assert "Legibilidade: indisponível" in result
    assert "0.0" not in result


async def test_sem_ptbr_mostra_o_ingles_identificado(fake_client):
    route_catalog(fake_client)
    fake_client.route(
        "GetArticle",
        _art({"readabilityFleschPtbr": None, "readabilityFlesch": 30.0, "wordCount": 400}),
    )

    result = await get_article("x1", fake_client)

    assert "Legibilidade (Flesch inglês, legado): 30.0 (difícil)" in result


async def test_api_sem_ptbr_usa_a_query_antiga(fake_client):
    from gobus_mcp.client import GobusGraphQLError

    route_catalog(fake_client)
    fake_client.route(
        "GetArticle",
        GobusGraphQLError(
            [{"message": "Cannot query field 'readabilityFleschPtbr' on type 'ArticleFeatures'."}]
        ),
    )
    fake_client.route("GetArticleLegacy", _art({"readabilityFlesch": 30.0, "wordCount": 400}))

    result = await get_article("x1", fake_client)

    assert "30.0 (difícil)" in result
    assert fake_client.calls("GetArticleLegacy") == [{"uniqueId": "x1"}]


async def test_nome_da_agencia_vem_do_catalogo(fake_client):
    route_catalog(fake_client)
    fake_client.route("GetArticle", _art({}))

    result = await get_article("x1", fake_client)

    assert "[pf] Polícia Federal" in result
    assert "[pf] pf" not in result


async def test_titulo_vira_link_markdown(fake_client):
    route_catalog(fake_client)
    fake_client.route("GetArticle", _art({"viewCount": 1500}))

    result = await get_article("x1", fake_client)

    assert result.startswith("# [Artigo](https://www.gov.br/x1)\n")
    assert "🔗" not in result
    assert "1.500 visualizações" in result


async def test_data_exibida_e_o_dia_de_brasilia(fake_client):
    route_catalog(fake_client)
    art = _art({})
    art["article"]["publishedAt"] = "2026-10-21T02:30:00+00:00"  # 23:30 de 20/10 em Brasília
    fake_client.route("GetArticle", art)

    result = await get_article("x1", fake_client)

    assert "· 2026-10-20" in result
