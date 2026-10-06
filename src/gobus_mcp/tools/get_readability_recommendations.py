"""Diagnóstico de legibilidade (Flesch) por agência, com recomendações de estilo.

Dois modos:
- **ranking** (sem ``agency_key``): agências ativas do catálogo, ordenadas pelo Flesch;
- **agência**: média da agência, benchmark da Agência Brasil na mesma janela, pior e
  melhor artigo de uma amostra (``articles``, escolhidos no cliente) e 3 recomendações.

Null nunca vira 0.0; se o dado parou, a análise usa a **janela efetiva** (último mês com
dado) e avisa. ``build_readability_payload`` faz o I/O e devolve o payload pydantic;
``render_readability_markdown`` é puro (o Markdown também vai em ``summary``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import (
    DateRange,
    brt_bounds,
    calendar_context,
    closed_window,
    now_brt,
    reference_date,
)
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import notices_for
from gobus_mcp.payloads.readability import (
    AgencyReadabilityRow,
    ArticleReadability,
    DayRange,
    ReadabilityCoverageInfo,
    ReadabilityReport,
    flesch_bands,
)
from gobus_mcp.readability import (
    TARGET_INSTITUTIONAL,
    TARGET_SERVICE,
    FleschValue,
    clamp_flesch,
    describe_flesch,
    flesch_band,
)
from gobus_mcp.readability_data import (
    AgencyReadability,
    ReadabilityWindow,
    aggregate_agencies,
    load_readability_window,
    rank_agencies,
)

BENCHMARK_AGENCY = "agencia_brasil"
ACTIVE_LIMIT = 40  # agências ativas consideradas no ranking
SAMPLE_LIMIT = 100  # artigos mais recentes da janela efetiva (modo agência)
MAX_DAYS = 730

_ARTICLES_QUERY = """
query ReadabilityArticles(
  $agencies: [String!]!, $startDate: String!, $endDate: String!, $limit: Int!
) {
  articles(
    page: 1
    limit: $limit
    filter: {agencies: $agencies, startDate: $startDate, endDate: $endDate}
    sort: DATE
  ) {
    found
    articles {
      uniqueId
      title
      url
      publishedAt
      features { readabilityFlesch wordCount }
    }
  }
}
"""

_RECOMMENDATIONS: dict[str, list[str]] = {
    "very_hard": [
        "1. **Frases curtas:** meta de no máximo 20 palavras por frase; cada ponto final "
        "melhora o índice.",
        "2. **Palavras simples:** prefira 'fazer' a 'realizar', 'ver' a 'verificar', "
        "'dizer' a 'declarar'; explique siglas e termos técnicos na primeira ocorrência.",
        "3. **Lead direto e voz ativa:** o quê, quem e quando na primeira frase; troque a "
        "voz passiva pela ativa.",
    ],
    "hard": [
        "1. **Frases mais curtas:** divida frases com mais de 25 palavras; você está a "
        "caminho da meta de serviço (≥50).",
        "2. **Vocabulário acessível:** revise os termos mais frequentes e troque os mais "
        "complexos.",
        "3. **Teste com o cidadão:** peça a um leitor sem formação técnica para ler antes "
        "de publicar.",
    ],
    "medium": [
        "1. **Mantenha o padrão:** o índice já atinge a meta de serviço (≥50); continue "
        "priorizando frases curtas.",
        "2. **Consistência:** garanta que toda a equipe siga o mesmo guia de estilo.",
        "3. **Monitore regressões:** textos técnicos tendem a puxar o índice para baixo.",
    ],
    "easy": [
        "1. **Referência interna:** o texto é fácil de ler; compartilhe o padrão com outras "
        "equipes.",
        "2. **Precisão:** confira se a simplificação não omitiu prazos, valores ou condições.",
        "3. **Monitore regressões:** acompanhe o índice mês a mês.",
    ],
}


# ── conversões para o payload ───────────────────────────────────────────────


def _agency_row(item: AgencyReadability) -> AgencyReadabilityRow:
    band = flesch_band(item.flesch)
    value = item.flesch.value
    return AgencyReadabilityRow(
        agency_key=item.code,
        agency_name=item.name,
        is_republisher=item.is_republisher,
        article_count=item.article_count,
        articles_with_data=item.articles_with_data,
        flesch=None if value is None else round(value, 2),
        flesch_raw=None if item.flesch.raw is None else round(item.flesch.raw, 2),
        band=band.key if band else None,
        band_label=band.label if band else None,
        gap_to_target=None if value is None else round(value - TARGET_SERVICE, 2),
        avg_word_count=None if item.avg_word_count is None else round(item.avg_word_count, 1),
    )


def _article_row(article: dict) -> ArticleReadability:
    features = article.get("features") or {}
    fv = clamp_flesch(features.get("readabilityFlesch"))
    band = flesch_band(fv)
    return ArticleReadability(
        unique_id=article.get("uniqueId") or "",
        title=article.get("title") or "Sem título",
        url=article.get("url"),
        published_at=article.get("publishedAt"),
        flesch=fv.value,
        flesch_raw=fv.raw,
        band=band.key if band else None,
        band_label=band.label if band else None,
        word_count=features.get("wordCount"),
    )


def _flesch_of(row: AgencyReadabilityRow | ArticleReadability) -> FleschValue:
    """Valor exibido (limitado) e bruto de uma linha do payload."""
    if row.flesch is None:
        return FleschValue(None, None, False)
    raw = row.flesch if row.flesch_raw is None else row.flesch_raw
    return FleschValue(raw, row.flesch, round(raw, 2) != round(row.flesch, 2))


def _coverage_info(window: ReadabilityWindow) -> ReadabilityCoverageInfo:
    c = window.coverage
    return ReadabilityCoverageInfo(
        periods_total=c.periods_total,
        periods_with_data=c.periods_with_data,
        articles_total=c.articles_total,
        articles_in_periods_with_data=c.articles_in_periods_with_data,
        last_period_with_data=c.last_period_with_data,
    )


def _status(window: ReadabilityWindow, has_data: bool) -> str:
    if window.effective.effective is None or not has_data:
        return "unavailable"
    if window.effective.shifted or window.data_status.status != "ok":
        return "partial"
    return "ok"


# ── builder ─────────────────────────────────────────────────────────────────


def _requested_window(days: int, date_to: date | None, today: date) -> DateRange:
    if date_to is None:
        return closed_window(days, today)
    return DateRange(date_to - timedelta(days=days - 1), date_to)


def _error_report(
    *, mode: str, error: str, params: dict, now: datetime, today: date
) -> ReadabilityReport:
    report = ReadabilityReport(
        summary="",
        status="unavailable",
        generated_at=now,
        reference_date=today,
        params=params,
        calendar=calendar_context(today),
        data_status=[],
        notices=[],
        mode=mode,
        error=error,
        bands=flesch_bands(),
        requested_window=None,
        effective_window=None,
        coverage=None,
    )
    return report.model_copy(update={"summary": render_readability_markdown(report)})


async def build_readability_payload(
    client: GobusGraphQLClient,
    *,
    agency_key: str | None = None,
    days: int = 90,
    limit: int = 10,
    date_to: str | None = None,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> ReadabilityReport:
    """Monta o ``ReadabilityReport`` (ranking ou agência). Nunca levanta por parâmetro
    inválido: devolve ``status="unavailable"`` com ``error``."""
    catalog = catalog or AgencyCatalog(client)
    now = now or now_brt()
    today = reference_date(now)
    days = max(1, min(int(days), MAX_DAYS))
    limit = max(1, min(int(limit), 50))
    mode = "agency" if agency_key else "ranking"
    params = {"agency_key": agency_key or None, "days": days, "limit": limit, "date_to": date_to}

    end: date | None = None
    if date_to:
        try:
            end = date.fromisoformat(date_to)
        except ValueError:
            return _error_report(
                mode=mode,
                error=f"date_to inválida: '{date_to}' (use AAAA-MM-DD).",
                params=params,
                now=now,
                today=today,
            )
    requested = _requested_window(days, end, today)

    code: str | None = None
    if agency_key:
        check = await catalog.validate(agency_key)
        if not check.ok:
            return _error_report(
                mode=mode, error=check.message, params=params, now=now, today=today
            )
        code = check.code
        params["agency_key"] = code
        agencies = [code] if code == BENCHMARK_AGENCY else [code, BENCHMARK_AGENCY]
    else:
        # topAgencies conta a partir de hoje: o intervalo precisa cobrir a janela pedida
        active_days = max(days, (today - requested.start).days)
        agencies = await catalog.active(active_days, limit=max(ACTIVE_LIMIT, limit))
        if BENCHMARK_AGENCY not in agencies:
            agencies = [*agencies, BENCHMARK_AGENCY]

    window = await load_readability_window(client, agencies, requested)
    all_agencies = await catalog.all()
    names = {a.code: a.name for a in all_agencies}
    republishers = await catalog.republishers()
    # sem janela efetiva, as contagens de artigos vêm da janela pedida (Flesch todo nulo)
    rows = window.rows if window.effective.effective else window.requested_rows
    items = aggregate_agencies(rows, names=names, republishers=republishers, codes=agencies)
    by_code = {a.code: a for a in items}
    benchmark_item = by_code.get(BENCHMARK_AGENCY)
    benchmark = _agency_row(benchmark_item) if benchmark_item and benchmark_item.has_data else None

    fields: dict = {}
    if code is None:
        with_data, without = rank_agencies(items)
        fields["agencies"] = [_agency_row(a) for a in with_data[:limit]]
        fields["agencies_without_data"] = [_agency_row(a) for a in without]
        has_data = bool(with_data)
    else:
        item = by_code[code]
        fields["agency"] = _agency_row(item)
        has_data = item.has_data
        band = flesch_band(item.flesch)
        fields["recommendations"] = list(_RECOMMENDATIONS[band.key]) if band else []
        if has_data and window.effective.effective is not None:
            start, stop = brt_bounds(window.effective.effective)
            data = await client.execute(
                _ARTICLES_QUERY,
                {"agencies": [code], "startDate": start, "endDate": stop, "limit": SAMPLE_LIMIT},
            )
            result = data.get("articles") or {}
            sample = [
                a
                for a in result.get("articles") or []
                if (a.get("features") or {}).get("readabilityFlesch") is not None
            ]
            fields["sample_found"] = result.get("found")
            fields["sample_size"] = len(sample)
            if sample:

                def key(a: dict) -> tuple[float, float]:
                    fv = clamp_flesch(a["features"]["readabilityFlesch"])
                    return fv.value, fv.raw

                fields["worst_article"] = _article_row(min(sample, key=key))
                fields["best_article"] = _article_row(max(sample, key=key))

    data_status = [window.data_status]
    effective = window.effective.effective
    report = ReadabilityReport(
        summary="",
        status=_status(window, has_data),
        generated_at=now,
        reference_date=today,
        params=params,
        calendar=calendar_context(today),
        data_status=data_status,
        notices=notices_for(data_status),
        mode=mode,
        bands=flesch_bands(),
        requested_window=DayRange.of(requested),
        effective_window=DayRange.of(effective) if effective else None,
        window_shifted=window.effective.shifted,
        window_note=window.effective.note,
        coverage=_coverage_info(window),
        benchmark=benchmark,
        **fields,
    )
    return report.model_copy(update={"summary": render_readability_markdown(report)})


# ── render ──────────────────────────────────────────────────────────────────


def _d(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _span(r: DayRange) -> str:
    return f"{_d(r.start)}–{_d(r.end)} ({r.days} dias)"


def _short(row: AgencyReadabilityRow) -> str:
    """``"0.0 (bruto -22.9)"`` — para a coluna da tabela."""
    if row.flesch is None:
        return "—"
    text = f"{row.flesch:.1f}"
    if row.flesch_raw is not None and round(row.flesch_raw, 1) != round(row.flesch, 1):
        text += f" (bruto {row.flesch_raw:.1f})"
    return text


def _agency_label(row: AgencyReadabilityRow) -> str:
    return f"{row.agency_name} (republicadora)" if row.is_republisher else row.agency_name


def _window_lines(report: ReadabilityReport) -> list[str]:
    lines = []
    if report.window_shifted and report.effective_window:
        lines.append(
            f"> **Janela efetiva:** {_span(report.effective_window)} — {report.window_note}. "
            "A janela pedida não tem Flesch até o fim."
        )
    elif report.effective_window is None:
        lines.append(f"> **Legibilidade indisponível:** {report.window_note}.")
    for status in report.data_status:
        if status.status != "ok":
            lines.append(f"> {status.message}")
    return lines


def _benchmark_line(report: ReadabilityReport) -> str | None:
    if report.benchmark is None:
        return None
    flesch = describe_flesch(_flesch_of(report.benchmark))
    return f"**Benchmark interno (Agência Brasil, mesma janela):** {flesch}"


def _footer() -> list[str]:
    return [
        f"**Meta:** ≥{TARGET_SERVICE:.0f} para serviço ao cidadão · "
        f"≥{TARGET_INSTITUTIONAL:.0f} para institucional",
        "_Escala: Flesch com a fórmula inglesa do textstat, limitado a 0–100 (o valor bruto "
        "aparece quando foi limitado)._",
    ]


def _render_ranking(report: ReadabilityReport) -> list[str]:
    lines = [f"# Ranking de Legibilidade — {_span(report.requested_window)}"]
    window_lines = _window_lines(report)
    if window_lines:
        lines += ["", *window_lines]
    if report.agencies:
        lines += [
            "",
            "| # | Agência | Flesch | Nível | Artigos (com Flesch) | Gap até 50 |",
            "|---|---------|--------|-------|----------------------|------------|",
        ]
        for i, row in enumerate(report.agencies, 1):
            lines.append(
                f"| {i} | {_agency_label(row)} | {_short(row)} | {row.band_label} | "
                f"{row.article_count} ({row.articles_with_data}) | {row.gap_to_target:+.1f} |"
            )
    if report.agencies_without_data:
        listed = ", ".join(
            f"{row.agency_name} ({row.article_count} artigos)"
            for row in report.agencies_without_data[:15]
        )
        extra = len(report.agencies_without_data) - 15
        if extra > 0:
            listed += f" e mais {extra}"
        lines.append(
            f"\n**Sem dado de legibilidade na janela ({len(report.agencies_without_data)}):** "
            f"{listed}"
        )
    lines.append("")
    benchmark = _benchmark_line(report)
    if benchmark:
        lines.append(benchmark)
    lines.extend(_footer())
    return lines


def _article_line(label: str, art: ArticleReadability) -> str:
    when = (art.published_at or "")[:10]
    title = f"[{art.title}]({art.url})" if art.url else art.title
    words = f" · {art.word_count} palavras" if art.word_count is not None else ""
    flesch = describe_flesch(_flesch_of(art))
    return f"- **{label}:** {title} — {when} · Flesch {flesch}{words} · `{art.unique_id}`"


def _render_agency(report: ReadabilityReport) -> list[str]:
    row = report.agency
    lines = [f"# Diagnóstico de Legibilidade: {row.agency_name} (`{row.agency_key}`)\n"]
    lines.append(f"**Janela pedida:** {_span(report.requested_window)}")
    lines.extend(_window_lines(report))
    words = f"{row.avg_word_count:.0f}" if row.avg_word_count is not None else "indisponível"
    lines.append(
        f"\n**Flesch médio:** {describe_flesch(_flesch_of(row))} · "
        f"**Artigos na janela:** {row.article_count} ({row.articles_with_data} com Flesch) · "
        f"**Palavras/artigo:** {words}"
    )
    if row.gap_to_target is not None:
        lines.append(f"**Gap até a meta de serviço (50):** {row.gap_to_target:+.1f}")
    benchmark = _benchmark_line(report)
    if benchmark:
        lines.append(benchmark)

    if report.worst_article or report.best_article:
        lines.append(
            f"\n## Artigos da janela (amostra dos {SAMPLE_LIMIT} mais recentes: "
            f"{report.sample_size} com Flesch)\n"
        )
        if report.worst_article:
            lines.append(_article_line("Pior", report.worst_article))
        if report.best_article:
            lines.append(_article_line("Melhor", report.best_article))

    if report.recommendations:
        lines.append("\n## Recomendações de Estilo\n")
        lines.extend(report.recommendations)
    elif row.flesch is None:
        lines.append("\nSem dado de legibilidade para esta agência — recomendações indisponíveis.")
    lines.append("")
    lines.extend(_footer())
    return lines


def render_readability_markdown(report: ReadabilityReport) -> str:
    """Markdown do relatório (puro: não faz I/O)."""
    if report.error:
        title = "Diagnóstico de Legibilidade" if report.mode == "agency" else "Legibilidade"
        return f"# {title}\n\n{report.error}"
    if report.mode == "agency" and report.agency is not None:
        return "\n".join(_render_agency(report))
    return "\n".join(_render_ranking(report))


async def get_readability_recommendations(
    agency_key: str | None,
    client: GobusGraphQLClient,
    days: int = 90,
    limit: int = 10,
    *,
    date_to: str | None = None,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> str:
    """Markdown do diagnóstico de legibilidade (ranking sem ``agency_key``)."""
    report = await build_readability_payload(
        client,
        agency_key=agency_key,
        days=days,
        limit=limit,
        date_to=date_to,
        catalog=catalog,
        now=now,
    )
    return report.summary
