"""Avaliadores de saúde dos dados (detecção dinâmica) e mapeamento para avisos."""

from datetime import UTC, date, datetime, timedelta

import pytest

from gobus_mcp.data_status import (
    NOTICE_FOR_KEY,
    SINCE_HINTS,
    entity_ranking_status,
    metric_coverage_status,
    notices_for,
    parse_api_datetime,
    sentiment_analytics_status,
    share_status,
    theme_coverage_status,
    to_notice,
)
from gobus_mcp.payloads.common import DataStatus

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)


# ── share_status ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("covered", "total", "expected"),
    [(95, 100, "ok"), (80, 100, "ok"), (79, 100, "degraded"), (10, 100, "degraded"),
     (9, 100, "unavailable"), (0, 100, "unavailable"), (0, 0, "unavailable")],
)  # fmt: skip
def test_share_status_limiares_padrao(covered, total, expected):
    ds = share_status("summaries", covered, total)
    assert isinstance(ds, DataStatus)
    assert ds.key == "summaries"
    assert ds.status == expected
    assert ds.metric["covered"] == covered and ds.metric["total"] == total


def test_share_status_limiares_customizados_e_ratio():
    ds = share_status("entities_ner", 60, 100, dead=0.5, degraded=0.9)
    assert ds.status == "degraded"
    assert ds.metric["ratio"] == pytest.approx(0.6)
    assert share_status("entities_ner", 0, 0).metric["ratio"] is None


def test_since_usa_dica_so_quando_nao_ok_e_explicito_prevalece():
    assert SINCE_HINTS["themes"] == date(2026, 9, 26)
    assert share_status("themes", 0, 100).since == date(2026, 9, 26)
    assert share_status("themes", 100, 100).since is None
    assert share_status("themes", 0, 100, since=date(2026, 9, 25)).since == date(2026, 9, 25)
    assert share_status("entity_ranking", 0, 100).since is None  # sem dica


# ── theme_coverage_status ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("classified", "total", "expected"),
    [(0, 1097, "unavailable"), (600, 1097, "degraded"), (500, 1097, "unavailable"), (700, 1000, "degraded"),
     (800, 1000, "ok"), (0, 0, "unavailable")],
)  # fmt: skip
def test_theme_coverage_status(classified, total, expected):
    ds = theme_coverage_status(classified, total, days=7)
    assert ds.key == "themes"
    assert ds.status == expected
    assert "7" in ds.message


def test_theme_coverage_status_com_escopo_explicito():
    # baseline anterior à janela: o texto não é "dos últimos N dias"
    ds = theme_coverage_status(10, 1000, days=21, scope="do baseline (18 dias antes da janela)")
    assert ds.status == "unavailable"
    assert "do baseline (18 dias antes da janela)" in ds.message
    assert "últimos" not in ds.message
    assert ds.metric["days"] == 21


# ── metric_coverage_status (legibilidade, word_count) ───────────────────────


def _rows(*pairs):
    return [{"articleCount": n, "avgReadabilityFlesch": v, "avgWordCount": v} for n, v in pairs]


def test_legibilidade_toda_nula_e_indisponivel_com_dica_de_data():
    ds = metric_coverage_status(
        "readability", _rows((120, None), (30, None)), "avgReadabilityFlesch"
    )
    assert ds.status == "unavailable"
    assert ds.since == date(2026, 6, 30)
    assert ds.metric["coveredArticles"] == 0 and ds.metric["totalArticles"] == 150


def test_legibilidade_com_dado_e_ok_e_cobertura_ponderada():
    ok = metric_coverage_status(
        "readability", _rows((100, 33.5), (10, None)), "avgReadabilityFlesch"
    )
    assert ok.status == "ok"
    assert ok.metric["ratio"] == pytest.approx(100 / 110)
    partial = metric_coverage_status("word_count", _rows((50, 400.0), (50, None)), "avgWordCount")
    assert partial.status == "degraded"


def test_zero_nao_e_tratado_como_nulo():
    ds = metric_coverage_status("readability", _rows((10, 0.0)), "avgReadabilityFlesch")
    assert ds.status == "ok"


def test_sem_artigos_e_indisponivel():
    assert metric_coverage_status("readability", [], "avgReadabilityFlesch").status == "unavailable"


# ── sentiment_analytics_status ──────────────────────────────────────────────


def test_sentimento_analytics_nulo_e_indisponivel_mesmo_com_pct_positive_zero():
    rows = [{"articleCount": 50, "avgSentimentScore": None, "pctPositive": 0.0}]
    ds = sentiment_analytics_status(rows)
    assert ds.key == "sentiment_analytics"
    assert ds.status == "unavailable"


def test_sentimento_analytics_presente_e_ok():
    rows = [{"articleCount": 50, "avgSentimentScore": 0.12, "pctPositive": 0.4}]
    assert sentiment_analytics_status(rows).status == "ok"


# ── entity_ranking_status ───────────────────────────────────────────────────


def _trending_row(computed_at: str | None, vr: float, wc: int, **extra) -> dict:
    return {"computedAt": computed_at, "volumeRatio": vr, "windowCount": wc, **extra}


def test_ranking_estado_de_05_10_e_degradado():
    # linhas de 25/06 a 05/10, todas no piso antigo (vr = wc · 142,857)
    rows = [
        _trending_row("2026-07-03 21:06:24.66578+00", 8571.43, 60),
        _trending_row("2026-09-02 21:06:24.98625+00", 4000.0, 28),
        _trending_row("2026-10-05 03:06:11.1+00", 714.29, 5),
    ]
    ds = entity_ranking_status(rows, now=NOW)
    assert ds.status == "degraded"
    assert ds.metric["rowsTotal"] == 3
    assert ds.metric["rowsLegacyFloor"] == 3
    assert ds.metric["distinctRuns"] == 3
    assert ds.metric["rowsLastRun"] == 1
    assert ds.metric["ageHours"] == pytest.approx(11.9, abs=0.1)


def test_ranking_corrigido_e_recente_e_ok():
    rows = [_trending_row("2026-10-05 12:00:00+00", 3.2, 12, isNew=False) for _ in range(10)]
    rows.append(_trending_row("2026-10-05 12:00:00+00", 12.0, 3, isNew=True))
    ds = entity_ranking_status(rows, now=NOW)
    assert ds.status == "ok"
    assert ds.metric["rowsLegacyFloor"] == 0
    assert ds.metric["isNewShare"] == pytest.approx(1 / 11)


def test_ranking_com_mais_de_13h_e_degradado_e_com_mais_de_7_dias_indisponivel():
    stale = (NOW - timedelta(hours=20)).isoformat()
    assert entity_ranking_status([_trending_row(stale, 2.0, 5)], now=NOW).status == "degraded"
    dead = (NOW - timedelta(days=8)).isoformat()
    assert entity_ranking_status([_trending_row(dead, 2.0, 5)], now=NOW).status == "unavailable"


def test_ranking_vazio_ou_sem_computed_at_e_indisponivel():
    assert entity_ranking_status([], now=NOW).status == "unavailable"
    assert entity_ranking_status([_trending_row(None, 2.0, 5)], now=NOW).status == "unavailable"


def test_parse_api_datetime():
    assert parse_api_datetime("2026-07-03 21:06:24.66578+00") == datetime(
        2026, 7, 3, 21, 6, 24, 665780, tzinfo=UTC
    )
    assert parse_api_datetime("2026-07-03T21:06:24") == datetime(2026, 7, 3, 21, 6, 24, tzinfo=UTC)
    assert parse_api_datetime(None) is None
    assert parse_api_datetime("lixo") is None


# ── avisos ──────────────────────────────────────────────────────────────────


def test_mapeamento_data_key_para_notice_code():
    assert NOTICE_FOR_KEY == {
        "themes": "THEMES_UNCLASSIFIED",
        "sentiment_labels": "SENTIMENT_UNAVAILABLE",
        "sentiment_analytics": "SENTIMENT_UNAVAILABLE",
        "readability": "READABILITY_UNAVAILABLE",
        "word_count": "READABILITY_UNAVAILABLE",
        "entity_ranking": "TRENDING_ENTITIES_STALE",
        "indexing_lag": "INDEXING_LAG",
    }


def test_to_notice():
    unavailable = share_status("themes", 0, 100)
    notice = to_notice(unavailable)
    assert notice.code == "THEMES_UNCLASSIFIED"
    assert notice.severity == "error"
    assert notice.since == date(2026, 9, 26)
    assert notice.affects == ["themes"]
    assert to_notice(share_status("themes", 50, 100)).severity == "warn"
    assert to_notice(share_status("themes", 100, 100)) is None
    assert to_notice(share_status("summaries", 0, 100)) is None  # sem código


def test_notices_for_agrupa_por_codigo():
    statuses = [
        metric_coverage_status("readability", _rows((10, None)), "avgReadabilityFlesch"),
        metric_coverage_status("word_count", _rows((5, 300.0), (5, None)), "avgWordCount"),
        share_status("themes", 100, 100),
    ]
    notices = notices_for(statuses)
    assert [n.code for n in notices] == ["READABILITY_UNAVAILABLE"]
    (notice,) = notices
    assert notice.severity == "error"
    assert notice.affects == ["readability", "word_count"]


# ── cobertura de temas via GraphQL (topThemes + analyticsKpis) ─────────────


async def test_theme_coverage_consulta_e_avalia(fake_client):
    from gobus_mcp.data_status import theme_coverage

    fake_client.route(
        "ThemeCoverage",
        {
            "topThemes": [{"label": "Saúde", "count": 30}, {"label": "Economia", "count": 20}],
            "analyticsKpis": {"total": 100},
        },
    )

    status = await theme_coverage(fake_client, 7)

    assert fake_client.calls("ThemeCoverage") == [{"days": 7}]
    assert status.key == "themes"
    assert status.status == "degraded"
    assert status.metric["classified"] == 50


async def test_theme_coverage_sem_tema_fica_indisponivel(fake_client):
    from gobus_mcp.data_status import theme_coverage

    fake_client.route("ThemeCoverage", {"topThemes": [], "analyticsKpis": {"total": 930}})

    status = await theme_coverage(fake_client, 7)

    assert status.status == "unavailable"
    assert status.since.isoformat() == "2026-09-26"


# ── indexing_lag (G2) ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("indexed", "stored", "expected"),
    [
        (155, 155, "ok"),
        (140, 155, "ok"),  # ≥ 90%
        (3, 8, "ok"),  # faltam só 5: atraso normal de poucos minutos
        (100, 155, "degraded"),
        (78, 155, "degraded"),  # ≥ 50%
        (4, 171, "unavailable"),  # 05/10: o tempo real do Typesense parado
        (200, 150, "ok"),  # bucket diferente: o Typesense à frente não é atraso
    ],
)
def test_indexing_lag_status_pela_fracao_indexada(indexed, stored, expected):
    from gobus_mcp.data_status import indexing_lag_status

    status = indexing_lag_status(indexed, stored, label="05/10 (UTC)")

    assert status.key == "indexing_lag"
    assert status.status == expected
    assert status.metric["indexed"] == indexed
    assert status.metric["stored"] == stored


def test_indexing_lag_status_redige_quanto_falta():
    from gobus_mcp.data_status import indexing_lag_status

    status = indexing_lag_status(4, 171, label="05/10 (UTC)")

    assert status.metric["missing"] == 167
    assert status.metric["ratio"] == pytest.approx(4 / 171)
    assert "4 de 171" in status.message and "05/10 (UTC)" in status.message
    assert to_notice(status).code == "INDEXING_LAG"


def test_indexing_lag_sem_artigos_no_postgres_nao_acusa_atraso():
    from gobus_mcp.data_status import indexing_lag_status

    status = indexing_lag_status(0, 0, label="05/10 (UTC)")

    assert status.status == "ok"
    assert status.metric["ratio"] is None
