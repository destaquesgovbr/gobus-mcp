"""Leitura de legibilidade por agência: janela pedida, janela efetiva e agregação null-aware."""

from datetime import date

from gobus_mcp.calendario import DateRange
from gobus_mcp.readability_data import (
    aggregate_agencies,
    load_readability_window,
    rank_agencies,
)

REQUESTED = DateRange(date(2026, 7, 7), date(2026, 10, 4))  # closed_window(90, 05/10)
LOOKBACK_FROM = "2025-10-04"
EFFECTIVE_FROM, EFFECTIVE_TO = "2026-04-02", "2026-06-30"


def _row(period, key, count, flesch, wc=450.0, name=None):
    return {
        "period": f"{period}-01 00:00:00+00",
        "agencyKey": key,
        "agencyName": name or key,
        "articleCount": count,
        "avgReadabilityFlesch": flesch,
        "avgWordCount": wc if flesch is not None else None,
    }


def _route(client, by_from):
    client.route(
        "ReadabilityWindow",
        lambda v: {
            "agencyAnalytics": [
                r for r in by_from.get(v["dateFrom"], []) if r["agencyKey"] in v["agencies"]
            ]
        },
    )


async def test_janela_com_dado_nao_desloca(fake_client):
    rows = [_row("2026-09", "saude", 50, None), _row("2026-10", "saude", 100, 30.0)]
    _route(fake_client, {"2026-07-07": rows, LOOKBACK_FROM: rows})

    window = await load_readability_window(fake_client, ["saude"], REQUESTED)

    assert window.effective.shifted is False
    assert window.effective.effective == REQUESTED
    assert window.rows == rows
    assert window.coverage.last_period_with_data.startswith("2026-10")
    calls = fake_client.calls("ReadabilityWindow")
    assert {c["dateFrom"] for c in calls} == {"2026-07-07", LOOKBACK_FROM}
    assert all(c["dateTo"] == "2026-10-04" for c in calls)
    assert window.data_status.status == "degraded"  # 100 de 150 artigos com valor


async def test_sem_dado_na_janela_usa_ultimo_periodo_com_dado(fake_client):
    requested_rows = [_row("2026-09", "saude", 80, None), _row("2026-10", "saude", 10, None)]
    lookback_rows = [_row("2026-05", "saude", 90, 25.0), _row("2026-06", "saude", 100, 31.0)]
    effective_rows = [_row("2026-05", "saude", 90, 25.0), _row("2026-06", "saude", 100, 31.0)]
    _route(
        fake_client,
        {
            "2026-07-07": requested_rows,
            LOOKBACK_FROM: lookback_rows + requested_rows,
            EFFECTIVE_FROM: effective_rows,
        },
    )

    window = await load_readability_window(fake_client, ["saude"], REQUESTED)

    assert window.effective.shifted is True
    assert window.effective.effective == DateRange(date(2026, 4, 2), date(2026, 6, 30))
    assert window.effective.note == "dados até 06/2026"
    assert window.rows == effective_rows
    assert window.requested_rows == requested_rows
    third = fake_client.calls("ReadabilityWindow")[-1]
    assert (third["dateFrom"], third["dateTo"]) == (EFFECTIVE_FROM, EFFECTIVE_TO)
    # cobertura descreve a janela pedida, com o último período do histórico
    assert window.coverage.periods_with_data == 0
    assert window.coverage.last_period_with_data.startswith("2026-06")
    assert window.data_status.status == "unavailable"
    assert window.data_status.key == "readability"


async def test_sem_dado_no_historico_nao_tem_janela_efetiva(fake_client):
    rows = [_row("2026-09", "saude", 80, None)]
    _route(fake_client, {"2026-07-07": rows, LOOKBACK_FROM: rows})

    window = await load_readability_window(fake_client, ["saude"], REQUESTED)

    assert window.effective.effective is None
    assert window.rows == []
    assert len(fake_client.calls("ReadabilityWindow")) == 2


def test_agregacao_ignora_nulo_e_limita_a_escala():
    rows = [
        _row("2026-05", "defesa", 100, -22.9, wc=800.0),
        _row("2026-06", "defesa", 100, 10.0, wc=600.0),
        _row("2026-05", "mec", 40, None),
        _row("2026-05", "saude", 60, 40.0),
        _row("2026-06", "saude", 20, None),
    ]
    items = aggregate_agencies(
        rows,
        names={"defesa": "Ministério da Defesa", "saude": "Ministério da Saúde"},
        republishers=frozenset(),
        codes=["saude", "defesa", "mec", "cgu"],
    )
    by_code = {a.code: a for a in items}

    defesa = by_code["defesa"]
    assert defesa.name == "Ministério da Defesa"
    assert defesa.flesch.value == 5.0  # média de (0.0, 10.0): cada linha limitada antes
    assert round(defesa.flesch.raw, 2) == -6.45
    assert defesa.flesch.clamped is True
    assert defesa.avg_word_count == 700.0

    saude = by_code["saude"]
    assert saude.flesch.value == 40.0  # a linha nula não puxa a média para 0
    assert (saude.article_count, saude.articles_with_data) == (80, 60)

    mec = by_code["mec"]
    assert mec.flesch.value is None and mec.has_data is False
    assert mec.name == "mec"  # sem nome no catálogo → código

    cgu = by_code["cgu"]  # pedida, sem linhas
    assert (cgu.article_count, cgu.has_data) == (0, False)


def test_ranking_ordena_por_flesch_e_separa_sem_dado():
    rows = [
        _row("2026-05", "a", 10, -1.2),
        _row("2026-05", "b", 10, -22.9),
        _row("2026-05", "c", 10, 33.5),
        _row("2026-05", "d", 10, None),
    ]
    with_data, without = rank_agencies(aggregate_agencies(rows))
    assert [a.code for a in with_data] == ["c", "a", "b"]  # empate em 0.0: bruto decide
    assert [a.code for a in without] == ["d"]
