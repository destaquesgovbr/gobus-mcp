"""Saúde das fontes de dados: avaliadores puros, compartilhados pelo health e pelas tools.

Só ``theme_coverage`` faz I/O (uma query nomeada); os demais avaliadores são puros.

A **detecção é sempre dinâmica** (cobertura medida na própria resposta da API). As datas
de ``SINCE_HINTS`` só servem para redigir "desde dd/mm" quando o avaliador já disse que
o dado não está ok — nunca para decidir o status.

Vocabulário (integration.md §1.3): ``ok | degraded | unavailable``. Cada ``DataStatus``
não-ok vira um ``Notice`` pelo mapeamento ``NOTICE_FOR_KEY``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime

from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.payloads.common import DataKey, DataStatus, Notice, NoticeCode, Status

# Rótulos PT das fontes (só texto; os enums ficam em inglês).
KEY_LABELS: Mapping[str, str] = {
    "themes": "Temas",
    "summaries": "Resumos",
    "sentiment_labels": "Rótulos de sentimento",
    "sentiment_analytics": "Sentimento (analytics)",
    "entities_ner": "Entidades (NER)",
    "readability": "Legibilidade (Flesch)",
    "word_count": "Contagem de palavras",
    "article_trending": "trendingScore por artigo",
    "entity_ranking": "Ranking de entidades em alta",
    "indexing_lag": "Indexação (Typesense)",
    "agency_activity": "Atividade das agências",
}

STATUS_LABELS: Mapping[str, str] = {
    "ok": "ok",
    "degraded": "degradado",
    "unavailable": "indisponível",
}

# Início provável de incidentes conhecidos (05/10/2026). Só redação, nunca detecção.
SINCE_HINTS: Mapping[str, date] = {
    "themes": date(2026, 9, 26),
    "summaries": date(2026, 9, 26),
    "sentiment_labels": date(2026, 9, 26),
    "readability": date(2026, 6, 30),
    "word_count": date(2026, 6, 30),
}

NOTICE_FOR_KEY: Mapping[str, NoticeCode] = {
    "themes": "THEMES_UNCLASSIFIED",
    "sentiment_labels": "SENTIMENT_UNAVAILABLE",
    "sentiment_analytics": "SENTIMENT_UNAVAILABLE",
    "readability": "READABILITY_UNAVAILABLE",
    "word_count": "READABILITY_UNAVAILABLE",
    "entity_ranking": "TRENDING_ENTITIES_STALE",
    "indexing_lag": "INDEXING_LAG",
}

# Ranking de entidades (antes da correção F2, as linhas do piso antigo têm vr/wc ≈ 142,9).
LEGACY_FLOOR_RATIO = 100.0
RANKING_FRESH_HOURS = 13.0
RANKING_DEAD_DAYS = 7

_SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _make(
    key: DataKey,
    status: Status,
    detail: str,
    *,
    since: date | None,
    metric: dict[str, float | int | None],
) -> DataStatus:
    if status != "ok" and since is None:
        since = SINCE_HINTS.get(key)
    if status == "ok":
        since = None
    message = f"{KEY_LABELS[key]}: {STATUS_LABELS[status]} — {detail}"
    if since is not None:
        message += f" (desde {_fmt_date(since)})"
    return DataStatus(key=key, status=status, since=since, message=message, metric=metric)


def data_status_for(
    key: DataKey,
    status: Status,
    detail: str,
    *,
    since: date | None = None,
    metric: dict[str, float | int | None] | None = None,
) -> DataStatus:
    """``DataStatus`` com a redação padrão ("Rótulo: status — detalhe (desde dd/mm/aaaa)")."""
    return _make(key, status, detail, since=since, metric=metric or {})


_STATUS_RANK: Mapping[str, int] = {"ok": 0, "degraded": 1, "unavailable": 2}


def worst_status(statuses: Iterable[Status]) -> Status:
    """O pior status (``ok`` < ``degraded`` < ``unavailable``); ``ok`` se vazio."""
    return max(statuses, key=_STATUS_RANK.__getitem__, default="ok")


def failed_status(key: DataKey, error: BaseException | str) -> DataStatus:
    """``unavailable`` por falha de consulta. Sem dica de ``since``: a falha é de agora."""
    text = error if isinstance(error, str) else (str(error) or type(error).__name__)
    return DataStatus(
        key=key,
        status="unavailable",
        since=None,
        message=f"{KEY_LABELS[key]}: indisponível — falha ao consultar a graphql-api ({text})",
        metric={},
    )


def _status_for_ratio(ratio: float | None, *, dead: float, degraded: float) -> Status:
    if ratio is None or ratio < dead:
        return "unavailable"
    if ratio < degraded:
        return "degraded"
    return "ok"


def _pct(ratio: float | None) -> str:
    return "—" if ratio is None else f"{ratio:.0%}"


def share_status(
    key: DataKey,
    covered: int,
    total: int,
    *,
    dead: float = 0.1,
    degraded: float = 0.8,
    since: date | None = None,
) -> DataStatus:
    """Status pela fração ``covered/total``: < ``dead`` indisponível; < ``degraded`` degradado."""
    ratio = covered / total if total > 0 else None
    status = _status_for_ratio(ratio, dead=dead, degraded=degraded)
    detail = (
        f"{covered} de {total} artigos com dado ({_pct(ratio)})" if total > 0 else "sem artigos"
    )
    return _make(
        key,
        status,
        detail,
        since=since,
        metric={"covered": covered, "total": total, "ratio": ratio},
    )


def theme_coverage_status(
    classified: int, total: int, *, days: int, scope: str | None = None
) -> DataStatus:
    """Cobertura de classificação de temas na janela (Σ topThemes / analyticsKpis.total).

    Abaixo de 50% o bloco de temas fica indisponível; abaixo de 80%, degradado.
    ``scope`` troca o "dos últimos N dias" do texto (ex.: o baseline anterior à janela).
    """
    ratio = classified / total if total > 0 else None
    status = _status_for_ratio(ratio, dead=0.5, degraded=0.8)
    where = scope or f"dos últimos {days} dias"
    detail = (
        f"{_pct(ratio)} dos artigos {where} com tema ({classified} de {total})"
        if total > 0
        else f"sem artigos {where}"
    )
    metric = {"classified": classified, "total": total, "ratio": ratio, "days": days}
    return _make("themes", status, detail, since=None, metric=metric)


_THEME_COVERAGE_QUERY = """
query ThemeCoverage($days: Int!) {
  topThemes(range: {days: $days}, limit: 100) {
    label
    count
  }
  analyticsKpis(range: {days: $days}) {
    total
  }
}
"""

THEME_COVERAGE_TTL = 600.0  # 10 min


async def theme_coverage(
    client: GobusGraphQLClient, days: int, *, cache: TTLCache | None = None
) -> DataStatus:
    """Cobertura de classificação de temas dos últimos ``days`` dias (janela móvel UTC).

    ``Σ topThemes.count / analyticsKpis.total`` — os dois leem o Typesense, então o
    atraso de indexação afeta numerador e denominador igualmente.
    """

    async def load() -> dict:
        return await client.execute(_THEME_COVERAGE_QUERY, {"days": days})

    if cache is None:
        data = await load()
    else:
        data = await cache.get_or_load(("theme_coverage", days), load, THEME_COVERAGE_TTL)
    classified = sum(t.get("count") or 0 for t in data.get("topThemes") or [])
    total = (data.get("analyticsKpis") or {}).get("total") or 0
    return theme_coverage_status(classified, total, days=days)


def metric_coverage_status(
    key: DataKey,
    rows: Iterable[Mapping],
    field: str,
    *,
    weight_key: str = "articleCount",
    dead: float = 0.1,
    degraded: float = 0.8,
    since: date | None = None,
) -> DataStatus:
    """Cobertura de uma média do ``agencyAnalytics`` ponderada por artigos.

    Linha com ``field`` nulo não tem dado (0.0 é dado). Mede a fração de artigos em
    linhas com valor — é o que separa "0.0 de verdade" de "pipeline parado".
    """
    total = covered = 0
    for row in rows:
        weight = row.get(weight_key) or 0
        total += weight
        if row.get(field) is not None:
            covered += weight
    ratio = covered / total if total > 0 else None
    status = _status_for_ratio(ratio, dead=dead, degraded=degraded)
    detail = (
        f"{_pct(ratio)} dos artigos com valor ({covered} de {total})"
        if total > 0
        else "sem artigos no período"
    )
    metric = {"coveredArticles": covered, "totalArticles": total, "ratio": ratio}
    return _make(key, status, detail, since=since, metric=metric)


def sentiment_analytics_status(rows: Iterable[Mapping]) -> DataStatus:
    """Sentimento do ``agencyAnalytics``: decide pela nulidade de ``avgSentimentScore``.

    ``pctPositive`` é fração 0..1 e pode vir 0.0 mesmo sem dado (F0c) — não serve de sinal.
    """
    return metric_coverage_status("sentiment_analytics", rows, "avgSentimentScore")


def parse_api_datetime(value: str | None) -> datetime | None:
    """Timestamp da API (``'2026-07-03 21:06:24.66578+00'``); sem fuso = UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def entity_ranking_status(rows: list[Mapping], *, now: datetime) -> DataStatus:
    """Saúde do ``trendingEntities``.

    - indisponível: vazio, sem ``computedAt`` ou última execução há mais de 7 dias;
    - degradado: linhas no piso antigo (``volumeRatio/windowCount ≥ 100``), execuções
      misturadas ou última execução há mais de 13 h;
    - ok: uma única execução recente, sem linhas legadas.
    """
    parsed = [parse_api_datetime(r.get("computedAt")) for r in rows]
    stamps = [p for p in parsed if p is not None]
    metric: dict[str, float | int | None] = {"rowsTotal": len(rows)}
    if not stamps:
        detail = "ranking vazio" if not rows else "linhas sem computedAt"
        return _make("entity_ranking", "unavailable", detail, since=None, metric=metric)

    last = max(stamps)
    age_hours = (now - last).total_seconds() / 3600
    legacy = sum(
        1
        for r in rows
        if (r.get("volumeRatio") or 0) / max(r.get("windowCount") or 0, 1) >= LEGACY_FLOOR_RATIO
    )
    distinct_runs = len(set(stamps))
    metric.update(
        rowsLastRun=sum(1 for p in parsed if p == last),
        rowsLegacyFloor=legacy,
        distinctRuns=distinct_runs,
        ageHours=round(age_hours, 2),  # metric só aceita números; a data vai no texto
    )
    if any("isNew" in r for r in rows):
        metric["isNewShare"] = sum(1 for r in rows if r.get("isNew")) / len(rows)

    last_txt = last.strftime("%d/%m/%Y %H:%M UTC")
    if age_hours > RANKING_DEAD_DAYS * 24:
        detail = f"última execução em {last_txt} (há {age_hours / 24:.0f} dias)"
        return _make("entity_ranking", "unavailable", detail, since=None, metric=metric)

    problems = []
    if legacy:
        problems.append(f"{legacy} de {len(rows)} linhas no piso antigo (baseline zero)")
    if distinct_runs > 1:
        problems.append(f"{distinct_runs} execuções misturadas")
    if age_hours > RANKING_FRESH_HOURS:
        problems.append(f"última execução há {age_hours:.0f} h")
    if problems:
        return _make("entity_ranking", "degraded", "; ".join(problems), since=None, metric=metric)
    detail = f"execução única de {last_txt} (há {age_hours:.0f} h)"
    return _make("entity_ranking", "ok", detail, since=None, metric=metric)


def to_notice(status: DataStatus) -> Notice | None:
    """``DataStatus`` não-ok → ``Notice`` (``None`` se ok ou sem código mapeado)."""
    code = NOTICE_FOR_KEY.get(status.key)
    if status.status == "ok" or code is None:
        return None
    return Notice(
        code=code,
        severity="error" if status.status == "unavailable" else "warn",
        message=status.message,
        since=status.since,
        affects=[status.key],
    )


def notices_for(statuses: Iterable[DataStatus]) -> list[Notice]:
    """Avisos dos status não-ok, um por código (pior severidade, ``since`` mais antigo)."""
    grouped: dict[str, Notice] = {}
    for status in statuses:
        notice = to_notice(status)
        if notice is None:
            continue
        current = grouped.get(notice.code)
        if current is None:
            grouped[notice.code] = notice
            continue
        sinces = [d for d in (current.since, notice.since) if d is not None]
        worst = max(current, notice, key=lambda n: _SEVERITY_RANK[n.severity])
        grouped[notice.code] = Notice(
            code=notice.code,
            severity=worst.severity,
            message=f"{current.message}; {notice.message}",
            since=min(sinces) if sinces else None,
            affects=[*current.affects, *notice.affects],
        )
    return list(grouped.values())
