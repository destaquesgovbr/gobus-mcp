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
                        "readabilityFlesch": 65.0,
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
        assert "fácil" in result.lower() or "médio" in result.lower()
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


# ── null ≠ 0, faixa única de Flesch e nome do catálogo ──────────────────────


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
        (65.0, "65.0 (médio)"),
        (72.5, "72.5 (médio)"),
        (80.0, "80.0 (fácil)"),
    ],
)
async def test_flesch_zero_e_negativo_aparecem_na_faixa_unica(fake_client, flesch, expected):
    route_catalog(fake_client)
    fake_client.route("GetArticle", _art({"readabilityFlesch": flesch, "wordCount": 400}))

    result = await get_article("x1", fake_client)

    assert expected in result


async def test_flesch_e_word_count_nulos_aparecem_como_indisponiveis(fake_client):
    route_catalog(fake_client)
    fake_client.route("GetArticle", _art({"readabilityFlesch": None, "wordCount": None}))

    result = await get_article("x1", fake_client)

    assert "Legibilidade: indisponível" in result
    assert "0.0" not in result


async def test_nome_da_agencia_vem_do_catalogo(fake_client):
    route_catalog(fake_client)
    fake_client.route("GetArticle", _art({}))

    result = await get_article("x1", fake_client)

    assert "[pf] Polícia Federal" in result
    assert "[pf] pf" not in result
