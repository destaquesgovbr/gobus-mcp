"""Markdown de anomalias e forecast a partir dos modelos (puro; vai no ``summary``)."""

from datetime import UTC, date, datetime

from gobus_mcp.analytics.render import (
    SUMMARY_MAX_BYTES,
    fit_summary,
    render_anomalies_markdown,
    render_forecast_markdown,
)
from gobus_mcp.calendario import calendar_context
from gobus_mcp.domains import Domain
from gobus_mcp.payloads.anomalies import OwnerInfo
from gobus_mcp.payloads.common import Notice
from tests.factories import (
    anomaly_report,
    entity_signal,
    forecast_report,
    forecast_theme,
    forecast_window,
    projection,
    theme_signal,
)

SECTIONS = [
    "### Picos Sustentados",
    "### Quedas Sustentadas",
    "### Silêncio Coordenado",
    "### Cobertura Concentrada",
    "### Explicado pelo Calendário",
    "### Rajadas e Entidades Novas",
    "### Tendências Normais",
    "### Metodologia",
]


def _section(md: str, header: str) -> str:
    start = md.index(header) + len(header)
    rest = md[start:]
    nxt = rest.find("\n### ")
    return rest if nxt < 0 else rest[:nxt]


def _all_kinds_report():
    owner = OwnerInfo(agency_key="saude", agency_name="Ministério da Saúde", method="agency_key")
    entities = [
        entity_signal(entity_id="e1", name="Silêncio X", kind="coordinated_silence", owner=owner,
                      owner_window_count=0, owner_activity_ratio=0.9, silence_score=6.2,
                      severity=0.7, band="alert"),
        entity_signal(entity_id="e2", name="Concentrada Y", kind="concentrated_coverage"),
        entity_signal(entity_id="e3", name="Calendário Z", kind="calendar_explained",
                      explanation="A agência dona (secom) está sem publicar no defeso."),
        entity_signal(entity_id="e4", name="Censo Escolar 2025", kind="burst", max_day_share=0.95),
        entity_signal(entity_id="e5", name="Programa Novo", kind="new_entity", baseline_count=0),
        entity_signal(entity_id="e6", name="Tendência W", kind="normal", window_agencies=9),
    ]  # fmt: skip
    themes = [
        theme_signal(label="Saúde", kind="sustained_spike"),
        theme_signal(label="Educação", domain=Domain.EDUCATION, kind="sustained_drop",
                     ratio_short=0.4, ratio_long=0.5),
    ]  # fmt: skip
    return anomaly_report(theme_signals=themes, entity_signals=entities)


def test_anomalias_secoes_em_ordem_e_cabecalho_com_os_dois_tipos_de_janela():
    md = render_anomalies_markdown(_all_kinds_report())
    assert md.startswith("## Detector de Anomalias Comunicacionais")
    positions = [md.index(h) for h in SECTIONS]
    assert positions == sorted(positions)
    head = md[: md.index("### Picos")]
    assert "janela fechada" in head and "28/09–04/10/2026" in head
    assert "America/Sao_Paulo" in head
    assert "janelas móveis" in head and "UTC" in head
    assert "**Sensibilidade:** medium" in head and "**Domínio:** todos" in head
    assert "Defeso eleitoral 2026" in head and "faltam 20 dias" in head
    assert "39 agências" in head


def test_anomalias_cada_classe_na_sua_secao():
    md = render_anomalies_markdown(_all_kinds_report())
    assert "Saúde" in _section(md, "### Picos Sustentados")
    assert "Educação" in _section(md, "### Quedas Sustentadas")
    silence = _section(md, "### Silêncio Coordenado")
    assert "Silêncio X" in silence and "Ministério da Saúde" in silence
    assert "0 menções" in silence and "6,2" in silence
    assert "Concentrada Y" in _section(md, "### Cobertura Concentrada")
    assert "Calendário Z" in _section(md, "### Explicado pelo Calendário")
    burst = _section(md, "### Rajadas e Entidades Novas")
    assert "Censo Escolar 2025" in burst and "Programa Novo" in burst
    assert "Tendência W" in _section(md, "### Tendências Normais")


def test_anomalias_nunca_mostram_o_volume_ratio_do_upstream():
    report = anomaly_report(entity_signals=[entity_signal(upstream_volume_ratio=8571.43)])
    md = render_anomalies_markdown(report)
    assert "8571" not in md and "8.571" not in md


def test_anomalias_com_temas_indisponiveis_e_avisos():
    notice = Notice(
        code="THEMES_UNCLASSIFIED",
        severity="error",
        message="Temas: indisponível — 0% dos artigos dos últimos 3 dias com tema (desde 26/09/2026)",
        since=date(2026, 9, 26),
        affects=["themes"],
    )
    report = anomaly_report(
        theme_signals=[],
        themes_status="unavailable",
        themes_note="Bloco de temas indisponível. Temas: indisponível (desde 26/09/2026).",
        entity_signals=[],
        entities_status="unavailable",
        entities_note="todos os candidatos descartados (baseline zero)",
        notices=[notice],
        domain_filter="HEALTH",
    )
    md = render_anomalies_markdown(report)
    assert "**Avisos de dados**" in md and "desde 26/09/2026" in md
    picos = _section(md, "### Picos Sustentados")
    assert "indisponível" in picos.lower()
    assert "baseline zero" in _section(md, "### Silêncio Coordenado")
    assert "**Domínio:** Saúde" in md


def test_anomalias_cabem_em_6_kb():
    entities = [
        entity_signal(entity_id=f"e{i}", name=f"Entidade com nome comprido número {i}",
                      kind="normal", explanation="x" * 120)
        for i in range(60)
    ]  # fmt: skip
    md = render_anomalies_markdown(anomaly_report(entity_signals=entities))
    assert len(md.encode()) <= SUMMARY_MAX_BYTES
    assert "### Metodologia" in md or "truncado" in md


def test_fit_summary():
    assert fit_summary("curto") == "curto"
    long_md = "\n".join(f"- linha {i} " + "y" * 50 for i in range(500))
    fitted = fit_summary(long_md, max_bytes=2000)
    assert len(fitted.encode()) <= 2000
    assert "truncado" in fitted
    assert fitted.split("\n")[0] == "- linha 0 " + "y" * 50  # corta em fim de linha


# ── forecast ────────────────────────────────────────────────────────────────


def test_forecast_titulo_tabela_e_cruzamento_do_fim_do_defeso():
    report = forecast_report(themes=[forecast_theme(), forecast_theme("Educação",
                                     domain=Domain.EDUCATION, momentum="undetermined",
                                     acceleration=None, confidence="low")])  # fmt: skip
    md = render_forecast_markdown(report)
    assert md.startswith("## Forecast de Tendências — Horizonte 21 dias (05/10 → 25/10/2026)")
    assert (
        "| Tema | Ritmo (×/semana) | Momentum | Confiança | Artigos esperados (21d) | Janelas |"
        in md
    )
    assert "| Saúde | 1,15× | acelerando | média |" in md
    assert "indeterminado" in md and "baixa" in md
    assert "fim do defeso" in md and "26/10" in md
    assert "177" in md and "267" in md  # nível por dia útil antes e depois
    assert "janelas móveis" in md.lower() and "UTC" in md
    assert "### Metodologia" in md
    assert "φ" in md or "amortecida" in md


def test_forecast_horizonte_ajustado_e_janelas_indisponiveis():
    windows = {
        "3d": forecast_window(3, 14, 0.5, status="unavailable", effective_weight=0.0,
                              classified_coverage=0.0),
        "7d": forecast_window(7, 28, 0.3, status="unavailable", effective_weight=0.0,
                              classified_coverage=0.0),
        "21d": forecast_window(21, 84, 0.2, status="degraded", effective_weight=1.0,
                               classified_coverage=0.6),
    }  # fmt: skip
    theme = forecast_theme(projection=projection(horizon=28), confidence="low")
    report = forecast_report(themes=[theme], windows=windows, horizon=28, horizon_requested=60)
    md = render_forecast_markdown(report)
    assert "Horizonte 28 dias" in md
    assert "60" in md  # pedido ajustado
    assert "3d" in md and "indisponível" in md and "60%" in md


def test_forecast_sem_temas():
    md = render_forecast_markdown(forecast_report(themes=[], status="unavailable"))
    assert "Nenhum tema" in md


def test_forecast_fora_do_defeso_sem_linha_de_calendario():
    report = forecast_report(today=date(2026, 12, 7), now=datetime(2026, 12, 7, tzinfo=UTC))
    report = report.model_copy(update={"calendar": calendar_context(date(2026, 12, 7))})
    md = render_forecast_markdown(report)
    assert "defeso" not in md.split("### Metodologia")[0].lower()
    assert len(md.encode()) <= SUMMARY_MAX_BYTES


def test_anomalias_entidade_sem_mencoes_proprias_nao_mostra_razao():
    # w = b = 0 (só republicadoras): a razão de Laplace (4×) não mede nada
    ghost = entity_signal(
        name="Caminhos da Reportagem",
        kind="normal",
        window_count=0,
        baseline_count=0,
        window_agencies=0,
        distinct_days=0,
        max_day_share=0.0,
        ratio=4.0,
        owner=None,
        owner_window_count=None,
        owner_activity_ratio=None,
        severity=0.0,
        band="normal",
        flags=["republishers_excluded"],
    )
    md = render_anomalies_markdown(anomaly_report(entity_signals=[ghost]))
    line = next(x for x in md.splitlines() if "Caminhos da Reportagem" in x)
    assert "sem menções próprias" in line
    assert "razão" not in line
