import json

from gobus_mcp.resources.health_pipelines import fetch_health_pipelines


def _analytics(rows):
    return {"agencyAnalytics": rows}


def _entities(scores):
    return {"trendingEntities": [
        {"entityId": f"Q{i}", "canonicalName": f"E{i}", "type": "ORG",
         "trendingScore": s, "volumeRatio": 2.0, "windowCount": 10,
         "windowAgencies": 5, "computedAt": "2026-06-30"}
        for i, s in enumerate(scores)
    ]}


async def test_status_dead_quando_sentiment_zero(fake_client):
    analytics = _analytics([
        {"period": "2026-06-01", "agencyKey": "secom", "agencyName": "Secom",
         "articleCount": 100, "pctPositive": 0.0, "avgReadabilityFlesch": 17.0},
        {"period": "2026-06-01", "agencyKey": "agencia_brasil", "agencyName": "AB",
         "articleCount": 100, "pctPositive": 0.0, "avgReadabilityFlesch": 33.0},
        {"period": "2026-06-01", "agencyKey": "saude", "agencyName": "MS",
         "articleCount": 100, "pctPositive": 0.0, "avgReadabilityFlesch": 40.0},
    ])
    entities = _entities([5.0, 4.0, 3.0])
    fake_client.set_responses([analytics, entities])

    result = await fetch_health_pipelines(fake_client)
    data = json.loads(result)
    assert data["pipelines"]["sentiment"]["status"] == "DEAD"


async def test_status_degraded_quando_flesch_negativo(fake_client):
    analytics = _analytics([
        {"period": "2026-06-01", "agencyKey": "secom", "agencyName": "Secom",
         "articleCount": 100, "pctPositive": 10.0, "avgReadabilityFlesch": 17.0},
        {"period": "2026-06-01", "agencyKey": "agencia_brasil", "agencyName": "AB",
         "articleCount": 100, "pctPositive": 10.0, "avgReadabilityFlesch": 33.0},
        {"period": "2026-06-01", "agencyKey": "saude", "agencyName": "MS",
         "articleCount": 100, "pctPositive": 10.0, "avgReadabilityFlesch": -5.0},
    ])
    entities = _entities([5.0, 4.0, 3.0])
    fake_client.set_responses([analytics, entities])

    result = await fetch_health_pipelines(fake_client)
    data = json.loads(result)
    assert data["pipelines"]["flesch"]["status"] == "DEGRADED"


async def test_retorna_json_valido(fake_client):
    analytics = _analytics([
        {"period": "2026-06-01", "agencyKey": "secom", "agencyName": "Secom",
         "articleCount": 100, "pctPositive": 10.0, "avgReadabilityFlesch": 17.0},
    ])
    entities = _entities([5.0, 4.0, 3.0])
    fake_client.set_responses([analytics, entities])

    result = await fetch_health_pipelines(fake_client)
    data = json.loads(result)
    assert "checkedAt" in data
    assert "pipelines" in data
    assert set(data["pipelines"].keys()) == {"trendingScore", "sentiment", "flesch"}
