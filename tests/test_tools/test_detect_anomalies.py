"""gobus_detect_anomalies (G2): temas por share-of-voice com gate de cobertura, entidades
recalculadas via entityCoverage a partir dos candidatos do trendingEntities, classes com
precedência, calendário do defeso e payload ``AnomalyReport``."""

import asyncio
import time
from datetime import date, datetime

import pytest

from gobus_mcp.agency_activity import AgencyActivityService
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import BRT
from gobus_mcp.domains import Domain
from gobus_mcp.payloads.anomalies import MAX_PAYLOAD_BYTES, AnomalyReport, payload_size
from gobus_mcp.tools.detect_anomalies import build_anomaly_report, detect_anomalies
from tests.fixtures.g2 import (
    NOW_0510,
    busy,
    context,
    coverage_rows,
    route_g2,
    spread,
    theme_ranges_0510,
    trending_row,
    trending_rows_0510,
)

D = date
RUN_0510 = "2026-10-05 21:00:00+00"


def silent_since_blackout(day: date) -> int:
    """Agência que parou de publicar no início do defeso (04/07)."""
    return busy(day) if day < D(2026, 7, 4) else 0


def resumed_on_26_10(day: date) -> int:
    """Agência calada no defeso que voltou a publicar em 26/10."""
    return busy(day) if day < D(2026, 7, 4) or day >= D(2026, 10, 26) else 0


ACTIVITY_0510 = {
    "saude": busy,
    "mec": busy,
    "pf": busy,
    "cgu": busy,
    "secom": silent_since_blackout,
}


def _section(md: str, header: str) -> str:
    for part in md.split("### "):
        if part.startswith(header):
            return part
    return ""


def _by_id(report: AnomalyReport) -> dict:
    return {s.entity_id: s for s in report.entities.signals}


def scenario_0510() -> tuple[list[dict], dict[str, dict]]:
    """Ranking já corrigido (uma execução, Laplace) e a cobertura de cada candidato em
    05/10: janela 28/09–04/10 e baseline 31/08–27/09."""
    rows = [
        trending_row("dgb_novo", "Programa Novo", vr=32.0, wc=7, run=RUN_0510),
        trending_row(
            "dgb_censo-escolar-2025",
            "Censo Escolar 2025",
            type_="EVENT",
            vr=4321.0,
            wc=60,
            run=RUN_0510,
        ),  # fmt: skip
        trending_row("dgb_concentrada", "Pauta Concentrada", vr=10.4, wc=12, run=RUN_0510),
        trending_row("dgb_silencio", "Tema Calado", vr=13.0, wc=9, run=RUN_0510),
        trending_row("dgb_secom", "Pauta da Secom", vr=7.0, wc=6, run=RUN_0510),
        trending_row("dgb_normal", "Assunto Comum", vr=1.06, wc=12, run=RUN_0510),
        trending_row("dgb_pe-de-meia", "Pé-de-Meia", type_="POLICY", vr=1.14, wc=5, run=RUN_0510),
        trending_row("dgb_republicada", "Só Republicada", vr=2.0, wc=5, run=RUN_0510),
    ]
    normal_rows = []
    for agency in ("saude", "mec", "pf", "cgu", "defesa", "trabalho-e-emprego"):
        normal_rows += coverage_rows(
            agency,
            {**spread(D(2026, 8, 31), D(2026, 9, 27), 8), **spread(D(2026, 9, 28), D(2026, 10, 4), 2)},
        )  # fmt: skip
    contexts = {
        # baseline zero com padrão de concentrada (2 agências, 3 dias): é entidade nova
        "dgb_novo": context(
            "dgb_novo",
            "Programa Novo",
            rows=coverage_rows("mec", {D(2026, 9, 29): 3, D(2026, 10, 1): 2})
            + coverage_rows("cgu", {D(2026, 10, 2): 2}),
        ),  # fmt: skip
        # caso Censo: 57 de 60 artigos num dia
        "dgb_censo-escolar-2025": context(
            "dgb_censo-escolar-2025",
            "Censo Escolar 2025",
            type_="EVENT",
            rows=coverage_rows("inep", {D(2026, 9, 10): 2, D(2026, 10, 1): 57, D(2026, 10, 2): 3}),
        ),  # fmt: skip
        "dgb_concentrada": context(
            "dgb_concentrada",
            "Pauta Concentrada",
            rows=coverage_rows(
                "mec",
                {
                    **spread(D(2026, 9, 1), D(2026, 9, 20), 4),
                    **spread(D(2026, 9, 29), D(2026, 10, 2), 8),
                },
            )
            + coverage_rows("saude", spread(D(2026, 9, 29), D(2026, 10, 2), 4)),
        ),  # fmt: skip
        "dgb_silencio": context(
            "dgb_silencio",
            "Tema Calado",
            agency_key="saude",
            rows=coverage_rows("saude", spread(D(2026, 9, 1), D(2026, 9, 25), 6))
            + coverage_rows(
                "mec",
                {
                    **spread(D(2026, 9, 2), D(2026, 9, 20), 2),
                    **spread(D(2026, 9, 28), D(2026, 10, 3), 4),
                },
            )
            + coverage_rows("pf", spread(D(2026, 9, 29), D(2026, 10, 2), 3))
            + coverage_rows("cgu", {D(2026, 9, 30): 1, D(2026, 10, 1): 1}),
        ),  # fmt: skip
        "dgb_secom": context(
            "dgb_secom",
            "Pauta da Secom",
            agency_key="secom",
            rows=coverage_rows("mec", {D(2026, 9, 5): 2, D(2026, 9, 29): 2, D(2026, 9, 30): 1})
            + coverage_rows("pf", {D(2026, 10, 1): 2, D(2026, 10, 2): 1}),
        ),  # fmt: skip
        "dgb_normal": context("dgb_normal", "Assunto Comum", rows=normal_rows),
        "dgb_pe-de-meia": context(
            "dgb_pe-de-meia",
            "Pé-de-Meia",
            type_="POLICY",
            domain="EDUCATION",
            rows=coverage_rows(
                "mec",
                {
                    **spread(D(2026, 8, 31), D(2026, 9, 27), 20),
                    **spread(D(2026, 9, 28), D(2026, 10, 4), 5),
                },
            ),
        ),  # fmt: skip
        "dgb_republicada": context(
            "dgb_republicada",
            "Só Republicada",
            rows=coverage_rows(
                "agencia_brasil",
                {D(2026, 9, 10): 3, **spread(D(2026, 9, 28), D(2026, 10, 2), 5)},
            ),
        ),  # fmt: skip
    }
    return rows, contexts


def _route_scenario(fake_client, **overrides):
    rows, contexts = scenario_0510()
    params = {"trending": rows, "contexts": contexts, "activity": ACTIVITY_0510}
    params.update(overrides)
    return route_g2(fake_client, **params)


# ── estado medido em 05/10 ──────────────────────────────────────────────────


async def test_estado_0510_temas_indisponiveis_desde_26_09_e_sem_linhas_legadas(fake_client):
    route_g2(
        fake_client,
        themes=theme_ranges_0510(),
        trending=trending_rows_0510(),
        activity=ACTIVITY_0510,
    )

    report = await build_anomaly_report(fake_client, now=NOW_0510)

    assert report.themes.status == "unavailable"
    assert report.themes.signals == []
    unclassified = next(n for n in report.notices if n.code == "THEMES_UNCLASSIFIED")
    assert unclassified.since == D(2026, 9, 26)
    codes = {n.code for n in report.notices}
    assert {"BASELINE_ZERO_SUPPRESSED", "TRENDING_ENTITIES_STALE", "ELECTORAL_BLACKOUT"} <= codes
    # as 50 linhas são do piso antigo: nenhuma vira candidata nem gasta consulta
    assert report.entities.upstream.rows_total == 50
    assert report.entities.upstream.rows_legacy_floor == 50
    assert report.entities.candidates == 0
    assert report.entities.signals == []
    assert fake_client.calls("AnomalyEntityContext") == []
    assert report.entities.status == "degraded"
    for leaked in ("8571", "8.571", "857,1", "857.1", "714,3"):
        assert leaked not in report.summary
    assert "### Picos Sustentados" in report.summary
    assert "26/09/2026" in report.summary


async def test_tool_devolve_o_mesmo_markdown_do_summary(fake_client):
    route_g2(fake_client, themes=theme_ranges_0510(), trending=trending_rows_0510())

    markdown = await detect_anomalies(fake_client, now=NOW_0510)
    report = await build_anomaly_report(fake_client, now=NOW_0510)

    assert markdown == report.summary
    assert markdown.startswith("## Detector de Anomalias Comunicacionais")


async def test_cabecalho_diferencia_janela_fechada_de_entidade_e_moveis_de_tema(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    header = report.summary.split("\n\n", 1)[0]

    assert "janela fechada 28/09–04/10/2026" in header
    assert "America/Sao_Paulo" in header
    assert "janelas móveis de 3 e 7 dias" in header
    assert "UTC" in header
    assert report.entities.window.kind == "closed"
    assert report.themes.windows.short.kind == "rolling"
    assert report.themes.windows.long.bucket_tz == "UTC"


# ── entidades ────────────────────────────────────────────────────────────────


async def test_baseline_zero_nunca_vira_silencio_nem_concentrada(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    signals = _by_id(report)

    assert signals["dgb_novo"].kind == "new_entity"
    assert signals["dgb_novo"].baseline_count == 0
    assert signals["dgb_republicada"].kind == "normal"
    assert not [
        s
        for s in report.entities.signals
        if s.baseline_count == 0 and s.kind in ("coordinated_silence", "concentrated_coverage")
    ]


async def test_rajada_com_max_day_share_acima_de_0_8(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    censo = _by_id(report)["dgb_censo-escolar-2025"]

    assert censo.max_day_share >= 0.8
    assert censo.kind == "burst"
    assert "Censo Escolar 2025" in _section(report.summary, "Rajadas e Entidades Novas")
    # rajada pontual (razão 81× contra 2 no baseline) e entidade nova não são "alerta"
    assert (censo.band, _by_id(report)["dgb_novo"].band) == ("watch", "watch")
    for name in ("Censo Escolar 2025", "Programa Novo"):
        line = next(ln for ln in report.summary.splitlines() if name in ln)
        assert "alerta" not in line and "(atenção)" in line


async def test_concentrada_com_baseline_pequeno_nao_e_alerta(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    concentrada = _by_id(report)["dgb_concentrada"]

    # 12 artigos na janela contra 4 no baseline (abaixo do min_count 5): razão 10,4×
    assert concentrada.kind == "concentrated_coverage" and concentrada.baseline_count == 4
    assert concentrada.band == "watch"
    assert "thin_baseline" in concentrada.flags
    line = next(ln for ln in report.summary.splitlines() if "Pauta Concentrada" in ln)
    assert "(atenção)" in line and "baseline pequeno" in line


async def test_classes_recalculadas_pela_cobertura(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    signals = _by_id(report)

    assert signals["dgb_concentrada"].kind == "concentrated_coverage"
    assert signals["dgb_concentrada"].owner.agency_key == "mec"
    assert signals["dgb_concentrada"].domain == Domain.EDUCATION
    assert signals["dgb_silencio"].kind == "coordinated_silence"
    assert signals["dgb_silencio"].owner.method == "agency_key"
    assert signals["dgb_silencio"].owner_window_count == 0
    assert signals["dgb_silencio"].domain == Domain.HEALTH
    assert signals["dgb_secom"].kind == "calendar_explained"
    assert "owner_silenced" in signals["dgb_secom"].flags
    assert signals["dgb_normal"].kind == "normal"
    assert signals["dgb_pe-de-meia"].domain == Domain.EDUCATION
    md = report.summary
    assert "Tema Calado" in _section(md, "Silêncio Coordenado")
    assert "Pauta Concentrada" in _section(md, "Cobertura Concentrada")
    assert "Pauta da Secom" in _section(md, "Explicado pelo Calendário")
    assert "Assunto Comum" in _section(md, "Tendências Normais")


async def test_volume_ratio_do_upstream_so_no_payload(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    censo = _by_id(report)["dgb_censo-escolar-2025"]

    assert censo.upstream_volume_ratio == 4321.0
    assert censo.upstream_computed_at == datetime.fromisoformat("2026-10-05 21:00:00+00:00")
    assert "4321" not in report.summary
    assert "4.321" not in report.summary


async def test_contexto_por_candidato_com_janela_de_cobertura_e_dateto_exclusivo(fake_client):
    _route_scenario(fake_client)

    await build_anomaly_report(fake_client, now=NOW_0510)
    calls = fake_client.calls("AnomalyEntityContext")

    assert len(calls) == 8
    # dona em [D−90, D−8] e série de 28 dias: desde 07/07; dateTo exclusivo = D
    assert {(c["dateFrom"], c["dateTo"]) for c in calls} == {("2026-07-07", "2026-10-05")}


async def test_falha_do_contexto_de_um_candidato_degrada_o_bloco(fake_client):
    rows, contexts = scenario_0510()
    _route_scenario(fake_client)

    def respond(variables):
        if variables["id"] == "dgb_normal":
            raise RuntimeError("timeout")
        return contexts[variables["id"]]

    fake_client.route("AnomalyEntityContext", respond)

    report = await build_anomaly_report(fake_client, now=NOW_0510)

    assert report.entities.status == "degraded"
    assert "dgb_normal" not in _by_id(report)
    assert "1 de 8" in report.entities.note
    assert report.status == "partial"


async def test_contexto_malformado_de_um_candidato_nao_derruba_a_tool(fake_client):
    rows, contexts = scenario_0510()
    contexts["dgb_normal"] = {
        "entity": {"entityId": "dgb_normal", "canonicalName": "Assunto Comum", "type": "ORG"},
        "entityCoverage": [{"period": "data-invalida", "agencyKey": "mec", "articleCount": 1}],
        "policyDetails": None,
    }
    _route_scenario(fake_client, contexts=contexts)

    report = await build_anomaly_report(fake_client, now=NOW_0510)

    assert "dgb_normal" not in _by_id(report)
    assert report.entities.status == "degraded"
    assert "1 de 8" in report.entities.note
    assert len(report.entities.signals) == 7


async def test_falha_do_ranking_deixa_entidades_indisponiveis_e_temas_seguem(fake_client):
    _route_scenario(fake_client)
    fake_client.route("AnomalyTrendingEntities", RuntimeError("503"))

    report = await build_anomaly_report(fake_client, now=NOW_0510)

    assert report.entities.status == "unavailable"
    assert report.themes.status == "ok"
    assert report.status == "partial"
    ranking = next(s for s in report.data_status if s.key == "entity_ranking")
    assert ranking.status == "unavailable"


async def test_falha_do_snapshot_de_atividade_nao_derruba_a_tool(fake_client):
    _route_scenario(fake_client)
    fake_client.route("AgencyActivitySnapshot", RuntimeError("timeout"))

    report = await build_anomaly_report(fake_client, now=NOW_0510)

    activity = next(s for s in report.data_status if s.key == "agency_activity")
    assert activity.status == "unavailable"
    assert report.entities.signals  # segue sem a atividade das donas
    assert "Atividade das agências" in report.summary


# ── temas ────────────────────────────────────────────────────────────────────


async def test_pico_e_queda_sustentados_por_share_of_voice(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    kinds = {t.label: t.kind for t in report.themes.signals}

    assert report.themes.status == "ok"
    assert kinds["Saúde"] == "sustained_spike"
    assert kinds["Educação"] == "sustained_drop"
    assert "Economia e Finanças" not in kinds
    assert sorted(v["days"] for v in fake_client.calls("ThemeRangeCounts")) == [3, 7, 21, 28]
    assert "Saúde" in _section(report.summary, "Picos Sustentados")
    assert "Educação" in _section(report.summary, "Quedas Sustentadas")
    health = next(d for d in report.domains if d.domain == Domain.HEALTH)
    assert (health.spikes, health.silences) == (1, 1)  # pico de tema + silêncio coordenado


# ── parâmetros ───────────────────────────────────────────────────────────────


async def test_domain_filter_com_alias_pt_filtra_os_sinais(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, domain_filter="saude", now=NOW_0510)

    assert report.params["domain_filter"] == "HEALTH"
    assert {t.domain for t in report.themes.signals} == {Domain.HEALTH}
    assert {s.entity_id for s in report.entities.signals} == {"dgb_silencio"}
    # os gauges seguem com os 8 domínios (contexto do radar)
    education = next(d for d in report.domains if d.domain == Domain.EDUCATION)
    assert education.concentrated == 1
    assert "**Domínio:** Saúde" in report.summary


async def test_domain_filter_invalido_devolve_as_opcoes_sem_consultar(fake_client):
    _route_scenario(fake_client)

    md = await detect_anomalies(fake_client, domain_filter="astrologia", now=NOW_0510)

    assert "inválido" in md
    for option in ("HEALTH", "EDUCATION", "OTHER", "meio_ambiente"):
        assert option in md
    assert fake_client.execute.call_count == 0
    with pytest.raises(ValueError):
        await build_anomaly_report(fake_client, domain_filter="astrologia", now=NOW_0510)


async def test_sensibilidade_invalida_devolve_as_opcoes(fake_client):
    _route_scenario(fake_client)

    md = await detect_anomalies(fake_client, sensitivity="extrema", now=NOW_0510)

    assert "inválida" in md
    assert "high" in md and "low" in md
    assert fake_client.execute.call_count == 0


async def test_sensibilidade_entra_nos_limiares_do_payload(fake_client):
    _route_scenario(fake_client)

    report = await build_anomaly_report(fake_client, sensitivity="HIGH", now=NOW_0510)

    assert report.params["sensitivity"] == "high"
    assert report.thresholds.ratio == 1.3
    assert "**Sensibilidade:** high" in report.summary


# ── calendário ───────────────────────────────────────────────────────────────


async def test_cenario_30_10_retomada_vira_calendar_explained_com_flag_recovery(fake_client):
    now = datetime(2026, 10, 30, 15, 0, tzinfo=BRT)  # janela 23–29/10; baseline 06/06–03/07
    rows = [trending_row("dgb_retomada", "Pauta Retomada", vr=2.8, wc=11,
                         run="2026-10-30 03:00:00+00")]  # fmt: skip
    ctx = context(
        "dgb_retomada",
        "Pauta Retomada",
        rows=coverage_rows(
            "secom",
            {
                **spread(D(2026, 6, 8), D(2026, 6, 30), 8),
                D(2026, 10, 26): 3,
                D(2026, 10, 27): 3,
                D(2026, 10, 28): 2,
                D(2026, 10, 29): 2,
            },
        )  # fmt: skip
        + coverage_rows(
            "saude",
            {
                **spread(D(2026, 6, 8), D(2026, 6, 30), 8),
                **spread(D(2026, 9, 1), D(2026, 9, 30), 4),
                D(2026, 10, 23): 1,
            },
        ),  # fmt: skip
    )
    route_g2(
        fake_client,
        trending=rows,
        contexts={"dgb_retomada": ctx},
        activity={"secom": resumed_on_26_10, "saude": busy, "mec": busy},
    )

    report = await build_anomaly_report(fake_client, now=now)
    signal = _by_id(report)["dgb_retomada"]

    assert report.calendar.phase == "recovery"
    assert report.calendar.resumed_agencies == 1
    assert signal.kind == "calendar_explained"
    assert "recovery" in signal.flags
    assert "pre_blackout_baseline" in signal.flags
    assert report.entities.baseline.start.astimezone(BRT).date() == D(2026, 6, 6)
    assert "POST_BLACKOUT_RECOVERY" in {n.code for n in report.notices}
    assert "Pauta Retomada" in _section(report.summary, "Explicado pelo Calendário")


def sporadic_until_26_10(day: date) -> int:
    """Agência esporádica: publica de tempos em tempos (o último silêncio ≥ 14 dias acabou
    em 20/10, dentro do defeso) e diariamente desde 26/10."""
    occasional = {D(2026, 6, 10), D(2026, 8, 20), D(2026, 9, 9), D(2026, 10, 1), D(2026, 10, 20)}
    return 1 if day in occasional or day >= D(2026, 10, 26) else 0


async def test_cenario_30_10_agencia_esporadica_nao_conta_como_retomada(fake_client):
    now = datetime(2026, 10, 30, 15, 0, tzinfo=BRT)
    rows = [trending_row("dgb_esporadica", "Pauta Esporádica", vr=2.8, wc=10,
                         run="2026-10-30 03:00:00+00")]  # fmt: skip
    ctx = context(
        "dgb_esporadica",
        "Pauta Esporádica",
        rows=coverage_rows("pf", spread(D(2026, 10, 26), D(2026, 10, 29), 9))
        + coverage_rows(
            "saude",
            {
                **spread(D(2026, 6, 8), D(2026, 6, 30), 8),
                **spread(D(2026, 9, 1), D(2026, 9, 30), 4),
                D(2026, 10, 23): 1,
            },
        ),  # fmt: skip
    )
    route_g2(
        fake_client,
        trending=rows,
        contexts={"dgb_esporadica": ctx},
        activity={
            "secom": resumed_on_26_10,
            "pf": sporadic_until_26_10,
            "saude": busy,
            "mec": busy,
        },
    )

    report = await build_anomaly_report(fake_client, now=now)
    signal = _by_id(report)["dgb_esporadica"]

    assert report.calendar.resumed_agencies == 1  # só a secom voltou depois do defeso
    assert signal.kind == "concentrated_coverage"
    assert "resumed_agencies" not in signal.flags


@pytest.mark.parametrize(
    ("today", "phase", "codes", "baseline_start"),
    [
        (D(2026, 7, 3), "normal", set(), D(2026, 5, 29)),
        (D(2026, 7, 4), "blackout", {"ELECTORAL_BLACKOUT"}, D(2026, 5, 30)),
        # os baselines de tema (21 e 28 dias) já não cruzam a troca de classificador
        (D(2026, 10, 25), "blackout", {"ELECTORAL_BLACKOUT"}, D(2026, 9, 20)),
        (D(2026, 10, 26), "recovery", {"POST_BLACKOUT_RECOVERY"}, D(2026, 6, 6)),
        (D(2026, 11, 29), "recovery", {"POST_BLACKOUT_RECOVERY"}, D(2026, 6, 6)),
        (D(2026, 11, 30), "normal", set(), D(2026, 10, 26)),
    ],
)
async def test_fases_do_calendario_nas_fronteiras(fake_client, today, phase, codes, baseline_start):
    route_g2(fake_client)
    now = datetime(today.year, today.month, today.day, 12, 0, tzinfo=BRT)

    report = await build_anomaly_report(fake_client, now=now)
    calendar_codes = {
        n.code
        for n in report.notices
        if n.code in ("ELECTORAL_BLACKOUT", "POST_BLACKOUT_RECOVERY", "CLASSIFIER_CHANGED")
    }

    assert report.calendar.phase == phase
    assert calendar_codes == codes
    assert report.entities.baseline.start.astimezone(BRT).date() == baseline_start


# ── payload e orçamento ─────────────────────────────────────────────────────


def _many_candidates(n: int = 30) -> tuple[list[dict], dict[str, dict]]:
    rows, contexts = [], {}
    agencies = ("saude", "mec", "pf", "cgu", "defesa", "trabalho-e-emprego", "mds")
    for i in range(n):
        entity_id = f"dgb_entidade-com-nome-longo-{i:02d}"
        name = f"Entidade com um nome canônico razoavelmente longo número {i:02d}"
        rows.append(trending_row(entity_id, name, vr=2.0 + i, wc=20 + i, run=RUN_0510))
        cov = []
        for k, agency in enumerate(agencies):
            cov += coverage_rows(
                agency,
                {**spread(D(2026, 7, 7), D(2026, 9, 27), 20 + k),
                 **spread(D(2026, 9, 28), D(2026, 10, 4), 3 + (i + k) % 4)},
            )  # fmt: skip
        contexts[entity_id] = context(entity_id, name, agency_key="saude", rows=cov)
    return rows, contexts


async def test_payload_valida_cabe_em_20kb_e_summary_e_o_markdown(fake_client):
    rows, contexts = _many_candidates()
    route_g2(fake_client, trending=rows, contexts=contexts, activity=ACTIVITY_0510)

    report = await build_anomaly_report(fake_client, now=NOW_0510)
    markdown = await detect_anomalies(fake_client, now=NOW_0510)

    assert report.entities.candidates == 30
    AnomalyReport.model_validate(report.model_dump(mode="json"))
    assert payload_size(report) <= MAX_PAYLOAD_BYTES
    assert report.summary == markdown
    assert len(markdown.encode()) <= 6_144
    assert [d.domain for d in report.domains] == list(Domain)


class _SlowClient:
    """Cliente com latência fixa por chamada; mede a concorrência dos contextos."""

    def __init__(self, inner, delay: float, slow_ops: dict[str, float] | None = None):
        self.inner = inner
        self.delay = delay
        self.slow_ops = slow_ops or {}
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def execute(self, query, variables=None, **kwargs):
        from tests.conftest import operation_name

        name = operation_name(query)
        self.calls += 1
        is_ctx = name == "AnomalyEntityContext"
        if is_ctx:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.slow_ops.get(name, self.delay))
            return await self.inner.execute(query, variables, **kwargs)
        finally:
            if is_ctx:
                self.in_flight -= 1


async def test_latencia_no_orcamento_com_cache_e_semaforo_de_8(fake_client):
    rows, contexts = _many_candidates()
    route_g2(fake_client, trending=rows, contexts=contexts, activity=ACTIVITY_0510)
    # escala 1/10: chamada comum 0,3 s → 0,03 s; snapshot de atividade 3 s → 0,3 s
    client = _SlowClient(fake_client, 0.03, {"AgencyActivitySnapshot": 0.3})
    catalog = AgencyCatalog(client)
    activity = AgencyActivityService(client, catalog)
    cache = TTLCache()

    start = time.perf_counter()
    cold = await build_anomaly_report(
        client, now=NOW_0510, catalog=catalog, activity=activity, cache=cache
    )
    cold_s = time.perf_counter() - start
    calls_cold = client.calls
    start = time.perf_counter()
    warm = await build_anomaly_report(
        client, now=NOW_0510, catalog=catalog, activity=activity, cache=cache
    )
    warm_s = time.perf_counter() - start

    assert 1 < client.max_in_flight <= 8
    assert cold_s <= 0.6  # orçamento a frio: 6 s (escala 1/10)
    assert warm_s <= 0.2  # orçamento com cache quente: 2 s (escala 1/10)
    assert client.calls == calls_cold  # cache quente: nenhuma consulta nova
    assert warm.summary == cold.summary
