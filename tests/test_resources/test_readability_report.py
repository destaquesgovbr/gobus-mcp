import json

from gobus_mcp.resources.readability_report import fetch_readability_report


MOCK_ANALYTICS = {"agencyAnalytics": [
    {"period": "2026-05-01", "agencyKey": "agencia_brasil", "agencyName": "Agência Brasil",
     "articleCount": 300, "avgReadabilityFlesch": 33.5, "avgWordCount": 470.0},
    {"period": "2026-05-01", "agencyKey": "secom", "agencyName": "Secom",
     "articleCount": 150, "avgReadabilityFlesch": 17.0, "avgWordCount": 450.0},
    {"period": "2026-05-01", "agencyKey": "defesa", "agencyName": "Min. Defesa",
     "articleCount": 200, "avgReadabilityFlesch": -22.9, "avgWordCount": 800.0},
]}


async def test_retorna_json_valido(fake_client):
    fake_client.set_response(MOCK_ANALYTICS)
    result = await fetch_readability_report(fake_client)
    data = json.loads(result)
    assert data["targetFlesch"] == 50
    assert "generatedAt" in data
    assert isinstance(data["agencies"], list)
    assert len(data["agencies"]) == 3


async def test_gap_calculado_corretamente(fake_client):
    fake_client.set_response(MOCK_ANALYTICS)
    result = await fetch_readability_report(fake_client)
    data = json.loads(result)
    ab = next(a for a in data["agencies"] if a["agencyKey"] == "agencia_brasil")
    assert ab["gapToTarget"] == -16.5


async def test_agencias_ordenadas_por_flesch_desc(fake_client):
    fake_client.set_response(MOCK_ANALYTICS)
    result = await fetch_readability_report(fake_client)
    data = json.loads(result)
    fleschs = [a["avgReadabilityFlesch"] for a in data["agencies"]]
    assert fleschs == sorted(fleschs, reverse=True)
