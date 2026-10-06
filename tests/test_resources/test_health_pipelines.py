"""gobus://health/pipelines: data_status (themes, readability, sentiment_analytics,
entity_ranking, indexing_lag, agency_activity), com detecção dinâmica, null nunca contado
como dado e pctPositive como fração 0..1."""

import json
from datetime import date, datetime

from gobus_mcp.calendario import BRT
from gobus_mcp.resources.health_pipelines import fetch_health_pipelines
from tests.conftest import CATALOG_AGENCIES, route_catalog
from tests.fixtures.g2 import activity_route, busy

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


def _indexing(*, day: int = 150, two_days: int = 300, stored: dict[str, int] | None = None):
    """Resposta ``HealthIndexingLag``: Typesense (``found``) no dia D e em D−1..D, e o
    ``agencyAnalytics`` DAY (Postgres) por dia, com uma linha duplicada (dedup)."""
    stored = {"2026-10-04": 150, "2026-10-05": 150} if stored is None else stored
    rows = []
    for period, n in stored.items():
        rows += [
            {"period": period, "agencyKey": "saude", "articleCount": n - 10},
            {"period": period, "agencyKey": "mec", "articleCount": 10},
            {"period": period, "agencyKey": "mec", "articleCount": 10},  # duplicada
        ]
    return {"day": {"found": day}, "twoDays": {"found": two_days}, "agencyAnalytics": rows}


def silent_since_blackout(day: date) -> int:
    return busy(day) if day < date(2026, 7, 4) else 0


def resumed_on_26_10(day: date) -> int:
    return busy(day) if day < date(2026, 7, 4) or day >= date(2026, 10, 26) else 0


def _route(
    client,
    *,
    analytics=None,
    ranking=None,
    classified=900,
    total=1000,
    indexing=None,
    activity=None,
):
    route_catalog(client)
    client.route("HealthIndexingLag", _indexing() if indexing is None else indexing)
    client.route(
        "AgencyActivitySnapshot",
        activity_route({"saude": busy, "mec": busy} if activity is None else activity),
    )
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


async def test_formato_com_as_seis_chaves_e_schema_2(fake_client):
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
        "indexing_lag",
        "agency_activity",
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
    # MONTH: dateTo exclusivo na API → D, para os 7 dias fechados inteiros
    assert (call["dateFrom"], call["dateTo"]) == ("2026-09-28", "2026-10-05")


async def test_falha_de_uma_consulta_nao_derruba_as_outras(fake_client):
    _route(fake_client)
    fake_client.route("HealthTrendingEntities", RuntimeError("timeout"))

    data = await _health(fake_client)

    assert data["pipelines"]["entity_ranking"]["status"] == "unavailable"
    assert "timeout" in data["pipelines"]["entity_ranking"]["message"]
    assert data["pipelines"]["themes"]["status"] == "ok"


# ── G2: atraso de indexação e atividade das agências ────────────────────────


async def test_atraso_de_indexacao_medido_no_dia_d_em_utc(fake_client):
    _route(fake_client, indexing=_indexing(day=4, stored={"2026-10-04": 150, "2026-10-05": 171}))

    data = await _health(fake_client)
    lag = data["pipelines"]["indexing_lag"]

    (call,) = fake_client.calls("HealthIndexingLag")
    assert call["agencies"] == sorted(code for code, _, _ in CATALOG_AGENCIES)
    assert (call["dateFrom"], call["dateTo"]) == ("2026-10-04", "2026-10-05")  # DAY inclusivo
    assert call["dayStart"] == "2026-10-05T00:00:00+00:00"
    assert call["prevStart"] == "2026-10-04T00:00:00+00:00"
    assert call["end"] == "2026-10-06T00:00:00+00:00"
    assert lag["status"] == "unavailable"
    assert (lag["metric"]["indexed"], lag["metric"]["stored"]) == (4, 171)  # sem a duplicata
    assert "05/10" in lag["message"]
    assert any(n["code"] == "INDEXING_LAG" for n in data["notices"])


async def test_com_pouco_volume_no_dia_d_compara_d_menos_1_e_d(fake_client):
    # 22:00 UTC de um dia fraco: 8 artigos no Postgres em D; a amostra vira D−1..D
    _route(
        fake_client,
        indexing=_indexing(day=2, two_days=155, stored={"2026-10-04": 150, "2026-10-05": 8}),
    )

    data = await _health(fake_client)
    lag = data["pipelines"]["indexing_lag"]

    assert lag["status"] == "ok"
    assert (lag["metric"]["indexed"], lag["metric"]["stored"]) == (155, 158)
    assert "04–05/10" in lag["message"]


async def test_atividade_das_agencias_com_silenciadas(fake_client):
    _route(fake_client, activity={"saude": busy, "secom": silent_since_blackout})

    data = await _health(fake_client)
    activity = data["pipelines"]["agency_activity"]

    assert activity["status"] == "ok"
    assert activity["metric"]["silenced"] == 1
    (silenced,) = data["agencyActivity"]["silenced"]
    assert silenced["key"] == "secom"
    assert silenced["silentSince"] == "2026-07-04"
    assert silenced["lastActive"] == "2026-07-03"
    assert data["agencyActivity"]["resumed"] == []
    assert data["calendar"]["silencedAgencies"] == 1


async def test_atividade_das_agencias_com_retomadas_na_recuperacao(fake_client):
    _route(fake_client, activity={"saude": busy, "secom": resumed_on_26_10})

    data = json.loads(
        await fetch_health_pipelines(fake_client, now=datetime(2026, 10, 30, 12, 0, tzinfo=BRT))
    )

    (resumed,) = data["agencyActivity"]["resumed"]
    assert (resumed["key"], resumed["resumedOn"]) == ("secom", "2026-10-26")
    assert data["calendar"]["phase"] == "recovery"
    assert data["calendar"]["resumedAgencies"] == 1


async def test_falha_do_snapshot_deixa_so_a_atividade_indisponivel(fake_client):
    _route(fake_client)
    fake_client.route("AgencyActivitySnapshot", RuntimeError("timeout"))

    data = await _health(fake_client)

    assert data["pipelines"]["agency_activity"]["status"] == "unavailable"
    assert data["agencyActivity"] is None
    assert data["pipelines"]["indexing_lag"]["status"] == "ok"
    assert data["pipelines"]["themes"]["status"] == "ok"


async def test_falha_da_consulta_de_indexacao_deixa_so_o_atraso_indisponivel(fake_client):
    _route(fake_client)
    fake_client.route("HealthIndexingLag", RuntimeError("503"))

    data = await _health(fake_client)

    assert data["pipelines"]["indexing_lag"]["status"] == "unavailable"
    assert "503" in data["pipelines"]["indexing_lag"]["message"]
    assert data["pipelines"]["agency_activity"]["status"] == "ok"
