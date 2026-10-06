"""Nota editorial (0–10) de um artigo, comparada ao benchmark da própria agência.

Três dimensões (pesos 50/30/20): legibilidade (Flesch limitado a [0, 100]), concisão
(palavras contra a mediana da agência) e densidade de entidades (por 100 palavras).

- **refused**: sem Flesch ou sem wordCount → "Nota indisponível" (nunca uma nota neutra);
- **partial**: sem benchmark de concisão (amostra < 10) → média renormalizada;
- **scored**: as três dimensões.

O benchmark é uma amostra ``articles`` da agência (e da Agência Brasil) nos 90 dias antes
da publicação do artigo, com mediana calculada no cliente.
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import calendar_context, now_brt, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import notices_for, share_status
from gobus_mcp.payloads.common import DataStatus
from gobus_mcp.payloads.readability import DayRange, flesch_bands
from gobus_mcp.payloads.scorecard import (
    ScoreBenchmark,
    ScoredArticle,
    ScoreDimension,
    ScoreReport,
)
from gobus_mcp.readability import clamp_flesch, describe_flesch, readability_score

BENCHMARK_AGENCY = "agencia_brasil"
BENCHMARK_DAYS = 90
SAMPLE_LIMIT = 250
MIN_SAMPLE = 10
WEIGHTS = {"readability": 0.5, "conciseness": 0.3, "entity_density": 0.2}
LABELS = {
    "readability": "Legibilidade",
    "conciseness": "Concisão",
    "entity_density": "Densidade de entidades",
}

_ARTICLE_QUERY = """
query ScoreArticle($uniqueId: String!) {
  article(uniqueId: $uniqueId) {
    uniqueId
    title
    url
    agency
    agencyName
    publishedAt
    features {
      readabilityFlesch
      wordCount
      entities { type }
    }
  }
}
"""

_BENCHMARK_QUERY = """
query ScoreArticleBenchmark(
  $agencies: [String!]!, $startDate: String!, $endDate: String!, $limit: Int!
) {
  ag: articles(
    page: 1
    limit: $limit
    filter: {agencies: $agencies, startDate: $startDate, endDate: $endDate}
    sort: DATE
  ) {
    found
    articles { uniqueId publishedAt features { readabilityFlesch wordCount } }
  }
  ab: articles(
    page: 1
    limit: $limit
    filter: {agencies: ["agencia_brasil"], startDate: $startDate, endDate: $endDate}
    sort: DATE
  ) {
    found
    articles { uniqueId publishedAt features { readabilityFlesch wordCount } }
  }
}
"""


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
    result: dict | None, *, code: str, name: str, exclude: str
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
        if feats.get("readabilityFlesch") is not None:
            flesch.append(clamp_flesch(feats["readabilityFlesch"]).value)
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


async def build_score_payload(
    client: GobusGraphQLClient,
    unique_id: str,
    *,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> ScoreReport | None:
    """``ScoreReport`` do artigo; ``None`` se o artigo não existe."""
    catalog = catalog or AgencyCatalog(client)
    now = now or now_brt()
    today = reference_date(now)

    data = await client.execute(_ARTICLE_QUERY, {"uniqueId": unique_id})
    art = data.get("article")
    if not art:
        return None

    features = art.get("features") or {}
    fv = clamp_flesch(features.get("readabilityFlesch"))
    word_count = features.get("wordCount")
    entity_count = len(features.get("entities") or [])
    code = art.get("agency") or ""
    name, ab_name = await asyncio.gather(
        catalog.display_name(code, art.get("agencyName")),
        catalog.display_name(BENCHMARK_AGENCY, "Agência Brasil"),
    )

    published = _parse_dt(art.get("publishedAt"))
    benchmark = reference = None
    data_status: list[DataStatus] = []
    if published is not None and code:
        bench_data = await client.execute(
            _BENCHMARK_QUERY,
            {
                "agencies": [code],
                "startDate": (published - timedelta(days=BENCHMARK_DAYS)).isoformat(),
                "endDate": published.isoformat(),
                "limit": SAMPLE_LIMIT,
            },
        )
        benchmark, with_flesch, total = _benchmark(
            bench_data.get("ag"), code=code, name=name, exclude=unique_id
        )
        reference, _, _ = _benchmark(
            bench_data.get("ab"), code=BENCHMARK_AGENCY, name=ab_name, exclude=unique_id
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
            f"Flesch {describe_flesch(fv)}",
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
        dims = [d.model_copy(update={"score": None}) for d in dims]

    report = ScoreReport(
        summary="",
        status=status,
        generated_at=now,
        reference_date=today,
        params={"unique_id": unique_id},
        calendar=calendar_context(today),
        data_status=data_status,
        notices=notices_for(data_status),
        score_status=score_status,
        overall=overall,
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
    for notice in report.notices:
        lines.append(f"> {notice.message}")
    return "\n".join(lines)


async def score_article(
    unique_id: str,
    client: GobusGraphQLClient,
    *,
    catalog: AgencyCatalog | None = None,
    now: datetime | None = None,
) -> str:
    """Markdown do scorecard editorial do artigo."""
    report = await build_score_payload(client, unique_id, catalog=catalog, now=now)
    if report is None:
        return f"Artigo não encontrado: `{unique_id}`"
    return report.summary
