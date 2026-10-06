"""gobus_forecast_trends (G2): share-of-voice em 3/7/21 dias, taxa log por dia, composto
renormalizado, momentum, perfil de dia útil com feriados, projeção amortecida com
``horizon_days`` efetivo, confiança rebaixada na recuperação e payload ``ForecastReport``."""

import asyncio
import time
from datetime import date, datetime

import pytest

from gobus_mcp.agency_activity import AgencyActivityService
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import BRT
from gobus_mcp.payloads.anomalies import MAX_PAYLOAD_BYTES, payload_size
from gobus_mcp.payloads.forecast import ForecastReport
from gobus_mcp.tools.forecast_trends import build_forecast_report, forecast_trends
from tests.fixtures.g2 import NOW_0510, busy, route_g2, theme_ranges_0510

D = date


def _at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=BRT)


def _theme(report: ForecastReport, label: str):
    return next(t for t in report.themes if t.label == label)


def _daily(theme) -> dict[date, float]:
    return {p.date: p.expected for p in theme.projection.daily}


def blackout_drop(day: date) -> int:
    """Agência que só publica fora do defeso: o nível da plataforma cai no defeso."""
    return 0 if D(2026, 7, 4) <= day <= D(2026, 10, 25) else busy(day)


# ── estado medido em 05/10 ──────────────────────────────────────────────────


async def test_estado_0510_so_a_janela_de_21_dias_entra_e_degradada(fake_client):
    route_g2(fake_client, themes=theme_ranges_0510())

    report = await build_forecast_report(fake_client, now=NOW_0510)
    windows = report.windows

    assert (windows["3d"].status, windows["7d"].status) == ("unavailable", "unavailable")
    assert windows["3d"].classified_coverage == 0.0
    assert windows["21d"].status == "degraded"
    assert windows["21d"].effective_weight == 1.0
    assert report.themes
    assert {t.confidence for t in report.themes} == {"low"}
    assert {t.momentum for t in report.themes} == {"undetermined"}
    unclassified = next(n for n in report.notices if n.code == "THEMES_UNCLASSIFIED")
    assert unclassified.since == D(2026, 9, 26)
    assert {"CLASSIFIER_CHANGED", "ELECTORAL_BLACKOUT"} <= {n.code for n in report.notices}
    assert report.status == "partial"
    assert "Janela 3d: indisponível" in report.summary
    assert sorted(v["days"] for v in fake_client.calls("ThemeRangeCounts")) == [
        3,
        7,
        14,
        21,
        28,
        84,
    ]


# ── horizonte e limite ──────────────────────────────────────────────────────


async def test_horizon_7_e_21_dao_saidas_diferentes(fake_client):
    route_g2(fake_client)

    r7 = await build_forecast_report(fake_client, horizon_days=7, now=NOW_0510)
    r21 = await build_forecast_report(fake_client, horizon_days=21, now=NOW_0510)
    md7 = await forecast_trends(fake_client, horizon_days=7, now=NOW_0510)

    assert md7 == r7.summary
    assert r7.summary != r21.summary
    assert "Horizonte 7 dias (05/10 → 11/10/2026)" in r7.summary
    assert "Horizonte 21 dias (05/10 → 25/10/2026)" in r21.summary
    s7, s21 = _theme(r7, "Saúde").projection, _theme(r21, "Saúde").projection
    assert (s7.horizon_days, len(s7.daily)) == (7, 7)
    assert (s21.horizon_days, len(s21.daily)) == (21, 21)
    assert s21.expected_articles > s7.expected_articles
    assert s21.share_at_horizon > s7.share_at_horizon  # tema em alta: a fatia segue subindo


@pytest.mark.parametrize(("requested", "effective"), [(40, 28), (0, 1), (-3, 1)])
async def test_horizonte_fora_de_1_a_28_e_ajustado(fake_client, requested, effective):
    route_g2(fake_client)

    report = await build_forecast_report(fake_client, horizon_days=requested, now=NOW_0510)

    assert report.params["horizon_days_requested"] == requested
    assert report.params["horizon_days"] == effective
    assert f"ajustado para {effective}" in report.summary
    assert _theme(report, "Saúde").projection.horizon_days == effective


async def test_limit_entre_1_e_10(fake_client):
    route_g2(fake_client)

    many = await build_forecast_report(fake_client, limit=50, now=NOW_0510)
    two = await build_forecast_report(fake_client, limit=2, now=NOW_0510)

    assert many.params["limit"] == 10
    assert len(many.themes) == 6  # todos os temas do fixture
    assert len(two.themes) == 2


# ── ritmo, momentum e confiança ─────────────────────────────────────────────


async def test_momentum_e_ordem_pela_taxa_composta(fake_client):
    route_g2(fake_client)

    report = await build_forecast_report(fake_client, limit=10, now=NOW_0510)

    assert report.themes[0].label == "Saúde"
    assert _theme(report, "Saúde").momentum == "accelerating"
    assert _theme(report, "Educação").momentum == "decelerating"
    assert _theme(report, "Educação").weekly_multiplier < 1
    assert {w.status for w in report.windows.values()} == {"ok"}
    assert report.status == "ok"
    row = next(line for line in report.summary.splitlines() if line.startswith("| Saúde"))
    assert "acelerando" in row


async def test_confianca_cai_um_nivel_na_recuperacao(fake_client):
    route_g2(fake_client)

    normal = await build_forecast_report(fake_client, now=_at(D(2026, 11, 30)))
    recovery = await build_forecast_report(fake_client, now=_at(D(2026, 11, 29)))

    assert _theme(normal, "Saúde").confidence == "high"
    assert _theme(recovery, "Saúde").confidence == "medium"
    assert "recovery" in _theme(recovery, "Saúde").flags


# ── calendário: perfil, feriados e nível por fase ───────────────────────────


async def test_perfil_de_dia_util_do_snapshot(fake_client):
    route_g2(fake_client)

    report = await build_forecast_report(fake_client, now=NOW_0510)
    profile = report.platform.weekday_profile

    assert report.platform.profile_source == "snapshot"
    assert profile["0"] == 1.0
    assert profile["5"] == pytest.approx(0.3, abs=0.01)
    assert profile["6"] == pytest.approx(0.1, abs=0.01)


async def test_feriados_contam_como_domingo_na_projecao(fake_client):
    route_g2(fake_client)

    october = await build_forecast_report(fake_client, horizon_days=21, now=NOW_0510)
    recovery = await build_forecast_report(fake_client, horizon_days=28, now=_at(D(2026, 10, 26)))
    oct_daily = _daily(_theme(october, "Saúde"))
    nov_daily = _daily(_theme(recovery, "Saúde"))

    assert oct_daily[D(2026, 10, 12)] < 0.5 * oct_daily[D(2026, 10, 13)]  # 12/10, segunda
    assert nov_daily[D(2026, 11, 2)] < 0.5 * nov_daily[D(2026, 11, 3)]  # Finados, segunda
    assert nov_daily[D(2026, 11, 20)] < 0.5 * nov_daily[D(2026, 11, 19)]  # 20/11, sexta


async def test_calendario_conta_so_as_retomadas_pos_defeso(fake_client):
    def resumed_on_26_10(day: date) -> int:
        return busy(day) if day < D(2026, 7, 4) or day >= D(2026, 10, 26) else 0

    def sporadic(day: date) -> int:  # último silêncio ≥ 14 dias acabou em 20/10 (no defeso)
        return 1 if day in {D(2026, 9, 9), D(2026, 10, 1), D(2026, 10, 20)} else 0

    route_g2(fake_client, activity={"saude": busy, "secom": resumed_on_26_10, "pf": sporadic})

    report = await build_forecast_report(fake_client, now=_at(D(2026, 10, 30)))

    assert report.calendar.resumed_agencies == 1


async def test_horizonte_que_cruza_o_fim_do_defeso_usa_o_nivel_normal(fake_client):
    route_g2(fake_client, activity={"saude": busy, "secom": blackout_drop})

    report = await build_forecast_report(fake_client, horizon_days=28, now=NOW_0510)
    daily = _daily(_theme(report, "Economia e Finanças"))
    levels = report.platform.level_by_phase

    assert levels["normal"] > 1.5 * levels["blackout"]
    assert daily[D(2026, 10, 26)] > 1.5 * daily[D(2026, 10, 19)]  # segundas, antes e depois
    assert "cruza o fim do defeso" in report.summary


@pytest.mark.parametrize(
    ("today", "phase", "codes"),
    [
        (D(2026, 7, 3), "normal", set()),
        (D(2026, 7, 4), "blackout", {"ELECTORAL_BLACKOUT"}),
        (D(2026, 10, 25), "blackout", {"ELECTORAL_BLACKOUT", "CLASSIFIER_CHANGED"}),
        (D(2026, 10, 26), "recovery", {"POST_BLACKOUT_RECOVERY", "CLASSIFIER_CHANGED"}),
        (D(2026, 11, 29), "recovery", {"POST_BLACKOUT_RECOVERY", "CLASSIFIER_CHANGED"}),
        # o baseline de 84 dias cruza o corte (25/09) até 17/12
        (D(2026, 11, 30), "normal", {"CLASSIFIER_CHANGED"}),
        (D(2026, 12, 17), "normal", {"CLASSIFIER_CHANGED"}),
        (D(2026, 12, 18), "normal", set()),
    ],
)
async def test_avisos_de_calendario_nas_fronteiras(fake_client, today, phase, codes):
    route_g2(fake_client)

    report = await build_forecast_report(fake_client, now=_at(today))
    calendar_codes = {
        n.code
        for n in report.notices
        if n.code in ("ELECTORAL_BLACKOUT", "POST_BLACKOUT_RECOVERY", "CLASSIFIER_CHANGED")
    }

    assert report.calendar.phase == phase
    assert calendar_codes == codes


# ── degradação ──────────────────────────────────────────────────────────────


async def test_falha_do_snapshot_usa_o_perfil_padrao(fake_client):
    route_g2(fake_client)
    fake_client.route("AgencyActivitySnapshot", RuntimeError("timeout"))

    report = await build_forecast_report(fake_client, now=NOW_0510)

    assert report.platform.profile_source == "default"
    activity = next(s for s in report.data_status if s.key == "agency_activity")
    assert activity.status == "unavailable"
    assert report.themes
    assert "perfil semanal padrão" in report.summary


async def test_falha_de_um_range_tira_a_janela_do_composto(fake_client):
    route_g2(fake_client)
    themes = fake_client._routes["ThemeRangeCounts"]

    def respond(variables):
        if variables["days"] == 84:
            raise RuntimeError("503")
        return themes(variables)

    fake_client.route("ThemeRangeCounts", respond)

    report = await build_forecast_report(fake_client, now=NOW_0510)

    assert report.windows["21d"].status == "unavailable"
    assert report.windows["3d"].effective_weight == pytest.approx(0.625)
    assert report.windows["7d"].effective_weight == pytest.approx(0.375)
    assert _theme(report, "Saúde").windows["21d"] is None
    assert report.status == "partial"


# ── payload e orçamento ─────────────────────────────────────────────────────


async def test_payload_valida_cabe_em_20kb_e_summary_e_o_markdown(fake_client):
    route_g2(fake_client)

    report = await build_forecast_report(fake_client, horizon_days=28, limit=10, now=NOW_0510)
    markdown = await forecast_trends(fake_client, horizon_days=28, limit=10, now=NOW_0510)

    ForecastReport.model_validate(report.model_dump(mode="json"))
    assert payload_size(report) <= MAX_PAYLOAD_BYTES
    assert report.summary == markdown
    assert len(markdown.encode()) <= 6_144
    assert set(report.windows) == {"3d", "7d", "21d"}


async def test_latencia_no_orcamento_com_cache_quente(fake_client):
    route_g2(fake_client)

    class Slow:
        def __init__(self, inner):
            self.inner, self.calls = inner, 0

        async def execute(self, query, variables=None, **kwargs):
            self.calls += 1
            await asyncio.sleep(0.03)  # escala 1/10 de ~0,3 s por chamada
            return await self.inner.execute(query, variables, **kwargs)

    client = Slow(fake_client)
    catalog = AgencyCatalog(client)
    activity = AgencyActivityService(client, catalog)
    cache = TTLCache()

    await build_forecast_report(
        client, now=NOW_0510, catalog=catalog, activity=activity, cache=cache
    )
    calls_cold = client.calls
    start = time.perf_counter()
    await build_forecast_report(
        client, now=NOW_0510, catalog=catalog, activity=activity, cache=cache
    )

    assert time.perf_counter() - start <= 0.2  # orçamento: 2 s (escala 1/10)
    assert client.calls == calls_cold
