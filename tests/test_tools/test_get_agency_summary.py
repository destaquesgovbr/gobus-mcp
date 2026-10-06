"""gobus_get_agency_summary: null≠0, faixa única de Flesch, nomes do catálogo, validação da
agência, limiar convertido no trendingThemes e aviso de temas indisponíveis."""

from datetime import date

import pytest

from gobus_mcp.tools.get_agency_summary import _TRENDS_QUERY, get_agency_summary
from tests.conftest import route_catalog

TODAY = date(2026, 10, 5)


def _row(period="2026-09-01 00:00:00+00", count=42, flesch=55.0, sentiment=0.12, pct=0.3):
    return {
        "period": period,
        "agencyKey": "saude",
        "agencyName": "MS",
        "articleCount": count,
        "avgSentimentScore": sentiment,
        "pctPositive": pct,
        "avgReadabilityFlesch": flesch,
    }


THEME = {
    "themeLabel": "Vacinação",
    "growthScore": 2.0,
    "windowCount": 42,
    "baselineDailyAvg": 3.0,
    "topArticles": [
        {"uniqueId": "a1", "title": "Novo imunizante aprovado", "publishedAt": "2026-10-01"},
    ],
}


def _route(client, rows, themes, *, classified=900, total=1000):
    route_catalog(client)
    client.route("AgencySummaryAnalytics", {"agencyAnalytics": rows})
    client.route("AgencySummaryTrends", {"trendingThemes": themes})
    client.route(
        "ThemeCoverage",
        {
            "topThemes": [{"label": "Saúde", "count": classified}] if classified else [],
            "analyticsKpis": {"total": total},
        },
    )
    return client


async def _summary(client, key="saude", **kwargs):
    return await get_agency_summary(key, client, today=TODAY, **kwargs)


async def test_combina_analytics_e_temas_com_nome_do_catalogo(fake_client):
    _route(fake_client, [_row()], [THEME])

    result = await _summary(fake_client)

    assert "Ministério da Saúde" in result
    assert "42 artigos" in result
    assert "55.0 (médio)" in result
    assert "Vacinação" in result and "Novo imunizante aprovado" in result
    theme_line = next(line for line in result.splitlines() if "Vacinação" in line)
    assert "3.0×" in theme_line  # razão sem sobreposição


async def test_janela_fechada_e_limiar_convertido(fake_client):
    _route(fake_client, [_row()], [THEME])

    await _summary(fake_client, days=30)

    (analytics,) = fake_client.calls("AgencySummaryAnalytics")
    assert analytics["agencies"] == ["saude"]
    # MONTH: dateTo exclusivo na API → D (05/10) para cobrir D−1 inteiro
    assert (analytics["dateFrom"], analytics["dateTo"]) == ("2026-09-05", "2026-10-05")
    assert "baselineDailyAvg" in _TRENDS_QUERY
    (trends,) = fake_client.calls("AgencySummaryTrends")
    assert trends["agencyKey"] == "saude"
    assert trends["growthThreshold"] == pytest.approx(1.3333, abs=1e-4)


async def test_flesch_media_ponderada_ignora_nulo(fake_client):
    rows = [
        _row(count=30, flesch=40.0),
        _row(period="2026-10-01 00:00:00+00", count=10, flesch=None),
    ]
    _route(fake_client, rows, [THEME])

    result = await _summary(fake_client)

    assert "40.0 (difícil)" in result
    assert "30 de 40 artigos com Flesch" in result


async def test_flesch_e_sentimento_nulos_ficam_indisponiveis(fake_client):
    _route(fake_client, [_row(flesch=None, sentiment=None, pct=0.0)], [THEME])

    result = await _summary(fake_client)

    assert "**Legibilidade:** indisponível" in result
    assert "**Sentimento:** indisponível" in result
    assert "0.0" not in result
    assert "0% positivos" not in result  # o 0.0 do pctPositive sem dado é artefato


async def test_sem_temas_com_cobertura_baixa_avisa(fake_client):
    _route(fake_client, [_row()], [], classified=0, total=930)

    result = await _summary(fake_client)

    assert "Temas: indisponível" in result
    assert "26/09/2026" in result


async def test_agencia_invalida_sugere_sem_consultar(fake_client):
    _route(fake_client, [], [])

    result = await _summary(fake_client, key="trabalho")

    assert "trabalho-e-emprego" in result
    assert fake_client.calls("AgencySummaryAnalytics") == []


async def test_sem_dados_retorna_mensagem(fake_client):
    _route(fake_client, [], [])

    result = await _summary(fake_client, key="mec")

    assert "Sem dados" in result
    assert "Ministério da Educação" in result
