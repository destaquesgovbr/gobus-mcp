"""Nota editorial (0–10) de um artigo, comparada ao benchmark da própria agência.

Três dimensões (pesos 50/30/20): legibilidade (Flesch pt-BR limitado a [0, 100]; nota 10 na
meta de serviço 50), concisão (palavras contra a mediana da agência) e densidade de
entidades (por 100 palavras).

Escala: o Flesch pt-BR do artigo; sem ele, o inglês (legado), com aviso
``READABILITY_LEGACY_SCALE``. O benchmark usa a mesma escala do artigo. Com ``compare_with``,
os dois artigos usam a escala comum (``common_scale``: o pt-BR se ambos o têm; senão, o
inglês para os dois); sem escala comum, cada lado fica na sua, com aviso.

- **refused**: sem Flesch ou sem wordCount → "Nota indisponível" (nunca uma nota neutra);
- **partial**: sem benchmark de concisão (amostra < 10) → média renormalizada;
- **scored**: as três dimensões.

O benchmark é uma amostra ``articles`` da agência (e da Agência Brasil) nos 90 dias antes
da publicação do artigo, com mediana calculada no cliente. Da mesma amostra saem até 2
sugestões de comparação (maior Flesch da agência e da Agência Brasil); ``compare_with``
pontua um segundo artigo do mesmo jeito (app ``ui://article-scorecard``: lado a lado).
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta
from typing import NamedTuple

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import calendar_context, now_brt, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import notices_for, share_status
from gobus_mcp.payloads.common import DataStatus, Notice
from gobus_mcp.payloads.readability import DayRange, flesch_bands
from gobus_mcp.payloads.scorecard import (
    Light,
    ScoreBenchmark,
    ScoreComparison,
    ScoredArticle,
    ScoreDimension,
    ScoreReport,
    SuggestedComparison,
)
from gobus_mcp.readability import (
    PTBR_SCALE,
    SCALES,
    FleschScale,
    article_flesch,
    clamp_flesch,
    common_scale,
    describe_flesch,
    legacy_scale_notice,
    readability_score,
)
from gobus_mcp.schema_compat import FLESCH_PTBR, execute_compatible

BENCHMARK_AGENCY = "agencia_brasil"
BENCHMARK_DAYS = 90
SAMPLE_LIMIT = 250
MIN_SAMPLE = 10
LIGHT_GREEN = 7.0  # nota ≥ 7 → verde
LIGHT_YELLOW = 4.0  # nota ≥ 4 → amarelo; abaixo, vermelho
MAX_SUGGESTIONS = 2
WEIGHTS = {"readability": 0.5, "conciseness": 0.3, "entity_density": 0.2}
LABELS = {
    "readability": "Legibilidade",
    "conciseness": "Concisão",
    "entity_density": "Densidade de entidades",
}

_ARTICLE_TEMPLATE = """
query ScoreArticle__SUFFIX__($uniqueId: String!) {
  article(uniqueId: $uniqueId) {
    uniqueId
    title
    url
    agency
    agencyName
    publishedAt
    features {
      readabilityFlesch__PTBR__
      wordCount
      entities { type }
    }
  }
}
"""

_BENCHMARK_TEMPLATE = """
query ScoreArticleBenchmark__SUFFIX__(
  $agencies: [String!]!, $startDate: String!, $endDate: String!, $limit: Int!
) {
  ag: articles(
    page: 1
    limit: $limit
    filter: {agencies: $agencies, startDate: $startDate, endDate: $endDate}
    sort: DATE
  ) {
    found
    articles { uniqueId title publishedAt features { readabilityFlesch__PTBR__ wordCount } }
  }
  ab: articles(
    page: 1
    limit: $limit
    filter: {agencies: ["agencia_brasil"], startDate: $startDate, endDate: $endDate}
    sort: DATE
  ) {
    found
    articles { uniqueId title publishedAt features { readabilityFlesch__PTBR__ wordCount } }
  }
}
"""


def _ptbr(template: str, *, legacy: bool) -> str:
    """Query nova (com o Flesch pt-BR, GQL-1) ou a antiga (``…Legacy``, sem ele)."""
    if legacy:
        return template.replace("__SUFFIX__", "Legacy").replace("__PTBR__", "")
    return template.replace("__SUFFIX__", "").replace("__PTBR__", " readabilityFleschPtbr")


_ARTICLE_QUERY = _ptbr(_ARTICLE_TEMPLATE, legacy=False)
_ARTICLE_LEGACY_QUERY = _ptbr(_ARTICLE_TEMPLATE, legacy=True)
_BENCHMARK_QUERY = _ptbr(_BENCHMARK_TEMPLATE, legacy=False)
_BENCHMARK_LEGACY_QUERY = _ptbr(_BENCHMARK_TEMPLATE, legacy=True)


# ── dimensões (puras) ───────────────────────────────────────────────────────


def conciseness_score(word_count: int | None, median_word_count: float | None) -> float | None:
    """Nota 0–10: palavras do artigo contra a mediana da agência (None sem base)."""
    if not word_count or not median_word_count:
        return None
    ratio = word_count / median_word_count
    if ratio <= 0.8:
        return 10.0
    if ratio <= 1.0:
        return 8.0
    if ratio <= 1.3:
        return 6.0
    if ratio <= 1.6:
        return 4.0
    return 2.0


def entity_density(entity_count: int, word_count: int | None) -> float | None:
    """Entidades por 100 palavras (None sem wordCount)."""
    if not word_count or word_count <= 0:
        return None
    return entity_count * 100 / word_count


def entity_density_score(density: float | None) -> float | None:
    if density is None:
        return None
    if density >= 2:
        return 8.0
    if density >= 1:
        return 6.0
    if density >= 0.5:
        return 4.0
    return 2.0


def overall_score(scores: dict[str, float | None]) -> float | None:
    """Média ponderada **renormalizada** das dimensões disponíveis."""
    available = {k: s for k, s in scores.items() if s is not None}
    total_weight = sum(WEIGHTS[k] for k in available)
    if not total_weight:
        return None
    return round(sum(WEIGHTS[k] * s for k, s in available.items()) / total_weight, 1)


def score_light(score: float | None) -> Light:
    """Semáforo de uma nota 0–10 (cinza sem nota)."""
    if score is None:
        return "gray"
    if score >= LIGHT_GREEN:
        return "green"
    if score >= LIGHT_YELLOW:
        return "yellow"
    return "red"


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if len(values) >= MIN_SAMPLE else None


# ── benchmark ───────────────────────────────────────────────────────────────


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _benchmark(
    result: dict | None,
    *,
    code: str,
    name: str,
    exclude: str,
    scale: FleschScale = PTBR_SCALE,
) -> tuple[ScoreBenchmark, int, int]:
    """Benchmark da amostra e ``(com Flesch, total)`` para o data_status."""
    result = result or {}
    articles = [a for a in result.get("articles") or [] if a.get("uniqueId") != exclude]
    words: list[float] = []
    flesch: list[float] = []
    days = []
    for art in articles:
        feats = art.get("features") or {}
        used = False
        if feats.get("wordCount") is not None:
            words.append(feats["wordCount"])
            used = True
        if feats.get(scale.article_field) is not None:
            flesch.append(clamp_flesch(feats[scale.article_field]).value)
            used = True
        published = _parse_dt(art.get("publishedAt"))
        if used and published is not None:
            days.append(published.date())
    window = (
        DayRange(start=min(days), end=max(days), days=(max(days) - min(days)).days + 1)
        if days
        else None
    )
    bench = ScoreBenchmark(
        agency_key=code,
        agency_name=name,
        found=result.get("found"),
        sample_size=len(words),
        flesch_sample_size=len(flesch),
        median_word_count=_median(words),
        median_flesch=None if (m := _median(flesch)) is None else round(m, 1),
        window=window,
    )
    return bench, len(flesch), len(articles)


def _suggestion(
    result: dict | None,
    *,
    code: str,
    name: str,
    exclude: set[str],
    reason: str,
    scale: FleschScale = PTBR_SCALE,
) -> SuggestedComparison | None:
    """Artigo de maior Flesch (limitado; o bruto desempata) da amostra, fora ``exclude``."""
    field = scale.article_field
    candidates = [
        a
        for a in (result or {}).get("articles") or []
        if a.get("uniqueId")
        and a["uniqueId"] not in exclude
        and (a.get("features") or {}).get(field) is not None
    ]
    if not candidates:
        return None

    def key(a: dict) -> tuple[float, float]:
        fv = clamp_flesch(a["features"][field])
        return fv.value, fv.raw

    best = max(candidates, key=key)
    return SuggestedComparison(
        unique_id=best["uniqueId"],
        title=best.get("title") or best["uniqueId"],
        agency_key=code,
        agency_name=name,
        flesch=clamp_flesch(best["features"][field]).value,
        word_count=best["features"].get("wordCount"),
        reason=reason,
    )


# ── builder ─────────────────────────────────────────────────────────────────


def _dimension(key: str, score: float | None, value, reference, detail: str) -> ScoreDimension:
    return ScoreDimension(
        key=key,
        label=LABELS[key],
        weight=WEIGHTS[key],
        effective_weight=None,
        score=score,
        value=value,
        reference=reference,
        detail=detail,
        light=score_light(score),
    )


def _with_effective_weights(dims: list[ScoreDimension]) -> list[ScoreDimension]:
    total = sum(d.weight for d in dims if d.score is not None)
    return [
        d.model_copy(
            update={
                "effective_weight": round(d.weight / total, 3)
                if total and d.score is not None
                else None
            }
        )
        for d in dims
    ]


class _Scored(NamedTuple):
    report: ScoreReport  # ainda sem summary
    bench_data: dict  # amostras ``ag``/``ab`` (base das sugestões)
    name: str
    ab_name: str
    scale: FleschScale


class _Fetched(NamedTuple):
    """Dados de um artigo para pontuar: as amostras trazem os dois Flesch, então a escala
    pode ser escolhida depois (a comum aos dois lados de um ``compare_with``)."""

    unique_id: str
    art: dict
    bench_data: dict  # amostras ``ag``/``ab``; vazio sem data de publicação ou agência
    name: str
    ab_name: str

    @property
    def features(self) -> dict:
        return self.art.get("features") or {}


async def _fetch_one(
    client: GobusGraphQLClient, unique_id: str, *, catalog: AgencyCatalog
) -> _Fetched | None:
    """Artigo, nomes do catálogo e amostras do benchmark; ``None`` se o artigo não existe."""
    data, _ = await execute_compatible(
        client, FLESCH_PTBR, _ARTICLE_QUERY, _ARTICLE_LEGACY_QUERY, {"uniqueId": unique_id}
    )
    art = data.get("article")
    if not art:
        return None
    code = art.get("agency") or ""
    name, ab_name = await asyncio.gather(
        catalog.display_name(code, art.get("agencyName")),
        catalog.display_name(BENCHMARK_AGENCY, "Agência Brasil"),
    )
    published = _parse_dt(art.get("publishedAt"))
    bench_data: dict = {}
    if published is not None and code:
        bench_data, _ = await execute_compatible(
            client,
            FLESCH_PTBR,
            _BENCHMARK_QUERY,
            _BENCHMARK_LEGACY_QUERY,
            {
                "agencies": [code],
                "startDate": (published - timedelta(days=BENCHMARK_DAYS)).isoformat(),
                "endDate": published.isoformat(),
                "limit": SAMPLE_LIMIT,
            },
        )
    return _Fetched(unique_id, art, bench_data, name, ab_name)


def _score_one(fetched: _Fetched, *, now: datetime, scale: FleschScale | None = None) -> _Scored:
    """Pontua um artigo na escala dada (padrão: a do próprio artigo, ``article_flesch``);
    o benchmark e as sugestões seguem a mesma escala."""
    today = reference_date(now)
    unique_id, art, bench_data, name, ab_name = fetched
    features = fetched.features
    raw_flesch, scale = article_flesch(features, scale)
    fv = clamp_flesch(raw_flesch)
    word_count = features.get("wordCount")
    entity_count = len(features.get("entities") or [])
    code = art.get("agency") or ""

    published = _parse_dt(art.get("publishedAt"))
    benchmark = reference = None
    data_status: list[DataStatus] = []
    if published is not None and code:
        benchmark, with_flesch, total = _benchmark(
            bench_data.get("ag"), code=code, name=name, exclude=unique_id, scale=scale
        )
        reference, _, _ = _benchmark(
            bench_data.get("ab"),
            code=BENCHMARK_AGENCY,
            name=ab_name,
            exclude=unique_id,
            scale=scale,
        )
        if total:
            data_status = [
                share_status("readability", with_flesch, total),
                share_status("word_count", benchmark.sample_size, total),
            ]

    median_wc = benchmark.median_word_count if benchmark else None
    density = entity_density(entity_count, word_count)
    scores = {
        "readability": readability_score(fv),
        "conciseness": conciseness_score(word_count, median_wc),
        "entity_density": entity_density_score(density),
    }
    flags: list[str] = []
    refusal = None
    if fv.value is None or not word_count:
        missing = [
            label
            for label, absent in (
                ("Flesch", fv.value is None),
                ("contagem de palavras", not word_count),
            )
            if absent
        ]
        refusal = (
            f"artigo sem {' e sem '.join(missing)} — o pipeline de features não calculou as "
            "métricas deste artigo, então não há base para uma nota"
        )
        score_status, overall, status = "refused", None, "unavailable"
    else:
        overall = overall_score(scores)
        if scores["conciseness"] is None:
            score_status, status = "partial", "partial"
            flags.append("conciseness_without_benchmark")
        else:
            score_status, status = "scored", "ok"
    if fv.clamped:
        flags.append("readability_clamped")

    dims = [
        _dimension(
            "readability",
            scores["readability"],
            fv.value,
            None,
            f"{scale.short} {describe_flesch(fv)}",
        ),
        _dimension(
            "conciseness",
            scores["conciseness"],
            word_count,
            median_wc,
            (
                f"{word_count} palavras"
                if word_count is not None
                else "contagem de palavras indisponível"
            )
            + (
                f" (mediana da agência: {median_wc:.0f})"
                if median_wc is not None
                else " (sem benchmark da agência)"
            ),
        ),
        _dimension(
            "entity_density",
            scores["entity_density"],
            None if density is None else round(density, 2),
            None,
            f"{entity_count} entidades"
            + (f" ({density:.1f} por 100 palavras)" if density is not None else ""),
        ),
    ]
    if score_status == "refused":
        dims = [d.model_copy(update={"score": None, "light": "gray"}) for d in dims]

    notices = notices_for(data_status)
    legacy = legacy_scale_notice(scale) if fv.value is not None else None
    if legacy is not None:
        notices.append(legacy)
    report = ScoreReport(
        summary="",
        status=status,
        generated_at=now,
        reference_date=today,
        params={"unique_id": unique_id},
        calendar=calendar_context(today),
        data_status=data_status,
        notices=notices,
        scale=scale.id,
        scale_label=scale.label,
        scale_fallback=scale.legacy and fv.value is not None,
        score_status=score_status,
        overall=overall,
        overall_light=score_light(overall),
        refusal_reason=refusal,
        bands=flesch_bands(),
        article=ScoredArticle(
            unique_id=art.get("uniqueId") or unique_id,
            title=art.get("title") or unique_id,
            url=art.get("url"),
            agency_key=code,
            agency_name=name,
            published_at=art.get("publishedAt"),
            flesch=fv.value,
            flesch_raw=fv.raw,
            word_count=word_count,
            entity_count=entity_count,
        ),
        dimensions=_with_effective_weights(dims),
        benchmark=benchmark,
        reference_benchmark=reference,
        flags=flags,
    )
    return _Scored(report, bench_data, name, ab_name, scale)


def _suggestions(scored: _Scored, exclude: set[str]) -> list[SuggestedComparison]:
    found = [
        _suggestion(
            scored.bench_data.get("ag"),
            code=scored.report.article.agency_key,
            name=scored.name,
            exclude=exclude,
            reason=f"maior Flesch da amostra de {scored.name} nos {BENCHMARK_DAYS} dias antes",
            scale=scored.scale,
        ),
        _suggestion(
            scored.bench_data.get("ab"),
            code=BENCHMARK_AGENCY,
            name=scored.ab_name,
            exclude=exclude,
            reason=f"maior Flesch de {scored.ab_name} (referência) na mesma janela",
            scale=scored.scale,
        ),
    ]
    out, seen = [], set()
    for item in found:
        if item is not None and item.unique_id not in seen:
            seen.add(item.unique_id)
            out.append(item)
    return out[:MAX_SUGGESTIONS]


def _comparison(report: ScoreReport) -> ScoreComparison:
    return ScoreComparison(
        score_status=report.score_status,
        overall=report.overall,
        overall_light=report.overall_light,
        refusal_reason=report.refusal_reason,
        article=report.article,
        dimensions=report.dimensions,
        benchmark=report.benchmark,
        scale=report.scale,
        scale_label=report.scale_label,
        scale_fallback=report.scale_fallback,
    )


def _pair_notice(main: _Fetched, other: _Fetched, common: FleschScale | None) -> Notice | None:
    """Aviso de escala de um ``compare_with`` quando o pt-BR falta em só um dos lados
    (substitui o aviso de reserva do artigo): os dois foram para a fórmula inglesa, ou,
    sem escala comum, cada lado ficou na sua."""
    has_ptbr = [d.features.get(PTBR_SCALE.article_field) is not None for d in (main, other)]
    if common is None:
        mine, theirs = (
            article_flesch(main.features)[1].short,
            article_flesch(other.features)[1].short,
        )
        return Notice(
            code="READABILITY_LEGACY_SCALE",
            severity="warn",
            message=(
                f"Escalas diferentes na comparação: este artigo tem só o {mine} e o "
                f"comparado, só o {theirs}. A legibilidade de um não é comparável à do "
                "outro (a nota de legibilidade e o Flesch de cada lado usam a sua escala)."
            ),
            affects=["readability", "comparison"],
        )
    if common.legacy and any(has_ptbr):
        side = "o artigo comparado" if has_ptbr[0] else "este artigo"
        return Notice(
            code="READABILITY_LEGACY_SCALE",
            severity="warn",
            message=(
                f"Comparação pela fórmula inglesa do textstat (legado, escala distorcida "
                f"para o português): {side} não tem o Flesch pt-BR, e os dois artigos "
                "(e os benchmarks) usam a mesma escala; as faixas e a meta são as mesmas."
            ),
            affects=["readability", "comparison"],
        )
    return None


async def build_score_payload(
    client: GobusGraphQLClient,
    unique_id: str,
    *,
    compare_with: str | None = None,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> ScoreReport | None:
    """``ScoreReport`` do artigo (com a comparação, se ``compare_with``); ``None`` se o
    artigo não existe. Comparação inexistente ou igual ao artigo vira ``comparison_error``."""
    catalog = catalog or AgencyCatalog(client)
    now = now or now_brt()
    compare_with = (compare_with or "").strip() or None
    other_id = compare_with if compare_with and compare_with != unique_id else None

    if other_id:
        main_data, other_data = await asyncio.gather(
            _fetch_one(client, unique_id, catalog=catalog),
            _fetch_one(client, other_id, catalog=catalog),
        )
    else:
        main_data, other_data = await _fetch_one(client, unique_id, catalog=catalog), None
    if main_data is None:
        return None
    # lado a lado, os dois artigos usam a mesma escala (pt-BR se ambos o têm; senão, o inglês)
    common = (
        common_scale([main_data.features, other_data.features]) if other_data is not None else None
    )
    main = _score_one(main_data, now=now, scale=common)
    other = _score_one(other_data, now=now, scale=common) if other_data is not None else None
    report = main.report
    notice = _pair_notice(main_data, other_data, common) if other_data is not None else None
    if notice is not None:
        notices = [n for n in report.notices if n.code != "READABILITY_LEGACY_SCALE"]
        report = report.model_copy(update={"notices": [*notices, notice]})

    update: dict = {
        "params": {"unique_id": unique_id, "compare_with": compare_with},
        "suggested_comparisons": _suggestions(
            main, {unique_id, report.article.unique_id, compare_with or ""}
        ),
    }
    if compare_with and other_id is None:
        update["comparison_error"] = "compare_with é o próprio artigo: escolha outro uniqueId"
    elif other_id and other is None:
        update["comparison_error"] = f"artigo de comparação não encontrado: `{other_id}`"
    elif other is not None:
        update["comparison"] = _comparison(other.report)
    report = report.model_copy(update=update)
    return report.model_copy(update={"summary": render_score_markdown(report)})


# ── render ──────────────────────────────────────────────────────────────────


def _date(value: str | None) -> str:
    parsed = _parse_dt(value)
    return parsed.strftime("%d/%m/%Y") if parsed else "data desconhecida"


def _bench_cells(b: ScoreBenchmark | None) -> tuple[str, str, str]:
    if b is None:
        return "—", "—", "—"
    window = (
        f" ({b.window.start.strftime('%d/%m')}–{b.window.end.strftime('%d/%m/%Y')})"
        if b.window
        else ""
    )
    sample = f"{b.sample_size} artigos com palavras, {b.flesch_sample_size} com Flesch{window}"
    flesch = describe_flesch(b.median_flesch) if b.median_flesch is not None else "—"
    words = f"{b.median_word_count:.0f}" if b.median_word_count is not None else "—"
    return sample, flesch, words


def render_score_markdown(report: ScoreReport) -> str:
    """Markdown do scorecard (puro)."""
    art = report.article
    lines = [
        f"# Score Editorial: {art.title}",
        f"**{art.agency_name}** (`{art.agency_key}`) · {_date(art.published_at)} · "
        f"`{art.unique_id}`\n",
    ]
    if report.score_status == "refused":
        lines.append("## Nota indisponível\n")
        lines.append(f"> {report.refusal_reason[0].upper()}{report.refusal_reason[1:]}.")
    elif report.score_status == "partial":
        lines.append(f"## Nota Geral: {report.overall:.1f}/10 (parcial)\n")
        lines.append(
            "> Concisão sem benchmark: a amostra da agência nos 90 dias antes da publicação "
            f"tem menos de {MIN_SAMPLE} artigos com contagem de palavras. A nota é a média "
            "renormalizada de legibilidade e densidade de entidades."
        )
    else:
        lines.append(f"## Nota Geral: {report.overall:.1f}/10")

    lines.append("\n## Notas por Dimensão")
    for dim in report.dimensions:
        score = f"{dim.score:.1f}/10" if dim.score is not None else "indisponível"
        lines.append(f"- **{dim.label} (peso {dim.weight:.0%}):** {score} — {dim.detail}")

    if report.benchmark or report.reference_benchmark:
        own = _bench_cells(report.benchmark)
        ref = _bench_cells(report.reference_benchmark)
        own_name = report.benchmark.agency_name if report.benchmark else art.agency_name
        ref_name = (
            report.reference_benchmark.agency_name
            if report.reference_benchmark
            else "Agência Brasil"
        )
        lines += [
            "\n## Benchmark (90 dias antes da publicação)",
            f"| | {own_name} | {ref_name} |",
            "|---|---|---|",
            f"| Amostra | {own[0]} | {ref[0]} |",
            f"| Flesch mediano | {own[1]} | {ref[1]} |",
            f"| Palavras (mediana) | {own[2]} | {ref[2]} |",
            f'\n_Medianas com no mínimo {MIN_SAMPLE} artigos; abaixo disso, "—"._',
        ]
    lines.extend(_comparison_lines(report))
    if report.suggested_comparisons:
        lines.append("\n## Sugestões de comparação (`compare_with`)")
        for sug in report.suggested_comparisons:
            lines.append(f"- `{sug.unique_id}` — {sug.title} ({sug.reason})")
    for notice in report.notices:
        lines.append(f"> {notice.message}")
    return "\n".join(lines)


def _overall_cell(status: str, overall: float | None) -> str:
    if overall is None:
        return "indisponível"
    return f"{overall:.1f}/10" + (" (parcial)" if status == "partial" else "")


def _comparison_lines(report: ScoreReport) -> list[str]:
    if report.comparison_error:
        return [f"\n> Comparação indisponível: {report.comparison_error}."]
    cmp = report.comparison
    if cmp is None:
        return []
    art, other = report.article, cmp.article
    mine = {d.key: d for d in report.dimensions}
    theirs = {d.key: d for d in cmp.dimensions}

    def score(d: ScoreDimension | None) -> str:
        return f"{d.score:.1f}" if d is not None and d.score is not None else "—"

    mixed = cmp.scale != report.scale  # sem escala comum: cada lado diz a sua

    def flesch(a: ScoredArticle, scale_id: str) -> str:
        if a.flesch is None:
            return "—"
        text = describe_flesch(clamp_flesch(a.flesch_raw))
        scale = SCALES.get(scale_id)
        return f"{scale.short} {text}" if mixed and scale is not None else text

    lines = [
        f"\n## Comparação: {other.title}",
        f"**{other.agency_name}** (`{other.agency_key}`) · {_date(other.published_at)} · "
        f"`{other.unique_id}`\n",
        "| | Este artigo | Comparado |",
        "|---|---|---|",
        f"| Nota | {_overall_cell(report.score_status, report.overall)} | "
        f"{_overall_cell(cmp.score_status, cmp.overall)} |",
    ]
    for key in WEIGHTS:
        lines.append(f"| {LABELS[key]} | {score(mine.get(key))} | {score(theirs.get(key))} |")
    lines += [
        f"| Flesch | {flesch(art, report.scale)} | {flesch(other, cmp.scale)} |",
        f"| Palavras | {art.word_count if art.word_count is not None else '—'} | "
        f"{other.word_count if other.word_count is not None else '—'} |",
    ]
    return lines


async def score_article(
    unique_id: str,
    client: GobusGraphQLClient,
    *,
    compare_with: str | None = None,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> str:
    """Markdown do scorecard editorial do artigo."""
    report = await build_score_payload(
        client, unique_id, compare_with=compare_with, catalog=catalog, now=now
    )
    if report is None:
        return f"Artigo não encontrado: `{unique_id}`"
    return report.summary
