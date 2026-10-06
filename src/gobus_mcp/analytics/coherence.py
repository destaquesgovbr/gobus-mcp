"""Coerência de mensagem entre agências (F5): funções puras sobre a amostra de artigos.

Recebe as linhas do ``articles`` (já buscadas pela tool) e devolve as partes do
``CoherenceReport``. Nenhum I/O; datas em BRT a partir do ``publishedAt`` (nunca o
``publicationHour``, que é UTC).

- **Emissores:** agências não republicadoras com ≥ ``MIN_EMITTER_ARTICLES`` artigos. Com
  menos de 2, o índice fica ``insufficient`` ("voz única: X"). Republicadoras sempre à
  parte (volume, participação e atraso da 1ª republicação).
- **E, entidades (0,35):** ``w(a,e) = Σ salience / n_a × ln(1 + N/df(e))``, só com
  ``canonicalId``, sem a própria entidade e sem as ``dgb_{code}`` do catálogo; média dos
  cossenos entre pares ponderada por ``min(n_a, n_b)``; agência com < 3 entidades fora.
- **T, timing BRT (0,25):** ``0,5 × fração com o 1º artigo em até 48 h do primeiro emissor``
  + ``0,5 × Jaccard médio dos dias de publicação``. Fica fora do índice
  (``timing_unavailable``) quando a amostra não cobre a janela inteira (truncada, páginas com
  falha ou índice de busca parcial): a 1ª publicação de cada agência pode não estar nela.
- **F, enquadramento (0,25):** ``1 − JSD`` médio (base 2) das distribuições do léxico de
  ``analytics.framing``; indisponível com < 40% dos artigos classificados.
- **S, tom (0,15):** ``1 − JSD`` médio das contagens de sentimento por agência (aliases de
  contagem do Typesense); indisponível com cobertura < 50%.
- **Índice:** média das dimensões disponíveis com pesos renormalizados; 1–5 por
  ``INDEX_CUTS`` (provisórios).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from itertools import combinations

from gobus_mcp.analytics.framing import FRAME_LABELS, FRAME_PRIORITY, article_frame
from gobus_mcp.calendario import BRT
from gobus_mcp.data_status import parse_api_datetime
from gobus_mcp.payloads.coherence import (
    DIMENSION_ORDER,
    DIMENSION_WEIGHTS,
    INDEX_CUTS,
    MAX_AGENCIES,
    MAX_DIVERGENCES,
    MAX_EXCLUSIVE_ANCHORS,
    MAX_SHARED_ANCHORS,
    AgencyCoherence,
    Anchor,
    CoherenceDimension,
    CoherenceIndex,
    DimensionKey,
    Frame,
    IndexStatus,
    PairDivergence,
    RepublisherAgency,
    RepublishersBlock,
    ToneCounts,
)

MIN_EMITTER_ARTICLES = 2
MIN_ENTITIES = 3
SHARED_ANCHOR_SHARE = 0.5
TIMING_HOURS = 48.0
FRAMING_MIN_CLASSIFIED = 0.4
TONE_MIN_COVERAGE = 0.5
TONE_LABELS: tuple[str, ...] = ("positive", "negative", "neutral")
DEFAULT_SALIENCE = 0.5  # menção sem salience (raro) conta como média
PRIOR_DAYS = 30
TRUNCATED_START_RATIO = 0.5
TRUNCATED_START_MIN = 3

Pair = tuple[str, str]


# ── artigos ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntityMention:
    id: str
    type: str | None
    salience: float


@dataclass(frozen=True)
class CoherenceArticle:
    unique_id: str
    agency: str
    agency_name: str | None
    published_at: datetime  # com fuso
    entities: tuple[EntityMention, ...]
    texts: dict[str, list[str]]  # textos das menções, por canonicalId
    frame: Frame | None
    mock_summary: bool


def parse_article(row: Mapping) -> CoherenceArticle | None:
    """Linha do ``articles`` → ``CoherenceArticle``; ``None`` sem agência ou data.

    Menções repetidas da mesma entidade no artigo viram uma (a maior salience)."""
    agency = (row.get("agency") or "").strip()
    published = parse_api_datetime(row.get("publishedAt"))
    if not agency or published is None:
        return None
    mentions: dict[str, EntityMention] = {}
    texts: dict[str, list[str]] = {}
    for entity in (row.get("features") or {}).get("entities") or []:
        cid = entity.get("canonicalId")
        if not cid:
            continue
        salience = entity.get("salience")
        salience = DEFAULT_SALIENCE if salience is None else float(salience)
        texts.setdefault(cid, []).append(entity.get("text") or cid)
        current = mentions.get(cid)
        if current is None or salience > current.salience:
            etype = entity.get("type") or (current.type if current else None)
            mentions[cid] = EntityMention(cid, etype, salience)
    frame, mock = article_frame(row)
    return CoherenceArticle(
        unique_id=row.get("uniqueId") or "",
        agency=agency,
        agency_name=row.get("agencyName"),
        published_at=published,
        entities=tuple(mentions.values()),
        texts=texts,
        frame=frame,
        mock_summary=mock,
    )


def brt_day(moment: datetime) -> date:
    """Dia em BRT (``2026-09-26T01:30Z`` → 25/09)."""
    return moment.astimezone(BRT).date()


def excluded_entities(subject_id: str | None, agency_codes: Iterable[str]) -> frozenset[str]:
    """A própria entidade e as ``dgb_{code}`` das agências do catálogo (nunca por prefixo)."""
    excluded = {f"dgb_{code}" for code in agency_codes}
    if subject_id:
        excluded.add(subject_id)
    return frozenset(excluded)


# ── primitivas ──────────────────────────────────────────────────────────────


def cosine(u: Mapping[str, float], v: Mapping[str, float]) -> float:
    """Cosseno entre vetores esparsos; 0 se algum é nulo."""
    norm_u = math.sqrt(sum(x * x for x in u.values()))
    norm_v = math.sqrt(sum(x * x for x in v.values()))
    if norm_u == 0 or norm_v == 0:
        return 0.0
    dot = sum(x * v.get(k, 0.0) for k, x in u.items())
    return max(0.0, min(1.0, dot / (norm_u * norm_v)))


def idf(df: Mapping[str, int], n: int) -> dict[str, float]:
    """``ln(1 + N/df)``: a entidade em todos os artigos fica com ``ln 2``."""
    return {key: math.log(1 + n / count) for key, count in df.items() if count > 0}


def jsd(p: Mapping[str, float], q: Mapping[str, float]) -> float | None:
    """Divergência de Jensen-Shannon (base 2, 0–1) entre contagens; ``None`` sem massa."""
    total_p, total_q = sum(p.values()), sum(q.values())
    if total_p <= 0 or total_q <= 0:
        return None
    keys = set(p) | set(q)
    pp = {k: p.get(k, 0) / total_p for k in keys}
    qq = {k: q.get(k, 0) / total_q for k in keys}
    mid = {k: (pp[k] + qq[k]) / 2 for k in keys}

    def kl(a: Mapping[str, float]) -> float:
        return sum(a[k] * math.log2(a[k] / mid[k]) for k in keys if a[k] > 0)

    return max(0.0, min(1.0, 0.5 * kl(pp) + 0.5 * kl(qq)))


def jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def hhi(volumes: Iterable[int]) -> float | None:
    """Herfindahl-Hirschman (0–1) do volume entre emissores."""
    values = [v for v in volumes if v > 0]
    total = sum(values)
    if total <= 0:
        return None
    return sum((v / total) ** 2 for v in values)


def _weighted_mean(items: Iterable[tuple[float, float]]) -> float | None:
    pairs = list(items)
    weight = sum(w for _, w in pairs)
    if weight <= 0:
        return None
    return sum(v * w for v, w in pairs) / weight


def combine(
    values: Mapping[DimensionKey, float | None],
    weights: Mapping[DimensionKey, float] = DIMENSION_WEIGHTS,
) -> tuple[float | None, dict[DimensionKey, float | None]]:
    """Score 0–1 = média ponderada das dimensões disponíveis (pesos renormalizados)."""
    available = {k: v for k, v in values.items() if v is not None}
    if not available:
        return None, dict.fromkeys(DIMENSION_ORDER)
    total = sum(weights[k] for k in available)
    score = sum(weights[k] * v for k, v in available.items()) / total
    effective = {k: (weights[k] / total if k in available else None) for k in DIMENSION_ORDER}
    return score, effective


def index_level(score: float | None, cuts: Sequence[float] = INDEX_CUTS) -> int | None:
    """Índice 1–5: 1 + quantos cortes o score alcança."""
    if score is None:
        return None
    return 1 + sum(1 for cut in cuts if round(score, 6) >= cut)


def truncated_start(
    prior_articles: int, prior_days: int, window_articles: int, window_days: int
) -> bool:
    """A pauta já corria antes da janela? Taxa diária do prior ≥ metade da taxa da janela
    (e ao menos 3 artigos antes). Entidade grande com janela muito mais intensa não dispara."""
    if prior_articles < TRUNCATED_START_MIN or prior_days <= 0 or window_days <= 0:
        return False
    prior_rate = prior_articles / prior_days
    window_rate = window_articles / window_days
    return prior_rate >= TRUNCATED_START_RATIO * window_rate


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


# ── emissores ───────────────────────────────────────────────────────────────


@dataclass
class Split:
    emitters: dict[str, list[CoherenceArticle]]
    singles: dict[str, list[CoherenceArticle]]
    republishers: dict[str, list[CoherenceArticle]]


def _by_volume(groups: Mapping[str, list[CoherenceArticle]]) -> dict[str, list]:
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def split_agencies(
    articles: Iterable[CoherenceArticle],
    republishers: frozenset[str],
    min_articles: int = MIN_EMITTER_ARTICLES,
) -> Split:
    """Emissores (não republicadoras com ≥ ``min_articles``), agências com menos artigos e
    republicadoras; cada grupo ordenado por volume (e código)."""
    groups: dict[str, list[CoherenceArticle]] = {}
    for article in articles:
        groups.setdefault(article.agency, []).append(article)
    emitters, singles, reps = {}, {}, {}
    for agency, items in groups.items():
        if agency in republishers:
            reps[agency] = items
        elif len(items) >= min_articles:
            emitters[agency] = items
        else:
            singles[agency] = items
    return Split(_by_volume(emitters), _by_volume(singles), _by_volume(reps))


def _pairs(keys: Sequence[str]) -> list[Pair]:
    return list(combinations(keys, 2))


# ── E: entidades ────────────────────────────────────────────────────────────


@dataclass
class EntityResult:
    value: float | None
    reason: str | None
    vectors: dict[str, dict[str, float]]
    eligible: list[str]
    pairs: dict[Pair, float] = field(default_factory=dict)
    shared: list[Anchor] = field(default_factory=list)
    exclusive: dict[str, list[Anchor]] = field(default_factory=dict)


def entity_dimension(
    emitters: Mapping[str, list[CoherenceArticle]], *, exclude: frozenset[str]
) -> EntityResult:
    df: Counter[str] = Counter()
    texts: dict[str, Counter[str]] = {}
    types: dict[str, str | None] = {}
    sums: dict[str, Counter[str]] = {}
    n_total = 0
    for agency, items in emitters.items():
        acc: Counter[str] = Counter()
        for article in items:
            n_total += 1
            for mention in article.entities:
                if mention.id in exclude:
                    continue
                df[mention.id] += 1
                acc[mention.id] += mention.salience
                types.setdefault(mention.id, mention.type)
                texts.setdefault(mention.id, Counter()).update(article.texts.get(mention.id, ()))
        sums[agency] = acc
    weights = idf(df, n_total)
    vectors = {
        agency: {e: total / len(emitters[agency]) * weights[e] for e, total in acc.items()}
        for agency, acc in sums.items()
    }
    eligible = [a for a in emitters if len(vectors[a]) >= MIN_ENTITIES]

    def anchor(entity_id: str, agencies: int, weight: float) -> Anchor:
        label = texts[entity_id].most_common(1)[0][0] if texts.get(entity_id) else entity_id
        return Anchor(
            entity_id=entity_id,
            label=label,
            type=types.get(entity_id),
            agencies=agencies,
            weight=round(weight, 4),
        )

    exclusive: dict[str, list[Anchor]] = {}
    for agency, vector in vectors.items():
        others = [vectors[b] for b in vectors if b != agency]
        only = [(e, w) for e, w in vector.items() if not any(e in o for o in others)]
        only.sort(key=lambda ew: (-ew[1], ew[0]))
        exclusive[agency] = [anchor(e, 1, w) for e, w in only[:MAX_EXCLUSIVE_ANCHORS]]

    if len(eligible) < 2:
        return EntityResult(
            value=None,
            reason=(
                "menos de 2 agências com pelo menos 3 entidades canônicas (fora a própria "
                "entidade e as das agências)"
            ),
            vectors=vectors,
            eligible=eligible,
            exclusive=exclusive,
        )

    pairs = {(a, b): cosine(vectors[a], vectors[b]) for a, b in _pairs(eligible)}
    value = _weighted_mean(
        (sim, min(len(emitters[a]), len(emitters[b]))) for (a, b), sim in pairs.items()
    )
    needed = max(2, math.ceil(SHARED_ANCHOR_SHARE * len(eligible)))
    presence = Counter(e for a in eligible for e in vectors[a])
    shared = [
        anchor(e, count, sum(vectors[a].get(e, 0.0) for a in eligible))
        for e, count in presence.items()
        if count >= needed
    ]
    shared.sort(key=lambda x: (-x.agencies, -x.weight, x.label))
    return EntityResult(
        value=value,
        reason=None,
        vectors=vectors,
        eligible=eligible,
        pairs=pairs,
        shared=shared[:MAX_SHARED_ANCHORS],
        exclusive=exclusive,
    )


# ── T: timing ───────────────────────────────────────────────────────────────


@dataclass
class TimingResult:
    value: float | None
    first: dict[str, datetime]
    delay_hours: dict[str, float]
    days: dict[str, set[date]]
    within: float | None
    within_count: int
    jaccard: float | None
    pairs: dict[Pair, float] = field(default_factory=dict)


def timing_dimension(emitters: Mapping[str, list[CoherenceArticle]]) -> TimingResult:
    first = {a: min(x.published_at for x in items).astimezone(BRT) for a, items in emitters.items()}
    days = {a: {brt_day(x.published_at) for x in items} for a, items in emitters.items()}
    if not first:
        return TimingResult(None, {}, {}, {}, None, 0, None)
    start = min(first.values())
    delay = {a: round((t - start).total_seconds() / 3600, 2) for a, t in first.items()}
    index_agency = min(first, key=lambda a: (first[a], list(first).index(a)))
    others = [a for a in first if a != index_agency]
    within_count = sum(1 for a in others if delay[a] <= TIMING_HOURS)
    within = within_count / len(others) if others else None
    keys = list(emitters)
    pairs: dict[Pair, float] = {}
    jaccards = []
    for a, b in _pairs(keys):
        jac = jaccard(days[a], days[b])
        jaccards.append(jac)
        close = abs((first[a] - first[b]).total_seconds()) / 3600 <= TIMING_HOURS
        pairs[(a, b)] = 0.5 * float(close) + 0.5 * jac
    jac_mean = sum(jaccards) / len(jaccards) if jaccards else None
    value = 0.5 * within + 0.5 * jac_mean if within is not None and jac_mean is not None else None
    return TimingResult(value, first, delay, days, within, within_count, jac_mean, pairs)


# ── F: enquadramento ────────────────────────────────────────────────────────


@dataclass
class FramingResult:
    value: float | None
    reason: str | None
    classified_share: float | None
    counts: dict[str, dict[str, int]]
    dominant: dict[str, Frame | None]
    overall: Frame | None
    overall_share: float | None
    pairs: dict[Pair, float] = field(default_factory=dict)


def _dominant(counts: Mapping[str, int]) -> Frame | None:
    best = max(FRAME_PRIORITY, key=lambda f: (counts.get(f, 0), -FRAME_PRIORITY.index(f)))
    return best if counts.get(best, 0) > 0 else None


def framing_dimension(emitters: Mapping[str, list[CoherenceArticle]]) -> FramingResult:
    counts = {
        a: dict(Counter(x.frame for x in items if x.frame is not None))
        for a, items in emitters.items()
    }
    dominant = {a: _dominant(c) for a, c in counts.items()}
    total = sum(len(items) for items in emitters.values())
    classified = sum(sum(c.values()) for c in counts.values())
    share = classified / total if total else None
    overall_counts: Counter[str] = Counter()
    for c in counts.values():
        overall_counts.update(c)
    overall = _dominant(overall_counts)
    overall_share = overall_counts[overall] / classified if overall and classified else None

    def result(value, reason, pairs=None) -> FramingResult:
        return FramingResult(
            value, reason, share, counts, dominant, overall, overall_share, pairs or {}
        )

    if share is None or share < FRAMING_MIN_CLASSIFIED:
        return result(
            None,
            f"só {_pct(share)} dos artigos dos emissores com enquadramento identificado "
            f"(mínimo {FRAMING_MIN_CLASSIFIED:.0%})",
        )
    usable = [a for a in emitters if counts[a]]
    if len(usable) < 2:
        return result(None, "menos de 2 agências com enquadramento identificado")
    pairs = {(a, b): 1 - (jsd(counts[a], counts[b]) or 0.0) for a, b in _pairs(usable)}
    value = _weighted_mean(
        (sim, min(sum(counts[a].values()), sum(counts[b].values())))
        for (a, b), sim in pairs.items()
    )
    return result(value, None, pairs)


# ── S: tom ──────────────────────────────────────────────────────────────────


@dataclass
class ToneResult:
    value: float | None
    reason: str | None
    coverage: float | None
    labeled: dict[str, int]
    positive_share: float | None = None
    pairs: dict[Pair, float] = field(default_factory=dict)


def tone_dimension(
    counts: Mapping[str, Mapping[str, int]], totals: Mapping[str, int]
) -> ToneResult:
    """Tom por agência a partir das contagens de sentimento (``positive``/``negative``/
    ``neutral``) e do total de artigos de cada agência na janela."""
    labeled = {a: sum(int(c.get(lbl, 0) or 0) for lbl in TONE_LABELS) for a, c in counts.items()}
    total = sum(totals.values())
    coverage = min(1.0, sum(labeled.values()) / total) if total > 0 else None
    positives = sum(int(c.get("positive", 0) or 0) for c in counts.values())
    positive_share = positives / sum(labeled.values()) if sum(labeled.values()) else None
    if coverage is None or coverage < TONE_MIN_COVERAGE:
        return ToneResult(
            None,
            f"cobertura de sentimento de {_pct(coverage)} dos artigos dos emissores "
            f"(mínimo {TONE_MIN_COVERAGE:.0%})",
            coverage,
            labeled,
            positive_share,
        )
    usable = [a for a in counts if labeled.get(a)]
    if len(usable) < 2:
        return ToneResult(
            None, "menos de 2 agências com sentimento", coverage, labeled, positive_share
        )
    dists = {a: {lbl: counts[a].get(lbl, 0) or 0 for lbl in TONE_LABELS} for a in usable}
    pairs = {(a, b): 1 - (jsd(dists[a], dists[b]) or 0.0) for a, b in _pairs(usable)}
    value = _weighted_mean((sim, min(labeled[a], labeled[b])) for (a, b), sim in pairs.items())
    return ToneResult(value, None, coverage, labeled, positive_share, pairs)


# ── avaliação ───────────────────────────────────────────────────────────────


@dataclass
class Assessment:
    index_status: IndexStatus
    insufficient_reason: str | None
    index: CoherenceIndex
    dimensions: list[CoherenceDimension]
    agencies: list[AgencyCoherence]
    agencies_omitted: int
    shared_anchors: list[Anchor]
    divergences: list[PairDivergence]
    republishers: RepublishersBlock
    sample: dict[str, int]
    hhi: float | None
    timing: TimingResult | None = None


INSUFFICIENT_DETAIL = "menos de 2 emissores (agências não republicadoras com 2+ artigos)"


def _name(agency: str, items: Sequence[CoherenceArticle], names: Mapping[str, str]) -> str:
    fallback = next((x.agency_name for x in items if x.agency_name), None)
    return names.get(agency) or fallback or agency


def _dimension(
    key: DimensionKey,
    value: float | None,
    effective: float | None,
    detail: str,
    metric: dict[str, float | int | None] | None = None,
) -> CoherenceDimension:
    return CoherenceDimension(
        key=key,
        weight=DIMENSION_WEIGHTS[key],
        effective_weight=_round(effective),
        value=_round(value),
        status="ok" if value is not None else "unavailable",
        detail=detail,
        metric={k: (_round(v) if isinstance(v, float) else v) for k, v in (metric or {}).items()},
    )


def _divergences(
    keys: Sequence[str], by_key: Mapping[DimensionKey, Mapping[Pair, float]]
) -> list[PairDivergence]:
    out: list[PairDivergence] = []
    for a, b in _pairs(keys):
        values: dict[DimensionKey, float | None] = {}
        for dim in DIMENSION_ORDER:
            pairs = by_key.get(dim) or {}
            values[dim] = pairs.get((a, b), pairs.get((b, a)))
        score, _ = combine(values)
        if score is None:
            continue
        available = [d for d in DIMENSION_ORDER if values[d] is not None]
        weakest = min(available, key=lambda d: (values[d], DIMENSION_ORDER.index(d)))
        out.append(
            PairDivergence(
                agencies=[a, b],
                similarity=round(score, 4),
                weakest=weakest,
                by_dimension={d: _round(v) for d, v in values.items()},
            )
        )
    out.sort(key=lambda p: (p.similarity, p.agencies))
    return out[:MAX_DIVERGENCES]


def _republishers(
    split: Split, timing: TimingResult | None, total: int, names: Mapping[str, str]
) -> RepublishersBlock:
    start = min(timing.first.values()) if timing and timing.first else None
    agencies = []
    for agency, items in split.republishers.items():
        first = min(x.published_at for x in items).astimezone(BRT)
        delay = round((first - start).total_seconds() / 3600, 2) if start else None
        agencies.append(
            RepublisherAgency(
                agency_key=agency,
                agency_name=_name(agency, items, names),
                articles=len(items),
                first_published_at=first,
                delay_hours=delay,
            )
        )
    count = sum(len(items) for items in split.republishers.values())
    return RepublishersBlock(
        articles=count, share=_round(count / total) if total else None, agencies=agencies
    )


def assess(
    articles: Sequence[CoherenceArticle],
    *,
    republishers: frozenset[str],
    exclude: frozenset[str],
    names: Mapping[str, str] | None = None,
    tone_counts: Mapping[str, Mapping[str, int]] | None = None,
    tone_totals: Mapping[str, int] | None = None,
    tone_error: str | None = None,
    timing_unavailable: str | None = None,
) -> Assessment:
    """Avalia a coerência da amostra. ``tone_counts``/``tone_totals`` vêm dos aliases de
    contagem por agência (``None`` = não medido; ``tone_error`` explica a falha).
    ``timing_unavailable`` (o motivo) tira o T do índice e das divergências: a amostra não
    cobre a janela inteira e a 1ª publicação de cada agência pode estar fora dela."""
    names = names or {}
    split = split_agencies(articles, republishers)
    emitters = split.emitters
    sample = {
        "emitters": len(emitters),
        "emitter_articles": sum(len(v) for v in emitters.values()),
        "single_article_agencies": len(split.singles),
        "republisher_articles": sum(len(v) for v in split.republishers.values()),
        "mock_summaries_ignored": sum(1 for x in articles if x.mock_summary),
    }
    timing = timing_dimension(emitters)
    framing = framing_dimension(emitters)
    entities = entity_dimension(emitters, exclude=exclude)
    tone = tone_dimension(tone_counts, tone_totals or {}) if tone_counts is not None else None

    rows = [
        AgencyCoherence(
            agency_key=agency,
            agency_name=_name(agency, items, names),
            articles=len(items),
            first_published_at=timing.first[agency],
            delay_hours=timing.delay_hours[agency],
            active_days=len(timing.days[agency]),
            dominant_frame=framing.dominant.get(agency),
            frames=framing.counts.get(agency, {}),
            tone=(
                ToneCounts(
                    **{lbl: int(tone_counts[agency].get(lbl, 0) or 0) for lbl in TONE_LABELS}
                )
                if tone_counts is not None and agency in tone_counts
                else None
            ),
            exclusive_anchors=entities.exclusive.get(agency, []),
        )
        for agency, items in emitters.items()
    ]
    republisher_block = _republishers(split, timing, len(articles), names)
    common = dict(
        agencies=rows[:MAX_AGENCIES],
        agencies_omitted=max(0, len(rows) - MAX_AGENCIES),
        republishers=republisher_block,
        sample=sample,
        hhi=_round(hhi(len(v) for v in emitters.values())),
        timing=timing,
    )

    if len(emitters) < 2:
        if emitters:
            agency, items = next(iter(emitters.items()))
            reason = f"voz única: {_name(agency, items, names)} ({len(items)} artigos)"
        else:
            reason = "nenhuma agência não republicadora com 2 ou mais artigos na janela"
        return Assessment(
            index_status="insufficient",
            insufficient_reason=reason,
            index=CoherenceIndex(score=None, level=None),
            dimensions=[_dimension(k, None, None, INSUFFICIENT_DETAIL) for k in DIMENSION_ORDER],
            shared_anchors=[],
            divergences=[],
            **common,
        )

    tone_value = tone.value if tone else None
    timing_value = None if timing_unavailable else timing.value
    values: dict[DimensionKey, float | None] = {
        "entities": entities.value,
        "timing": timing_value,
        "framing": framing.value,
        "tone": tone_value,
    }
    score, effective = combine(values)

    entity_detail = (
        f"{len(entities.shared)} âncoras em comum entre {len(entities.eligible)} agências; "
        f"cosseno médio {_num(entities.value)}"
        if entities.value is not None
        else entities.reason or ""
    )
    others = len(timing.first) - 1
    timing_detail = timing_unavailable or (
        f"1º artigo em até 48 h: {timing.within_count} de {others} "
        f"{'agência' if others == 1 else 'agências'}; "
        f"dias em comum (Jaccard) {_num(timing.jaccard or 0.0)}"
    )
    timing_metric = (
        {"within48h": None, "jaccard": None}
        if timing_unavailable
        else {"within48h": timing.within, "jaccard": timing.jaccard}
    )
    if framing.value is not None:
        dominant = FRAME_LABELS[framing.overall] if framing.overall else "—"
        framing_detail = (
            f"{_pct(framing.classified_share)} dos artigos classificados; dominante: "
            f"{dominant} ({_pct(framing.overall_share)})"
        )
    else:
        framing_detail = framing.reason or ""
    if tone is None:
        tone_detail = f"falha ao consultar o sentimento ({tone_error or 'não medido'})"
    elif tone.value is not None:
        tone_detail = (
            f"cobertura de sentimento {_pct(tone.coverage)}; {_pct(tone.positive_share)} positivo"
        )
    else:
        tone_detail = tone.reason or ""

    dimensions = [
        _dimension(
            "entities",
            entities.value,
            effective["entities"],
            entity_detail,
            {"eligibleAgencies": len(entities.eligible), "sharedAnchors": len(entities.shared)},
        ),
        _dimension("timing", timing_value, effective["timing"], timing_detail, timing_metric),
        _dimension(
            "framing",
            framing.value,
            effective["framing"],
            framing_detail,
            {"classifiedShare": framing.classified_share},
        ),
        _dimension(
            "tone",
            tone_value,
            effective["tone"],
            tone_detail,
            {"coverage": tone.coverage if tone else None},
        ),
    ]
    divergences = _divergences(
        list(emitters),
        {
            "entities": entities.pairs,
            "timing": {} if timing_unavailable else timing.pairs,
            "framing": framing.pairs,
            "tone": tone.pairs if tone else {},
        },
    )
    return Assessment(
        index_status="scored",
        insufficient_reason=None,
        index=CoherenceIndex(score=_round(score), level=index_level(score)),
        dimensions=dimensions,
        shared_anchors=entities.shared,
        divergences=divergences,
        **common,
    )
