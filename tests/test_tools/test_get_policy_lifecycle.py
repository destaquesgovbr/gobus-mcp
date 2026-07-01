import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.tools.get_policy_lifecycle import get_policy_lifecycle


MOCK_ENTITY_SEARCH = {
    "entitySearch": [{
        "entityId": "dgb_pe-de-meia",
        "canonicalName": "Pé-de-Meia",
        "type": "POLICY",
        "description": "Programa de poupança para estudantes",
        "wikidataUrl": None,
        "agencyKey": "mec",
        "aliases": ["Pe-de-Meia", "Poupança do Jovem"],
        "articleCount": 247,
        "confidence": 0.95,
        "matchType": "exact",
    }]
}

MOCK_COVERAGE = {
    "entityCoverage": [
        {"period": "2023-08-01", "agencyKey": "mec", "agencyName": "MEC", "articleCount": 45, "totalMentions": 89, "avgSentimentScore": 0.0},
        {"period": "2023-09-01", "agencyKey": "mec", "agencyName": "MEC", "articleCount": 32, "totalMentions": 60, "avgSentimentScore": 0.0},
        {"period": "2024-01-01", "agencyKey": "caixa", "agencyName": "CAIXA", "articleCount": 28, "totalMentions": 55, "avgSentimentScore": 0.0},
        {"period": "2024-06-01", "agencyKey": "mec", "agencyName": "MEC", "articleCount": 15, "totalMentions": 30, "avgSentimentScore": 0.0},
        {"period": "2026-01-01", "agencyKey": "mec", "agencyName": "MEC", "articleCount": 8, "totalMentions": 16, "avgSentimentScore": 0.0},
    ]
}

MOCK_SEARCH_RESULT = {
    "search": {
        "articles": [
            {
                "uniqueId": "art-1",
                "title": "Pé-de-Meia: inscrições abertas",
                "agencyName": "MEC",
                "agency": "mec",
                "publishedAt": "2023-08-15",
                "summary": "Programa anuncia abertura de inscrições...",
                "url": "https://gov.br/1",
                "features": {"trendingScore": None, "viewCount": None},
            },
        ],
        "found": 1,
        "page": 1,
    }
}

MOCK_POLICY_DETAILS = {
    "policyDetails": {
        "domain": "SOCIAL",
        "lifecyclePhase": "ROUTINE",
        "enablingLaws": [],
        "responsibleAgencies": ["mec", "caixa"],
        "targetPopulation": ["estudantes", "ensino-medio"],
        "firstMentionedDate": "2023-08-01",
    }
}


class TestGetPolicyLifecycle:

    async def test_retorna_fases_com_volumes(self, fake_client):
        """Deve retornar fases identificadas com seus volumes de artigos."""
        fake_client.set_responses([MOCK_ENTITY_SEARCH, MOCK_COVERAGE, MOCK_POLICY_DETAILS, MOCK_SEARCH_RESULT])
        result = await get_policy_lifecycle("Pé-de-Meia", fake_client)
        # Deve mencionar a fase de anúncio/lançamento (pico em 45 artigos)
        assert "ANNOUNCED" in result or "LANÇAMENTO" in result or "Lançamento" in result
        # Deve mencionar o volume de artigos
        assert "45" in result
        # Deve mencionar fase de rotina (queda)
        assert "ROUTINE" in result or "ROTINA" in result or "Rotina" in result

    async def test_fase_atual_identificada_por_volume_recente(self, fake_client):
        """O período mais recente (8 artigos em 2026) deve ser identificado como fase de declínio/rotina."""
        fake_client.set_responses([MOCK_ENTITY_SEARCH, MOCK_COVERAGE, MOCK_POLICY_DETAILS, MOCK_SEARCH_RESULT])
        result = await get_policy_lifecycle("Pé-de-Meia", fake_client)
        # Fase atual = ROUTINE (volume 8 << 45 de pico)
        assert "ROUTINE" in result or "ROTINA" in result or "Rotina" in result
        # Fase atual deve aparecer destacada
        assert "atual" in result.lower() or "Atual" in result

    async def test_policy_nao_encontrada_retorna_mensagem_de_erro(self, fake_client):
        """Política inexistente deve retornar mensagem clara de erro."""
        fake_client.set_response({"entitySearch": []})
        result = await get_policy_lifecycle("Política Inexistente", fake_client)
        assert "não encontrada" in result.lower() or "Política Inexistente" in result

    async def test_policy_sem_cobertura_avisa_dados_insuficientes(self, fake_client):
        """Política sem dados de cobertura deve retornar aviso de dados insuficientes."""
        fake_client.set_responses([MOCK_ENTITY_SEARCH, {"entityCoverage": []}])
        result = await get_policy_lifecycle("Pé-de-Meia", fake_client)
        assert (
            "insuficientes" in result.lower()
            or "sem dados" in result.lower()
            or "dados" in result.lower()
        )

    async def test_retorna_markdown_com_secoes(self, fake_client):
        """O retorno deve ser Markdown com ao menos um cabeçalho e seções de fases e perspectiva."""
        fake_client.set_responses([MOCK_ENTITY_SEARCH, MOCK_COVERAGE, MOCK_POLICY_DETAILS, MOCK_SEARCH_RESULT])
        result = await get_policy_lifecycle("Pé-de-Meia", fake_client)
        assert isinstance(result, str)
        assert len(result.strip()) > 50
        # Deve ter cabeçalho principal
        assert "# " in result
        # Deve ter seção de fases
        assert "Fases" in result or "fases" in result
        # Deve ter seção de perspectiva ou fase atual
        assert "Perspectiva" in result or "perspectiva" in result or "atual" in result.lower()

    async def test_policy_details_opcional_quando_ausente(self, fake_client):
        """Quando policyDetails falha (query inexistente na API), o tool deve continuar sem ela."""
        fake_client.set_responses([
            MOCK_ENTITY_SEARCH,
            MOCK_COVERAGE,
            GobusGraphQLError([{"message": "policyDetails query not found"}]),
            MOCK_SEARCH_RESULT,
        ])
        result = await get_policy_lifecycle("Pé-de-Meia", fake_client)
        # Deve retornar markdown válido mesmo sem policyDetails
        assert "Pé-de-Meia" in result
        assert "#" in result
        # Não deve propagar a exceção — foi capturada gracefully
        assert "GobusGraphQLError" not in result

    async def test_ancoras_narrativos_identificados(self, fake_client):
        """Deve identificar e exibir as agências dominantes por fase (âncoras narrativos)."""
        fake_client.set_responses([MOCK_ENTITY_SEARCH, MOCK_COVERAGE, MOCK_POLICY_DETAILS, MOCK_SEARCH_RESULT])
        result = await get_policy_lifecycle("Pé-de-Meia", fake_client)
        # MEC é dominante em ANNOUNCED e ROUTINE
        assert "MEC" in result
        # Deve ter seção sobre âncoras/agências por fase
        assert (
            "Âncoras" in result
            or "âncoras" in result
            or "Agência" in result
            or "agência" in result.lower()
        )
