import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.resources.readability_dashboard import fetch_readability_dashboard


MOCK_ANALYTICS = {
    "agencyAnalytics": [
        {"period": "2026-04-01", "agencyKey": "secom", "agencyName": "Secom", "articleCount": 150, "avgReadabilityFlesch": 17.2, "avgWordCount": 450.0},
        {"period": "2026-04-01", "agencyKey": "cgu", "agencyName": "CGU", "articleCount": 80, "avgReadabilityFlesch": -1.2, "avgWordCount": 620.0},
        {"period": "2026-04-01", "agencyKey": "defesa", "agencyName": "Min. Defesa", "articleCount": 200, "avgReadabilityFlesch": -22.9, "avgWordCount": 800.0},
        {"period": "2026-04-01", "agencyKey": "agencia_brasil", "agencyName": "Agência Brasil", "articleCount": 300, "avgReadabilityFlesch": 33.5, "avgWordCount": 473.0},
    ]
}


class TestReadabilityDashboard:

    async def test_retorna_html_com_doctype(self, fake_client):
        """O output deve ser um documento HTML completo com <!DOCTYPE html>."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await fetch_readability_dashboard(client=fake_client)
        assert "<!DOCTYPE html>" in result or "<!doctype html>" in result.lower()

    async def test_html_contem_canvas_chartjs(self, fake_client):
        """O HTML deve conter um elemento <canvas> para o gráfico Chart.js."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await fetch_readability_dashboard(client=fake_client)
        assert "<canvas" in result
        assert "Chart" in result  # referência à lib Chart.js no código JS inline

    async def test_dados_das_agencias_embutidos_no_html(self, fake_client):
        """Os nomes das agências dos dados mock devem aparecer no HTML gerado."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await fetch_readability_dashboard(client=fake_client)
        assert "Secom" in result
        assert "CGU" in result
        assert "Agência Brasil" in result

    async def test_sem_referencias_externas_http(self, fake_client):
        """O HTML deve ser auto-contido — nenhuma URL https:// externa (CDN, fontes, etc.)."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await fetch_readability_dashboard(client=fake_client)
        # Remove dados embutidos (ex: URLs em JSON island de artigos) antes de checar
        # A checagem é: src=, href= e @import não devem apontar para https://
        import re
        external_refs = re.findall(r'(?:src|href)\s*=\s*["\']https?://', result)
        assert external_refs == [], f"Referências externas encontradas: {external_refs}"

    async def test_html_contem_dados_json_island(self, fake_client):
        """O HTML deve conter um JSON island com o campo avgReadabilityFlesch."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await fetch_readability_dashboard(client=fake_client)
        assert "avgReadabilityFlesch" in result

    async def test_retorna_string_nao_vazia(self, fake_client):
        """O retorno deve ser uma string não vazia."""
        fake_client.set_response(MOCK_ANALYTICS)
        result = await fetch_readability_dashboard(client=fake_client)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
