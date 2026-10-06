"""Contagens de temas por range móvel (``topThemes`` + ``analyticsKpis``) para anomalias e
forecast: uma consulta por range em paralelo, cache curto com o instante da consulta e
falha isolada por range."""

from datetime import UTC, datetime, timedelta

from gobus_mcp.cache import TTLCache
from gobus_mcp.theme_data import THEME_RANGE_TTL, fetch_theme_ranges

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)


def _respond(variables):
    days = variables["days"]
    return {
        "topThemes": [{"label": "Saúde", "count": 10 * days}, {"label": "Educação", "count": days}],
        "analyticsKpis": {"total": 12 * days},
    }


async def test_uma_consulta_por_range_com_contagens_e_total(fake_client):
    fake_client.route("ThemeRangeCounts", _respond)

    fetch = await fetch_theme_ranges(fake_client, (3, 21), now=NOW)

    assert sorted(v["days"] for v in fake_client.calls("ThemeRangeCounts")) == [3, 21]
    assert fetch.ranges[3].counts == {"Saúde": 30, "Educação": 3}
    assert fetch.ranges[21].total == 252
    assert fetch.errors == {}
    assert fetch.as_of == NOW


async def test_pair_monta_a_janela_dentro_do_range_que_a_inclui(fake_client):
    fake_client.route("ThemeRangeCounts", _respond)

    fetch = await fetch_theme_ranges(fake_client, (3, 21), now=NOW)
    pair = fetch.pair(3, 21)

    assert pair is not None
    assert (pair.window_days, pair.baseline_days) == (3, 21)
    assert fetch.pair(7, 28) is None  # range não consultado


async def test_falha_de_um_range_nao_derruba_os_outros(fake_client):
    def respond(variables):
        if variables["days"] == 21:
            raise RuntimeError("timeout")
        return _respond(variables)

    fake_client.route("ThemeRangeCounts", respond)

    fetch = await fetch_theme_ranges(fake_client, (3, 21), now=NOW)

    assert set(fetch.ranges) == {3}
    assert "timeout" in fetch.errors[21]
    assert fetch.pair(3, 21) is None


async def test_cache_reaproveita_e_guarda_o_instante_da_consulta(fake_client):
    fake_client.route("ThemeRangeCounts", _respond)
    cache = TTLCache()

    first = await fetch_theme_ranges(fake_client, (3, 21), now=NOW, cache=cache)
    later = NOW + timedelta(minutes=2)
    second = await fetch_theme_ranges(fake_client, (3, 21), now=later, cache=cache)

    assert len(fake_client.calls("ThemeRangeCounts")) == 2  # só a primeira rodada consulta
    assert second.ranges[3].counts == first.ranges[3].counts
    # janelas móveis terminam no instante em que o Typesense foi consultado
    assert second.as_of == NOW
    assert THEME_RANGE_TTL <= 600


async def test_falha_nao_e_cacheada(fake_client):
    cache = TTLCache()
    fake_client.route("ThemeRangeCounts", RuntimeError("503"))
    failed = await fetch_theme_ranges(fake_client, (3,), now=NOW, cache=cache)
    assert failed.ranges == {}

    fake_client.route("ThemeRangeCounts", _respond)
    ok = await fetch_theme_ranges(fake_client, (3,), now=NOW, cache=cache)

    assert ok.ranges[3].total == 36
