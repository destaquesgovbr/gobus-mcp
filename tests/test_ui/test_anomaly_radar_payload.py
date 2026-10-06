"""Payload do app ``ui://anomaly-radar`` (``structuredContent`` de ``gobus_detect_anomalies``).

O G2 mediu 19,7 KB com 30 candidatos e o ``summary`` truncado. No app:
- o ``content`` leva o Markdown **completo**; o ``summary`` é o mesmo texto até 6 KB;
- séries diárias só nos sinais que o app desenha (os anômalos); as tendências normais vão
  sem série e com teto; o que fica de fora é contado em ``entities.omitted`` (por classe);
- os limiares das faixas e as opções de sensibilidade vêm no payload (o JS não os fixa).
"""

from collections import Counter

from gobus_mcp.analytics.ratios import BAND_ALERT, BAND_WATCH
from gobus_mcp.analytics.render import SUMMARY_MAX_BYTES, fit_summary
from gobus_mcp.analytics.themes import SENSITIVITY
from gobus_mcp.payloads.anomalies import (
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_NORMALS,
    MAX_PAYLOAD_SIGNALS,
    compact_anomaly_payload,
    fit_anomaly_budget,
    payload_size,
)
from gobus_mcp.tools.detect_anomalies import build_anomaly_output, build_anomaly_report
from tests.conftest import FakeGraphQLClient
from tests.factories import anomaly_report, entity_signal
from tests.fixtures.g2 import (
    ACTIVITY_0510,
    NOW_0510,
    many_candidates,
    route_g2,
    scenario_0510,
)

ANOMALOUS = ("coordinated_silence", "concentrated_coverage", "burst", "new_entity")


def _signals(n_anomalous: int, n_normal: int) -> list:
    out = []
    for i in range(n_anomalous):
        out.append(
            entity_signal(
                entity_id=f"dgb_anomala-{i:02d}",
                name=f"Anômala {i:02d}",
                kind=ANOMALOUS[i % len(ANOMALOUS)],
                severity=round(0.9 - 0.05 * i, 2),
                band="alert" if i < 4 else "watch",
                daily=[i % 4] * 28,
                owner_daily=[i % 2] * 28,
            )
        )
    for i in range(n_normal):
        out.append(
            entity_signal(
                entity_id=f"dgb_normal-{i:02d}",
                name=f"Normal {i:02d}",
                kind="normal",
                severity=round(0.3 - 0.01 * i, 2),
                band="normal",
                daily=[1] * 28,
                owner_daily=[1] * 28,
            )
        )
    return out


def test_compacta_series_so_nos_sinais_exibidos_e_teto_de_normais():
    signals = _signals(MAX_PAYLOAD_SIGNALS + 4, MAX_PAYLOAD_NORMALS + 7)
    report = anomaly_report(entity_signals=signals, summary="resumo")

    compact = compact_anomaly_payload(report)
    kept = compact.entities.signals
    anomalous = [s for s in kept if s.kind != "normal"]
    normals = [s for s in kept if s.kind == "normal"]

    # os anômalos de maior severidade ficam, com as séries (o app desenha a sparkline)
    assert [s.entity_id for s in anomalous] == [
        f"dgb_anomala-{i:02d}" for i in range(MAX_PAYLOAD_SIGNALS)
    ]
    assert all(len(s.daily) == 28 for s in anomalous)
    # tendências normais: teto e sem série
    assert len(normals) == MAX_PAYLOAD_NORMALS
    assert all(s.daily == [] and s.owner_daily is None for s in normals)
    # o que saiu do payload é contado por classe (o Markdown do content tem tudo)
    dropped = Counter(s.kind for s in signals) - Counter(s.kind for s in kept)
    assert compact.entities.omitted == dict(dropped)
    assert sum(compact.entities.omitted.values()) == len(signals) - len(kept)
    # temas, gauges e resumo intactos
    assert compact.themes == report.themes
    assert compact.domains == report.domains
    assert compact.summary == "resumo"


def test_compactacao_de_relatorio_pequeno_so_tira_a_serie_das_normais():
    signals = _signals(2, 1)
    report = anomaly_report(entity_signals=signals)

    compact = compact_anomaly_payload(report)

    assert [s.entity_id for s in compact.entities.signals] == [s.entity_id for s in signals]
    assert compact.entities.signals[0].daily == signals[0].daily
    assert compact.entities.signals[-1].daily == []
    assert compact.entities.omitted == {}


def test_rede_de_seguranca_do_orcamento_tambem_conta_os_omitidos():
    long_text = "x" * 400
    signals = [
        entity_signal(
            entity_id=f"dgb_entidade-{i:02d}",
            kind="concentrated_coverage",
            severity=round(0.9 - 0.01 * i, 2),
            explanation=long_text,
            daily=[3] * 28,
            owner_daily=[1] * 28,
        )
        for i in range(30)
    ]
    report = anomaly_report(entity_signals=signals, summary="m" * 6000)

    fitted = fit_anomaly_budget(report)

    assert payload_size(fitted) <= MAX_PAYLOAD_BYTES
    assert fitted.entities.omitted == {"concentrated_coverage": 30 - len(fitted.entities.signals)}


def test_limiares_das_faixas_e_opcoes_de_sensibilidade_no_payload():
    data = anomaly_report().model_dump(mode="json")

    assert data["severityBands"] == {"watch": BAND_WATCH, "alert": BAND_ALERT}
    assert data["sensitivityOptions"] == list(SENSITIVITY)
    assert data["entities"]["omitted"] == {}


async def test_30_candidatos_markdown_completo_e_payload_compacto():
    rows, contexts = many_candidates()
    client = route_g2(FakeGraphQLClient(), trending=rows, contexts=contexts, activity=ACTIVITY_0510)

    report, markdown = await build_anomaly_output(client, now=NOW_0510)

    # o content leva o Markdown inteiro (todas as 30 entidades e a metodologia)
    assert "truncado" not in markdown and "### Metodologia" in markdown
    assert sum(f"número {i:02d}" in markdown for i in range(30)) == 30
    # o summary do payload é o mesmo texto, até 6 KB
    assert report.summary == fit_summary(markdown)
    assert len(report.summary.encode()) <= SUMMARY_MAX_BYTES
    # payload: no máximo os tetos, com folga no orçamento
    signals = report.entities.signals
    assert len([s for s in signals if s.kind != "normal"]) <= MAX_PAYLOAD_SIGNALS
    assert len([s for s in signals if s.kind == "normal"]) <= MAX_PAYLOAD_NORMALS
    assert all(s.daily for s in signals if s.kind != "normal")  # séries dos exibidos
    assert sum(report.entities.omitted.values()) == 30 - len(signals)
    assert payload_size(report) <= MAX_PAYLOAD_BYTES


async def test_build_anomaly_report_e_o_payload_do_output():
    rows, contexts = scenario_0510()
    client = route_g2(FakeGraphQLClient(), trending=rows, contexts=contexts, activity=ACTIVITY_0510)

    report, markdown = await build_anomaly_output(client, now=NOW_0510)
    again = await build_anomaly_report(client, now=NOW_0510)

    assert again == report
    assert report.summary == markdown  # cabe em 6 KB: idênticos
    assert all(s.daily == [] for s in report.entities.signals if s.kind == "normal")
