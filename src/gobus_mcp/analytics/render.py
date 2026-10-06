"""Markdown de ``gobus_detect_anomalies``, ``gobus_forecast_trends`` e
``gobus_get_message_coherence`` a partir dos modelos.

Puro: recebe ``AnomalyReport``/``ForecastReport`` e devolve o texto. Nas tools de app, o
Markdown completo (``max_bytes=None``) vai como ``content`` e o ``summary`` do payload é o
mesmo texto até 6 KB (``fit_summary`` corta em fim de linha).

Regras:
- o cabeçalho diz qual janela é qual (entidades: fechada em BRT, contagens por dia UTC;
  temas: móveis em UTC);
- números no formato brasileiro (``2,4×``); enums traduzidos só aqui;
- o ``volumeRatio`` do upstream **nunca** aparece no texto (só no payload).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from gobus_mcp.analytics.framing import FRAME_LABELS
from gobus_mcp.calendario import BRT
from gobus_mcp.data_status import NOTICE_FOR_KEY
from gobus_mcp.domains import DOMAIN_LABELS, Domain
from gobus_mcp.payloads.anomalies import AnomalyReport, EntitySignal, ThemeSignal
from gobus_mcp.payloads.coherence import (
    DIMENSION_WEIGHTS,
    INDEX_CUTS,
    AgencyCoherence,
    CoherenceReport,
)
from gobus_mcp.payloads.common import CalendarContext, DataStatus, Notice, Window
from gobus_mcp.payloads.forecast import ForecastReport, ForecastTheme

SUMMARY_MAX_BYTES = 6_144
MAX_NORMAL_LINES = 10
_TRUNCATED = "\n\n_(resumo truncado em 6 KB; o texto completo vai no content da tool)_"

CONFIDENCE_PT = {"high": "alta", "medium": "média", "low": "baixa"}
BAND_PT = {"normal": "normal", "watch": "atenção", "alert": "alerta"}
MOMENTUM_PT = {
    "accelerating": "acelerando",
    "decelerating": "desacelerando",
    "stable": "estável",
    "undetermined": "indeterminado",
}
STATUS_PT = {"ok": "ok", "degraded": "degradada", "unavailable": "indisponível"}
FLAG_PT = {
    "classifier_changed": "troca de classificador no baseline",
    "degraded_coverage": "cobertura de classificação parcial",
    "recovery": "recuperação pós-defeso",
    "resumed_agencies": "inclui agências retomadas",
    "owner_activity_unknown": "atividade da dona desconhecida",
    "republishers_excluded": "republicadoras excluídas",
    "thin_baseline": "baseline pequeno",
}


# ── formatação ──────────────────────────────────────────────────────────────


def _num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _x(value: float, digits: int = 1) -> str:
    return _num(value, digits) + "×"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _d(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _dm(day: date) -> str:
    return day.strftime("%d/%m")


def _days(window: Window) -> tuple[date, date]:
    """Primeiro e último dia (BRT) de uma janela fechada (``end`` exclusivo)."""
    start = window.start.astimezone(BRT).date()
    end = (window.end - timedelta(microseconds=1)).astimezone(BRT).date()
    return start, end


def _span(start: date, end: date) -> str:
    return f"{_dm(start)}–{_d(end)}"


def fit_summary(markdown: str, max_bytes: int | None = SUMMARY_MAX_BYTES) -> str:
    """O Markdown inteiro se couber em ``max_bytes`` (``None`` = sem limite); senão, corta
    em fim de linha e avisa."""
    if max_bytes is None or len(markdown.encode()) <= max_bytes:
        return markdown
    budget = max_bytes - len(_TRUNCATED.encode())
    kept, used = [], 0
    for line in markdown.split("\n"):
        size = len(line.encode()) + 1
        if used + size > budget:
            break
        kept.append(line)
        used += size
    return "\n".join(kept).rstrip() + _TRUNCATED


def _flags(flags: Iterable[str]) -> str:
    labels = [FLAG_PT[f] for f in flags if f in FLAG_PT]
    return f" · _{'; '.join(labels)}_" if labels else ""


def _calendar_line(cal: CalendarContext) -> str | None:
    if cal.phase == "blackout" and cal.blackout_start and cal.blackout_end:
        line = (
            f"**Calendário:** {cal.label} ({_span(cal.blackout_start, cal.blackout_end)}) — "
            f"faltam {cal.days_to_end} dias"
        )
        if cal.silenced_agencies:
            line += f" · {cal.silenced_agencies} agências sem publicar há ≥14 dias"
        return line
    if cal.phase == "recovery" and cal.recovery_until:
        line = (
            f"**Calendário:** {cal.label} até {_d(cal.recovery_until)} — faltam "
            f"{cal.days_to_end} dias; baselines do período antes do defeso e confiança "
            "reduzida em um nível"
        )
        if cal.resumed_agencies:
            line += f" · {cal.resumed_agencies} agências retomadas"
        return line
    return None


def _warnings(notices: Iterable[Notice], statuses: Iterable[DataStatus]) -> list[str]:
    items = [n.message for n in notices]
    items += [s.message for s in statuses if s.status != "ok" and s.key not in NOTICE_FOR_KEY]
    return items


def _quote(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return [f"> **{title}**", *(f"> - {item}" for item in items), ""]


# ── anomalias ───────────────────────────────────────────────────────────────


def _theme_line(t: ThemeSignal, short_days: int, long_days: int) -> str:
    return (
        f"- **{t.label}** ({DOMAIN_LABELS[t.domain]}) · fatia {_x(t.ratio_short)} em "
        f"{short_days} dias e {_x(t.ratio_long)} em {long_days} · {t.count_short} artigos em "
        f"{short_days} dias, {t.count_long} em {long_days} · severidade {_num(t.severity, 2)} "
        f"({BAND_PT[t.band]}) · confiança {CONFIDENCE_PT[t.confidence]}{_flags(t.flags)}"
    )


def _entity_line(e: EntitySignal, window_days: int) -> str:
    if e.window_count == 0:
        # só republicadoras na janela: a razão de Laplace (w=b=0) não mede nada
        return (
            f"- **{e.name}** ({e.type}, {DOMAIN_LABELS[e.domain]}) · sem menções próprias "
            f"em {window_days}d (só republicadoras){_flags(e.flags)}"
        )
    line = (
        f"- **{e.name}** ({e.type}, {DOMAIN_LABELS[e.domain]}) · {e.window_count} artigos/"
        f"{window_days}d em {e.window_agencies} agência(s) e {e.distinct_days} dia(s) · "
        f"razão {_x(e.ratio)}"
    )
    owner = (e.owner.agency_name or e.owner.agency_key) if e.owner else None
    if e.kind == "coordinated_silence" and owner:
        activity = (
            f"produção total {_x(e.owner_activity_ratio)} do baseline"
            if e.owner_activity_ratio is not None
            else "produção total desconhecida"
        )
        line += f" · dona: {owner} ({e.owner_window_count} menções; {activity})"
        if e.silence_score is not None:
            line += f" · score {_num(e.silence_score)}"
    elif e.kind == "burst":
        line += f" · {e.max_day_share:.0%} num único dia"
    elif e.kind == "new_entity":
        line += " · sem menções no baseline"
    elif owner:
        line += f" · dona: {owner}"
    if e.kind != "normal":  # normal = sem padrão anômalo: severidade só no payload
        line += f" · severidade {_num(e.severity, 2)} ({BAND_PT[e.band]})"
    line += f" · confiança {CONFIDENCE_PT[e.confidence]}"
    line += _flags(e.flags)
    if e.kind == "calendar_explained" and e.explanation:
        line += f"\n  {e.explanation}"
    return line


_ENTITY_SECTIONS = (
    ("### Silêncio Coordenado", ("coordinated_silence",), "Nenhum silêncio coordenado."),
    ("### Cobertura Concentrada", ("concentrated_coverage",), "Nenhuma cobertura concentrada."),
    ("### Explicado pelo Calendário", ("calendar_explained",), "Nada explicado pelo calendário."),
    ("### Rajadas e Entidades Novas", ("burst", "new_entity"), "Nenhuma rajada ou entidade nova."),
    ("### Tendências Normais", ("normal",), "Nenhuma tendência normal."),
)

_METHODOLOGY_ANOMALIES = [
    "### Metodologia",
    "- **Temas:** share-of-voice (fatia entre os artigos classificados) nas janelas móveis "
    "de 3 e 7 dias contra o baseline anterior (21 e 28 dias), com suavização de Laplace. Pico "
    "ou queda só quando as duas janelas passam do limiar. Cancela fim de semana e atraso de "
    "indexação; atenua o defeso.",
    "- **Entidades:** cobertura diária (`entityCoverage`) na janela fechada de 7 dias contra "
    "28 dias de baseline (na recuperação, os 28 dias antes do defeso), sem republicadoras. "
    "Precedência: rajada → entidade nova → calendário → silêncio coordenado → cobertura "
    "concentrada → normal.",
    "- **Severidade** de 0 a 1: 1/3 no limiar da sensibilidade e 2/3 no quadrado dele "
    "(atenção a partir de 0,33; alerta a partir de 0,66). Rajadas, entidades novas e "
    "cobertura com baseline abaixo do volume mínimo ficam no máximo em atenção.",
]


def render_anomalies_markdown(
    report: AnomalyReport, *, max_bytes: int | None = SUMMARY_MAX_BYTES
) -> str:
    """Markdown do detector de anomalias (≤ ``max_bytes``; ``None`` = completo)."""
    ent_start, ent_end = _days(report.entities.window)
    base_start, base_end = _days(report.entities.baseline)
    short, long = report.themes.windows.short, report.themes.windows.long
    themes_until = long.end.astimezone(BRT)
    domain = report.params.get("domain_filter")
    domain_label = DOMAIN_LABELS[Domain(domain)] if domain else "todos"
    lines = [
        "## Detector de Anomalias Comunicacionais",
        f"**Entidades:** janela fechada {_span(ent_start, ent_end)} (até {_dm(ent_end)} 23:59, "
        f"America/Sao_Paulo; contagens por dia UTC) contra o baseline "
        f"{_span(base_start, base_end)} · **Temas:** janelas móveis de {short.days} e "
        f"{long.days} dias até {themes_until.strftime('%d/%m %H:%M')} (BRT; contagens em UTC)",
        f"**Sensibilidade:** {report.params.get('sensitivity', 'medium')} · "
        f"**Domínio:** {domain_label}",
    ]
    calendar = _calendar_line(report.calendar)
    if calendar:
        lines.append(calendar)
    lines.append("")
    lines += _quote("Avisos de dados", _warnings(report.notices, report.data_status))

    themes = report.themes
    for header, kind, empty in (
        ("### Picos Sustentados", "sustained_spike", "Nenhum pico sustentado."),
        ("### Quedas Sustentadas", "sustained_drop", "Nenhuma queda sustentada."),
    ):
        lines.append(header)
        if themes.status == "unavailable":
            lines.append(f"_Indisponível: {themes.note or 'sem dados de temas'}_")
        else:
            if themes.status == "degraded" and themes.note:
                lines.append(f"_{themes.note}_")
            signals = [t for t in themes.signals if t.kind == kind]
            lines += [_theme_line(t, short.days, long.days) for t in signals] or [empty]
        lines.append("")

    ents = report.entities
    for index, (header, kinds, empty) in enumerate(_ENTITY_SECTIONS):
        lines.append(header)
        if ents.status == "unavailable":
            lines.append(
                f"_Entidades indisponíveis: {ents.note or 'sem candidatos'}_"
                if index == 0
                else "_Sem dados de entidades._"
            )
            lines.append("")
            continue
        if index == 0 and ents.status == "degraded" and ents.note:
            lines.append(f"_{ents.note}_")
        signals = [e for e in ents.signals if e.kind in kinds]
        signals.sort(key=lambda e: -e.severity)
        hidden = 0
        if kinds == ("normal",) and len(signals) > MAX_NORMAL_LINES:
            hidden = len(signals) - MAX_NORMAL_LINES
            signals = signals[:MAX_NORMAL_LINES]
        lines += [_entity_line(e, ents.window.days) for e in signals] or [empty]
        if hidden:
            lines.append(f"- … e mais {hidden} entidade(s) sem anomalia.")
        lines.append("")

    lines += _METHODOLOGY_ANOMALIES
    return fit_summary("\n".join(lines), max_bytes)


# ── forecast ────────────────────────────────────────────────────────────────


def _forecast_calendar(report: ForecastReport, start: date, last: date) -> str | None:
    cal = report.calendar
    levels: Mapping[str, float] = report.platform.level_by_phase
    if cal.phase == "blackout" and cal.blackout_end:
        if start <= cal.blackout_end <= last:
            return (
                f"**Calendário:** o horizonte cruza o fim do defeso ({_d(cal.blackout_end)}) — "
                f"o volume esperado sobe de ~{levels.get('blackout', 0):.0f} para "
                f"~{levels.get('normal', 0):.0f} artigos por dia útil a partir de "
                f"{_dm(cal.blackout_end + timedelta(days=1))}."
            )
        return (
            f"**Calendário:** defeso eleitoral até {_d(cal.blackout_end)} (faltam "
            f"{cal.days_to_end} dias); ~{levels.get('blackout', 0):.0f} artigos por dia útil."
        )
    if cal.phase == "recovery" and cal.recovery_until:
        return (
            f"**Calendário:** recuperação pós-defeso até {_d(cal.recovery_until)}; confiança "
            "reduzida em um nível."
        )
    return None


def _expected(t: ForecastTheme) -> str:
    p = t.projection
    if p is None:
        return "—"
    return f"{p.expected_articles:.0f} ({p.low:.0f}–{p.high:.0f})"


def _windows_cell(t: ForecastTheme) -> str:
    return " · ".join(
        f"{key} {_x(wr.ratio)}" if wr is not None else f"{key} —" for key, wr in t.windows.items()
    )


_METHODOLOGY_FORECAST = [
    "### Metodologia",
    "Razão de share-of-voice sem sobreposição (janela contra o baseline anterior a ela) e "
    "taxa log por dia ln(r)/(B/2); composto 0,5/0,3/0,2 renormalizado nas janelas com "
    "cobertura de classificação; momentum = taxa de 3 dias − taxa de 7 dias (±10% por "
    "semana). Projeção amortecida (φ = 0,9) sobre o volume esperado por dia (perfil de dia "
    "útil, feriado como domingo, nível por fase do calendário), com intervalo de Poisson de "
    "95%.",
]


def render_forecast_markdown(
    report: ForecastReport, *, max_bytes: int | None = SUMMARY_MAX_BYTES
) -> str:
    """Markdown do forecast de tendências (≤ ``max_bytes``; ``None`` = completo)."""
    horizon = int(report.params.get("horizon_days") or 0) or 1
    requested = report.params.get("horizon_days_requested")
    start = report.reference_date
    last = start + timedelta(days=horizon - 1)
    generated = report.generated_at.astimezone(BRT)
    lines = [f"## Forecast de Tendências — Horizonte {horizon} dias ({_dm(start)} → {_d(last)})"]
    if requested is not None and requested != horizon:
        lines.append(f"_Horizonte pedido: {requested} dias; ajustado para {horizon} (1–28)._")
    windows_txt = " · ".join(
        f"{key} (peso {_num(w.effective_weight, 2)})" for key, w in report.windows.items()
    )
    lines.append(
        f"**Janelas móveis até {generated.strftime('%d/%m %H:%M')} (BRT; contagens em UTC):** "
        f"{windows_txt} "
        "· share-of-voice entre os artigos classificados"
    )
    calendar = _forecast_calendar(report, start, last)
    if calendar:
        lines.append(calendar)
    lines.append("")

    warnings = _warnings(report.notices, report.data_status)
    for key, w in report.windows.items():
        if w.status == "unavailable":
            warnings.append(
                f"Janela {key}: indisponível (cobertura de classificação "
                f"{_pct(w.classified_coverage)}); fora do composto."
            )
        elif w.status == "degraded":
            warnings.append(
                f"Janela {key}: degradada (cobertura de classificação "
                f"{_pct(w.classified_coverage)}); confiança no máximo baixa."
            )
    lines += _quote("Avisos", warnings)

    if report.themes:
        lines += [
            f"| Tema | Ritmo (×/semana) | Momentum | Confiança | Artigos esperados "
            f"({horizon}d) | Janelas |",
            "|---|---|---|---|---|---|",
        ]
        for t in report.themes:
            rhythm = _x(t.weekly_multiplier, 2) if t.weekly_multiplier is not None else "—"
            lines.append(
                f"| {t.label} | {rhythm} | {MOMENTUM_PT[t.momentum]} | "
                f"{CONFIDENCE_PT[t.confidence]} | {_expected(t)} | {_windows_cell(t)} |"
            )
    else:
        lines.append("Nenhum tema com dados suficientes nas janelas disponíveis.")
    lines.append("")
    lines += _METHODOLOGY_FORECAST
    return fit_summary("\n".join(lines), max_bytes)


# ── coerência de mensagem ───────────────────────────────────────────────────

DIMENSION_PT = {
    "entities": "Entidades",
    "timing": "Timing (BRT)",
    "framing": "Enquadramento",
    "tone": "Tom",
}
DIMENSION_PT_LOWER = {
    "entities": "entidades",
    "timing": "timing",
    "framing": "enquadramento",
    "tone": "tom",
}


def _articles(n: int) -> str:
    return f"{n} artigo" if n == 1 else f"{n} artigos"


def _hm(moment) -> str:
    return moment.astimezone(BRT).strftime("%d/%m %H:%M")


def _delay(hours: float | None) -> str:
    """Atraso em horas (até 48 h) ou dias; ``1º`` para o primeiro emissor."""
    if hours is None:
        return "—"
    if hours == 0:
        return "1º"
    sign = "+" if hours > 0 else "−"
    value = abs(hours)
    return f"{sign}{value:.0f} h" if value < 48 else f"{sign}{_num(value / 24)} d"


def _agency_label(name: str, key: str) -> str:
    """``Nome (`código`)``; só o código quando o catálogo não deu o nome."""
    return f"`{key}`" if not name or name == key else f"{name} (`{key}`)"


def _agency_row(a: AgencyCoherence) -> str:
    frame = FRAME_LABELS[a.dominant_frame] if a.dominant_frame else "—"
    anchors = "; ".join(x.label for x in a.exclusive_anchors) or "—"
    return (
        f"| {_agency_label(a.agency_name, a.agency_key)} | {a.articles} | "
        f"{_hm(a.first_published_at)} | {_delay(a.delay_hours)} | {frame} | {anchors} |"
    )


def _coherence_header(report: CoherenceReport) -> list[str]:
    subject = report.subject
    if subject.kind == "entity":
        head = f"## Coerência de Mensagem — {subject.label} ({subject.type or 'entidade'} · `{subject.id}`)"
    else:
        head = f"## Coerência de Mensagem — {subject.label} (tema)"
    lines = [head]
    if subject.resolved_by == "search":
        alternatives = "; ".join(
            f"{a.name} (`{a.entity_id}`, {a.article_count or 0} artigos)"
            for a in subject.alternatives
        )
        text = f'_Entidade resolvida pela busca "{subject.query}" (a de maior volume)'
        lines.append(text + (f"; alternativas: {alternatives}._" if alternatives else "._"))
    elif subject.kind == "theme" and subject.query and subject.query != subject.label:
        lines.append(f'_Tema "{subject.query}" → label L1 "{subject.label}"._')
    start, end = _days(report.window)
    s, rep = report.sample, report.republishers
    window = f"**Janela:** {_span(start, end)} ({report.window.days} dias, BRT)"
    if report.index_status in ("unavailable", "no_articles"):
        return [*lines, window, ""]  # sem amostra: nada de emissores nem republicadoras
    line = f"{window} · **Artigos:** {s.found}"
    if s.fetched < s.found:
        line += f" (amostra de {s.fetched})"
    line += (
        f" · **Emissores:** {s.emitters} agências ({s.emitter_articles} artigos) · "
        f"**Republicadoras:** {rep.articles} artigos ({_pct(rep.share)})"
    )
    if report.params.get("agencies"):
        line += f" · **Agências pedidas:** {', '.join(report.params['agencies'])}"
    lines.append(line)
    if s.single_article_agencies:
        lines.append(
            f"_{s.single_article_agencies} agência(s) não republicadora(s) com 1 artigo ficam "
            "fora do índice._"
        )
    lines.append("")
    return lines


def _partial_sample(report: CoherenceReport) -> bool:
    """A amostra não cobre a janela inteira (``SAMPLE_TRUNCATED``: acima de 1000 ou páginas
    com falha; ou índice de busca parcial): a 1ª publicação e o atraso da tabela valem só
    para a amostra (os mesmos casos em que o timing sai do índice)."""
    truncated = any(n.code == "SAMPLE_TRUNCATED" for n in report.notices)
    lagging = any(d.key == "indexing_lag" and d.status != "ok" for d in report.data_status)
    return truncated or lagging


def _coherence_index(report: CoherenceReport) -> list[str]:
    status = report.index_status
    if status == "unavailable":
        return ["### Índice indisponível", f"**Artigos indisponíveis:** {report.index_note}", ""]
    if status == "no_articles":
        return ["### Nenhum artigo na janela", report.index_note or "", ""]
    if status == "insufficient":
        return [
            f"### Índice: insuficiente — {report.index_note}",
            "_A coerência compara ao menos 2 agências não republicadoras com 2 ou mais "
            "artigos na janela._",
            "",
        ]
    weights = "/".join(f"{DIMENSION_WEIGHTS[k] * 100:.0f}" for k in DIMENSION_WEIGHTS)
    cuts = "/".join(_num(c, 1) for c in INDEX_CUTS)
    lines = [
        f"### Índice: {report.index.level}/5 ({_num(report.index.score or 0.0, 2)})",
        "| Dimensão | Valor | Peso | Leitura |",
        "|---|---|---|---|",
    ]
    for d in report.dimensions:
        value = _num(d.value, 2) if d.value is not None else "indisponível"
        weight = _pct(d.effective_weight) if d.effective_weight is not None else "—"
        lines.append(f"| {DIMENSION_PT[d.key]} | {value} | {weight} | {d.detail} |")
    lines += [
        f"_Pesos nominais {weights}, renormalizados entre as dimensões disponíveis; cortes "
        f"{cuts} (provisórios)._",
        "",
    ]
    return lines


def _coherence_warnings(report: CoherenceReport) -> list[str]:
    items = _warnings(report.notices, report.data_status)
    if report.prior is not None and report.prior.truncated_start:
        p = report.prior
        items.append(
            f"Início truncado: a pauta já corria antes da janela ({_num(p.daily_rate)} "
            f"artigos/dia nos {p.window.days} dias anteriores contra "
            f"{_num(p.window_daily_rate)}/dia na janela); o atraso conta a partir do início "
            "da janela."
        )
    if report.sample.mock_summaries_ignored:
        items.append(
            f"{report.sample.mock_summaries_ignored} resumo(s) [MOCK] (texto de teste) "
            "ignorado(s) no enquadramento."
        )
    if report.subject.kind == "theme" and any(
        n.code == "THEMES_UNCLASSIFIED" for n in report.notices
    ):
        items.append(
            "Classificação de temas incompleta na janela: o filtro por tema perde artigos. "
            "Prefira `entity_id` (programa, política ou órgão via gobus_resolve_entity)."
        )
    items += report.notes
    return items


def render_coherence_markdown(
    report: CoherenceReport, *, max_bytes: int | None = SUMMARY_MAX_BYTES
) -> str:
    """Markdown da coerência de mensagem (≤ ``max_bytes``; ``None`` = completo)."""
    lines = _coherence_header(report) + _coherence_index(report)

    if report.agencies:
        first = "1ª na amostra (BRT)" if _partial_sample(report) else "1ª publicação (BRT)"
        lines += [
            "### Por agência",
            f"| Agência | Artigos | {first} | Atraso | Enquadramento | Âncoras exclusivas |",
            "|---|---|---|---|---|---|",
            *(_agency_row(a) for a in report.agencies),
        ]
        if report.agencies_omitted:
            lines.append(f"_… e mais {report.agencies_omitted} emissor(es) de menor volume._")
        lines.append("")

    if report.index_status == "scored":
        lines.append("### Âncoras compartilhadas")
        lines += [
            f"- {a.label} ({a.type or '—'}) — {a.agencies} agências" for a in report.shared_anchors
        ] or ["Nenhuma entidade em comum entre a maioria dos emissores."]
        lines.append("")
        if report.divergences:
            lines.append("### Divergências")
            for d in report.divergences:
                a, b = d.agencies
                weakest = (
                    f" — mais fraca: {DIMENSION_PT_LOWER[d.weakest]} "
                    f"({_num(d.by_dimension[d.weakest] or 0.0, 2)})"
                    if d.weakest
                    else ""
                )
                lines.append(f"- `{a}` × `{b}`: {_num(d.similarity, 2)}{weakest}")
            lines.append("")

    if report.index_status not in ("unavailable", "no_articles"):
        lines.append("### Republicadoras")
        if report.republishers.agencies:
            lines.append("_Fora do índice: republicam conteúdo de outras agências._")
            for r in report.republishers.agencies:
                delay = (
                    f" ({_delay(r.delay_hours)} do 1º emissor)" if r.delay_hours is not None else ""
                )
                lines.append(
                    f"- {_agency_label(r.agency_name, r.agency_key)}: {_articles(r.articles)} · 1ª em "
                    f"{_hm(r.first_published_at)}{delay}"
                )
        else:
            lines.append("Nenhuma republicadora na janela.")
        lines.append("")

    warnings = _coherence_warnings(report)
    if warnings:
        lines += ["### Avisos de dados", *(f"> - {w}" for w in warnings)]
    return fit_summary("\n".join(lines).rstrip() + "\n", max_bytes)
