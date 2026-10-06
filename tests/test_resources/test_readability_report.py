"""gobus://readability-report: agências ativas do catálogo, null-aware, janela efetiva."""

import json
from datetime import date

from gobus_mcp.resources.readability_report import fetch_readability_report
from tests.conftest import route_catalog

TODAY = date(2026, 10, 5)
REQ_FROM, LOOKBACK_FROM = "2026-07-07", "2025-10-04"


def _row(period, key, count, flesch, wc=450.0):
    return {
        "period": f"{period}-01 00:00:00+00",
        "agencyKey": key,
        "agencyName": key.upper(),
        "articleCount": count,
        "avgReadabilityFlesch": flesch,
        "avgWordCount": wc if flesch is not None else None,
    }


ROWS = [
    _row("2026-10", "agencia_brasil", 300, 33.5, wc=470.0),
    _row("2026-10", "secom", 150, 17.0),
    _row("2026-10", "defesa", 200, -22.9, wc=800.0),
    _row("2026-10", "mec", 120, None),
]


def _route(client, by_from, *, active=None):
    route_catalog(client, active=active)
    client.route(
        "ReadabilityWindow",
        lambda v: {
            "agencyAnalytics": [
                r for r in by_from.get(v["dateFrom"], []) if r["agencyKey"] in v["agencies"]
            ]
        },
    )
    return client


async def _report(client):
    return json.loads(await fetch_readability_report(client, today=TODAY))


async def test_formato_e_agencias_ativas_do_catalogo(fake_client):
    _route(fake_client, {REQ_FROM: ROWS, LOOKBACK_FROM: ROWS})

    data = await _report(fake_client)

    assert data["schemaVersion"] == 2
    assert data["targetFlesch"] == 50
    assert data["scale"] == "flesch_en_textstat"
    assert data["requestedWindow"] == {"start": "2026-07-07", "end": "2026-10-04", "days": 90}
    (top,) = fake_client.calls("CatalogTopAgencies")
    assert (top["days"], top["limit"]) == (90, 20)
    first = fake_client.calls("ReadabilityWindow")[0]
    assert "trabalho" not in first["agencies"]  # nada de lista fixa com chaves inválidas
    assert "saude" in first["agencies"]


async def test_nulo_continua_nulo_e_gap_nulo(fake_client):
    _route(fake_client, {REQ_FROM: ROWS, LOOKBACK_FROM: ROWS})

    data = await _report(fake_client)

    mec = next(a for a in data["agencies"] if a["agencyKey"] == "mec")
    assert mec["avgReadabilityFlesch"] is None
    assert mec["gapToTarget"] is None
    assert mec["articleCount"] == 120 and mec["articlesWithData"] == 0
    assert mec["agencyName"] == "Ministério da Educação"


async def test_gap_clamp_e_ordem(fake_client):
    _route(fake_client, {REQ_FROM: ROWS, LOOKBACK_FROM: ROWS})

    data = await _report(fake_client)

    by_key = {a["agencyKey"]: a for a in data["agencies"]}
    assert by_key["agencia_brasil"]["gapToTarget"] == -16.5
    assert by_key["defesa"]["avgReadabilityFlesch"] == 0.0
    assert by_key["defesa"]["avgReadabilityFleschRaw"] == -22.9
    assert by_key["defesa"]["band"] == "very_hard"
    values = [a["avgReadabilityFlesch"] for a in data["agencies"]]
    with_data = [v for v in values if v is not None]
    assert with_data == sorted(with_data, reverse=True)
    assert values[len(with_data) :] == [None] * (len(values) - len(with_data))  # nulos no fim


async def test_janela_efetiva_quando_o_dado_parou(fake_client):
    empty = [_row("2026-09", "saude", 90, None)]
    june = [_row("2026-06", "saude", 100, 30.0)]
    _route(fake_client, {REQ_FROM: empty, LOOKBACK_FROM: june + empty, "2026-04-02": june})

    data = await _report(fake_client)

    assert data["windowShifted"] is True
    assert data["effectiveWindow"]["start"] == "2026-04-02"
    assert data["note"] == "dados até 06/2026"
    assert data["coverage"]["lastPeriodWithData"].startswith("2026-06")
    assert data["dataStatus"][0]["status"] == "unavailable"
    saude = next(a for a in data["agencies"] if a["agencyKey"] == "saude")
    assert saude["avgReadabilityFlesch"] == 30.0
