"""gobus://health/pipelines: só data_status (themes, readability, sentiment_analytics,
entity_ranking), com detecção dinâmica, null nunca contado como dado e pctPositive como
fração 0..1."""

import json
from datetime import datetime

from gobus_mcp.calendario import BRT
from gobus_mcp.resources.health_pipelines import fetch_health_pipelines
from tests.conftest import route_catalog

NOW = datetime(2026, 10, 5, 19, 0, tzinfo=BRT)  # 22:00 UTC


def _analytics(flesch=40.0, sentiment=0.1, pct=0.3):
    return {
        "agencyAnalytics": [
            {
                "agencyKey": key,
                "articleCount": 100,
                "avgSentimentScore": sentiment,
                "pctPositive": pct,
                "avgReadabilityFlesch": flesch
                if key != "saude"
                else (-5.0 if flesch is not None else None),
            }
            for key in ("agencia_brasil", "saude", "mec")
        ]
    }


def _ranking(rows):
    return {"trendingEntities": rows}


FRESH = [
    {
        "entityId": f"Q{i}",
        "volumeRatio": 3.0,
        "windowCount": 10,
        "computedAt": "2026-10-05 21:00:00+00",
    }
    for i in range(5)
]

LEGACY = [
    {
        "entityId": "Q1",
        "volumeRatio": 8571.4,
        "windowCount": 60,
        "computedAt": "2026-07-03 21:00:00+00",
    },
    {
        "entityId": "Q2",
        "volumeRatio": 857.1,
        "windowCount": 6,
        "computedAt": "2026-10-05 21:00:00+00",
    },
]


def _route(client, *, analytics=None, ranking=None, classified=900, total=1000):
    route_catalog(client)
    client.route("HealthAnalytics", _analytics() if analytics is None else analytics)
    client.route("HealthTrendingEntities", _ranking(FRESH if ranking is None else ranking))
    client.route(
        "ThemeCoverage",
        {
            "topThemes": [{"label": "Saúde", "count": classified}] if classified else [],
            "analyticsKpis": {"total": total},
        },
    )
    return client


async def _health(client):
    return json.loads(await fetch_health_pipelines(client, now=NOW))


async def test_formato_com_as_quatro_chaves_e_schema_2(fake_client):
    _route(fake_client)

    data = await _health(fake_client)

    assert data["schemaVersion"] == 2
    assert data["referenceDate"] == "2026-10-05"
    assert data["calendar"]["phase"] == "blackout"
    assert set(data["pipelines"]) == {
        "themes",
        "readability",
        "sentiment_analytics",
        "entity_ranking",
    }
    assert data["status"] == "ok"
    assert data["notices"] == []
    for item in data["pipelines"].values():
        assert set(item) >= {"key", "status", "since", "message", "metric"}


async def test_flesch_todo_nulo_e_indisponivel(fake_client):
    _route(fake_client, analytics=_analytics(flesch=None))

    data = await _health(fake_client)

    readability = data["pipelines"]["readability"]
    assert readability["status"] == "unavailable"
    assert readability["since"] == "2026-06-30"
    assert any(n["code"] == "READABILITY_UNAVAILABLE" for n in data["notices"])
    assert data["status"] == "unavailable"


async def test_flesch_negativo_e_dado_nao_falha(fake_client):
    _route(fake_client)  # uma agência com Flesch -5.0

    data = await _health(fake_client)

    assert data["pipelines"]["readability"]["status"] == "ok"


async def test_sentimento_sem_score_e_indisponivel_mesmo_com_pct_zero(fake_client):
    _route(fake_client, analytics=_analytics(sentiment=None, pct=0.0))

    data = await _health(fake_client)

    sentiment = data["pipelines"]["sentiment_analytics"]
    assert sentiment["status"] == "unavailable"
    assert any(n["code"] == "SENTIMENT_UNAVAILABLE" for n in data["notices"])


async def test_sentimento_ok_com_pct_positive_em_fracao(fake_client):
    _route(fake_client, analytics=_analytics(sentiment=0.1, pct=0.3))

    data = await _health(fake_client)

    sentiment = data["pipelines"]["sentiment_analytics"]
    assert sentiment["status"] == "ok"
    assert sentiment["metric"]["pctPositive"] == 0.3  # fração 0..1, não percentual


async def test_temas_sem_classificacao_indisponiveis(fake_client):
    _route(fake_client, classified=0, total=930)

    data = await _health(fake_client)

    themes = data["pipelines"]["themes"]
    assert themes["status"] == "unavailable"
    assert themes["since"] == "2026-09-26"
    assert fake_client.calls("ThemeCoverage") == [{"days": 7}]


async def test_ranking_com_linhas_legadas_e_execucoes_misturadas_degradado(fake_client):
    _route(fake_client, ranking=LEGACY)

    data = await _health(fake_client)

    ranking = data["pipelines"]["entity_ranking"]
    assert ranking["status"] == "degraded"
    assert ranking["metric"]["rowsLegacyFloor"] == 2
    assert ranking["metric"]["distinctRuns"] == 2


async def test_ranking_execucao_unica_recente_ok(fake_client):
    _route(fake_client, ranking=FRESH)

    data = await _health(fake_client)

    assert data["pipelines"]["entity_ranking"]["status"] == "ok"


async def test_analytics_das_agencias_ativas_nos_ultimos_7_dias_fechados(fake_client):
    _route(fake_client)

    await _health(fake_client)

    (call,) = fake_client.calls("HealthAnalytics")
    assert call["agencies"] == ["agencia_brasil", "saude", "mec", "secom", "cgu"]
    assert (call["dateFrom"], call["dateTo"]) == ("2026-09-28", "2026-10-04")


async def test_falha_de_uma_consulta_nao_derruba_as_outras(fake_client):
    _route(fake_client)
    fake_client.route("HealthTrendingEntities", RuntimeError("timeout"))

    data = await _health(fake_client)

    assert data["pipelines"]["entity_ranking"]["status"] == "unavailable"
    assert "timeout" in data["pipelines"]["entity_ranking"]["message"]
    assert data["pipelines"]["themes"]["status"] == "ok"
