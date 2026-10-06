"""``AnomalyReport`` (integration.md §1.4): G2 produz, o app ``ui://anomaly-radar`` consome."""

import json

import pytest
from pydantic import ValidationError

from gobus_mcp.domains import DOMAIN_ORDER, Domain
from gobus_mcp.payloads.anomalies import (
    MAX_PAYLOAD_BYTES,
    AnomalyReport,
    fit_anomaly_budget,
    payload_size,
    summarize_domains,
)
from tests.factories import anomaly_report, domain_summaries, entity_signal, theme_signal


def test_relatorio_valida_e_serializa_em_camel_case():
    report = anomaly_report()
    data = report.model_dump(mode="json")
    assert data["schemaVersion"] == 1
    assert data["kind"] == "gobus.anomalies" and data["tool"] == "gobus_detect_anomalies"
    assert data["thresholds"] == {
        "ratio": 1.5,
        "windowAgencies": 5,
        "silenceRatio": 2.0,
        "minCount": 5,
    }
    themes = data["themes"]
    assert themes["windows"]["short"]["kind"] == "rolling"
    assert themes["windows"]["short"]["bucketTz"] == "UTC"
    assert themes["classifiedCoverage"] == {"short": 0.97, "long": 0.95}
    sig = themes["signals"][0]
    assert {"ratioShort", "ratioLong", "countShort", "shareLong", "band", "daily"} <= set(sig)
    assert sig["daily"] is None  # série diária de tema fica null na v1
    ents = data["entities"]
    assert ents["window"]["kind"] == "closed" and ents["window"]["bucketTz"] == "UTC"
    assert ents["upstream"]["rowsLegacyFloor"] == 0
    e = ents["signals"][0]
    assert e["owner"]["agencyKey"] == "saude" and e["owner"]["method"] == "coverage"
    for key in ("maxDayShare", "upstreamVolumeRatio", "ownerDaily", "samples"):
        assert key in e
    assert e["samples"] == []
    assert [d["domain"] for d in data["domains"]] == [d.value for d in DOMAIN_ORDER]
    assert AnomalyReport.model_validate(data) == report


def test_dominios_em_ordem_fixa_e_completos():
    report = anomaly_report()
    data = report.model_dump(mode="json")
    data["domains"] = list(reversed(data["domains"]))
    with pytest.raises(ValidationError):
        AnomalyReport.model_validate(data)
    data["domains"] = data["domains"][:7]
    with pytest.raises(ValidationError):
        AnomalyReport.model_validate(data)


def test_enums_em_ingles_e_severidade_entre_0_e_1():
    with pytest.raises(ValidationError):
        theme_signal(kind="pico_sustentado")
    with pytest.raises(ValidationError):
        entity_signal(kind="rajada")
    with pytest.raises(ValidationError):
        entity_signal(severity=1.2)
    with pytest.raises(ValidationError):
        theme_signal(band="alto")
    with pytest.raises(ValidationError):
        entity_signal(owner={"agency_key": "saude", "method": "cobertura"})


def test_series_diarias_com_no_maximo_28_pontos():
    entity_signal(daily=[0] * 28, owner_daily=[0] * 28)
    with pytest.raises(ValidationError):
        entity_signal(daily=[0] * 29)
    with pytest.raises(ValidationError):
        entity_signal(owner_daily=[0] * 29)


def test_campos_extras_sao_proibidos():
    data = anomaly_report().model_dump(mode="json")
    data["themes"]["signals"][0]["ratioShortRaw"] = 1.0
    with pytest.raises(ValidationError):
        AnomalyReport.model_validate(data)


def test_summarize_domains_conta_e_mede_por_dominio():
    themes = [
        theme_signal(domain=Domain.HEALTH, kind="sustained_spike", severity=0.5, band="watch"),
        theme_signal(domain=Domain.HEALTH, kind="sustained_drop", severity=0.4, band="watch"),
        theme_signal(domain=Domain.EDUCATION, kind="sustained_spike", severity=0.7, band="alert"),
    ]
    entities = [
        entity_signal(domain=Domain.HEALTH, kind="coordinated_silence", severity=0.8, band="alert"),
        entity_signal(domain=Domain.HEALTH, kind="concentrated_coverage", severity=0.6),
        entity_signal(domain=Domain.SECURITY, kind="normal", severity=0.9, band="alert"),
        entity_signal(domain=Domain.SECURITY, kind="burst", severity=0.9, band="alert"),
        entity_signal(domain=Domain.OTHER, kind="new_entity", severity=0.9, band="alert"),
    ]
    summary = {d.domain: d for d in summarize_domains(themes, entities)}
    assert [d.domain for d in summarize_domains(themes, entities)] == list(DOMAIN_ORDER)
    health = summary[Domain.HEALTH]
    assert (health.spikes, health.silences, health.concentrated) == (1, 2, 1)
    assert health.spike_level == pytest.approx(0.6)  # pico de tema e cobertura concentrada
    assert health.silence_level == pytest.approx(0.8)
    assert health.max_severity == pytest.approx(0.8)
    assert (health.spike_band, health.silence_band) == ("watch", "alert")
    assert health.label == "Saúde"
    assert summary[Domain.EDUCATION].spike_band == "alert"
    # normal, burst, new_entity e calendar_explained não entram nos gauges
    security = summary[Domain.SECURITY]
    assert (security.spikes, security.silences, security.concentrated) == (0, 0, 0)
    assert security.max_severity == 0.0 and security.spike_band == "normal"
    assert summary[Domain.OTHER].max_severity == 0.0


def test_domain_summaries_da_fabrica_seguem_a_ordem():
    assert [d.domain for d in domain_summaries()] == list(DOMAIN_ORDER)


def _big_report():
    long_text = "x" * 150
    entities = [
        entity_signal(
            entity_id=f"dgb_entidade-{i:02d}",
            kind="normal" if i % 6 else "concentrated_coverage",
            severity=round(0.01 * i, 2),
            band="normal",
            explanation=long_text,
            daily=[i % 5] * 28,
            owner_daily=[i % 3] * 28,
        )
        for i in range(30)
    ]
    themes = [theme_signal(label=f"Tema {i}") for i in range(15)]
    return anomaly_report(theme_signals=themes, entity_signals=entities, summary="m" * 6000)


def test_fit_anomaly_budget_corta_primeiro_o_que_e_normal():
    report = _big_report()
    assert payload_size(report) > MAX_PAYLOAD_BYTES
    fitted = fit_anomaly_budget(report)
    assert payload_size(fitted) <= MAX_PAYLOAD_BYTES
    kept = {s.entity_id for s in fitted.entities.signals}
    anomalies = {s.entity_id for s in report.entities.signals if s.kind != "normal"}
    assert anomalies <= kept  # as anomalias sobrevivem
    assert len(fitted.themes.signals) == 15
    assert fitted.entities.note and "orçamento" in fitted.entities.note
    assert fitted.summary == report.summary


def test_fit_anomaly_budget_nao_mexe_no_que_ja_cabe():
    report = anomaly_report()
    assert fit_anomaly_budget(report) == report
    assert payload_size(report) == len(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False).encode()
    )
