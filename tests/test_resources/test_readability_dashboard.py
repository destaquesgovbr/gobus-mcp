from datetime import date

from gobus_mcp.resources.readability_dashboard import fetch_readability_dashboard
from tests.conftest import route_catalog

TODAY = date(2026, 10, 5)

MOCK_ANALYTICS = {
    "agencyAnalytics": [
        {
            "period": "2026-10-01 00:00:00+00",
            "agencyKey": "secom",
            "agencyName": "Secom",
            "articleCount": 150,
            "avgReadabilityFlesch": 17.2,
            "avgWordCount": 450.0,
        },
        {
            "period": "2026-10-01 00:00:00+00",
            "agencyKey": "cgu",
            "agencyName": "CGU",
            "articleCount": 80,
            "avgReadabilityFlesch": -1.2,
            "avgWordCount": 620.0,
        },
        {
            "period": "2026-10-01 00:00:00+00",
            "agencyKey": "defesa",
            "agencyName": "Min. Defesa",
            "articleCount": 200,
            "avgReadabilityFlesch": -22.9,
            "avgWordCount": 800.0,
        },
        {
            "period": "2026-10-01 00:00:00+00",
            "agencyKey": "agencia_brasil",
            "agencyName": "Agência Brasil",
            "articleCount": 300,
            "avgReadabilityFlesch": 33.5,
            "avgWordCount": 473.0,
        },
    ]
}


def _route(client, rows=None, *, agencies=None):
    rows = MOCK_ANALYTICS["agencyAnalytics"] if rows is None else rows
    route_catalog(client, agencies)
    client.route(
        "ReadabilityWindow",
        lambda v: {"agencyAnalytics": [r for r in rows if r["agencyKey"] in v["agencies"]]},
    )
    return client


class TestReadabilityDashboard:
    async def test_retorna_html_com_doctype(self, fake_client):
        """O output deve ser um documento HTML completo com <!DOCTYPE html>."""
        _route(fake_client)
        result = await fetch_readability_dashboard(client=fake_client, today=TODAY)
        assert "<!DOCTYPE html>" in result or "<!doctype html>" in result.lower()

    async def test_html_contem_canvas_chartjs(self, fake_client):
        """O HTML deve conter um elemento <canvas> para o gráfico Chart.js."""
        _route(fake_client)
        result = await fetch_readability_dashboard(client=fake_client, today=TODAY)
        assert "<canvas" in result
        assert "Chart" in result  # referência à lib Chart.js no código JS inline

    async def test_dados_das_agencias_embutidos_no_html(self, fake_client):
        """Os nomes das agências dos dados mock devem aparecer no HTML gerado."""
        _route(fake_client)
        result = await fetch_readability_dashboard(client=fake_client, today=TODAY)
        assert "Secretaria de Comunicação Social" in result  # nomes do catálogo
        assert "Controladoria-Geral da União" in result
        assert "Agência Brasil" in result

    async def test_sem_referencias_externas_http(self, fake_client):
        """O HTML deve ser auto-contido — nenhuma URL https:// externa (CDN, fontes, etc.)."""
        _route(fake_client)
        result = await fetch_readability_dashboard(client=fake_client, today=TODAY)
        # Remove dados embutidos (ex: URLs em JSON island de artigos) antes de checar
        # A checagem é: src=, href= e @import não devem apontar para https://
        import re

        external_refs = re.findall(r'(?:src|href)\s*=\s*["\']https?://', result)
        assert external_refs == [], f"Referências externas encontradas: {external_refs}"

    async def test_html_contem_dados_json_island(self, fake_client):
        """O HTML deve conter um JSON island com o campo avgReadabilityFlesch."""
        _route(fake_client)
        result = await fetch_readability_dashboard(client=fake_client, today=TODAY)
        assert "avgReadabilityFlesch" in result

    async def test_retorna_string_nao_vazia(self, fake_client):
        """O retorno deve ser uma string não vazia."""
        _route(fake_client)
        result = await fetch_readability_dashboard(client=fake_client, today=TODAY)
        assert isinstance(result, str)
        assert len(result.strip()) > 0


async def test_dashboard_usa_agencias_ativas_do_catalogo(fake_client):
    _route(fake_client)
    await fetch_readability_dashboard(client=fake_client, today=TODAY)
    first = fake_client.calls("ReadabilityWindow")[0]
    assert "cgcom" not in first["agencies"] and "saude" in first["agencies"]


async def test_dashboard_nulo_nao_vira_zero(fake_client):
    rows = [*MOCK_ANALYTICS["agencyAnalytics"]]
    rows.append(
        {
            "period": "2026-10-01 00:00:00+00",
            "agencyKey": "mec",
            "agencyName": "MEC",
            "articleCount": 120,
            "avgReadabilityFlesch": None,
            "avgWordCount": None,
        }
    )
    _route(fake_client, rows)

    result = await fetch_readability_dashboard(client=fake_client, today=TODAY)

    mec_row = next(line for line in result.splitlines() if "Ministério da Educação</td>" in line)
    assert "—" in mec_row and "0.0" not in mec_row


async def test_dashboard_escapa_nomes_e_json(fake_client):
    evil = "</script><script>alert(1)</script>"
    _route(
        fake_client,
        [
            {
                "period": "2026-10-01 00:00:00+00",
                "agencyKey": "xss",
                "agencyName": evil,
                "articleCount": 10,
                "avgReadabilityFlesch": 20.0,
                "avgWordCount": 300.0,
            }
        ],
        agencies=[("xss", False, evil), ("agencia_brasil", True, "Agência Brasil")],
    )

    result = await fetch_readability_dashboard(client=fake_client, today=TODAY)

    assert evil not in result
    assert "&lt;/script&gt;" in result
