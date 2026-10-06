"""Ciclo de vida comunicacional de uma política pública.

O ``entityCoverage(MONTH)`` devolve uma linha por **mês × agência**. A série do ciclo de
vida é mensal: as agências de cada mês são somadas e os meses sem artigos, do primeiro mês
com cobertura até o mês de referência (o de hoje, em BRT), entram com 0. O mês de
referência é **parcial**: aparece na tabela, mas fica fora da classificação, e a fase
atual é a do último mês fechado. O pico é o mês fechado de maior total. Os artigos
representativos vêm da janela do mês de pico (filtro de entidade e de data).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from gobus_mcp.calendario import reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.readability import period_start

_ENTITY_SEARCH_QUERY = """
query EntitySearch($query: String!, $entityType: EntityKind, $limit: Int) {
  entitySearch(query: $query, entityType: $entityType, limit: $limit) {
    entityId canonicalName type description wikidataUrl agencyKey aliases articleCount confidence matchType
  }
}
"""

_ENTITY_COVERAGE_QUERY = """
query EntityCoverage($entityId: String!, $granularity: Granularity, $dateFrom: String, $dateTo: String) {
  entityCoverage(entityId: $entityId, granularity: $granularity, dateFrom: $dateFrom, dateTo: $dateTo) {
    period agencyKey agencyName articleCount totalMentions avgSentimentScore
  }
}
"""

_PEAK_ARTICLES_QUERY = """
query PolicyPeakArticles(
  $entities: [String!]!, $startDate: String!, $endDate: String!, $limit: Int!
) {
  articles(
    page: 1
    limit: $limit
    filter: {entityCanonical: $entities, startDate: $startDate, endDate: $endDate}
    sort: DATE
  ) {
    found
    articles { uniqueId title agencyName agency publishedAt url }
  }
}
"""

_PEAK_SEARCH_QUERY = """
query PolicyPeakSearch($query: String!, $filter: ArticleFilter) {
  search(query: $query, filter: $filter, page: 1) {
    found
    page
    articles { uniqueId title agencyName agency publishedAt url }
  }
}
"""

_POLICY_DETAILS_QUERY = """
query PolicyDetails($entityId: String!) {
  policyDetails(entityId: $entityId) {
    domain lifecyclePhase enablingLaws responsibleAgencies targetPopulation firstMentionedDate
  }
}
"""

# Limiar de volume relativo ao pico para classificação de fases:
# acima de 40% do pico → IMPLEMENTATION; abaixo → ROUTINE.
_IMPLEMENTATION_RATIO_THRESHOLD = 0.40
_PEAK_ARTICLES_LIMIT = 5

PHASE_DESCRIPTIONS = {
    "ANNOUNCED": "Fase de lançamento/anúncio — volume máximo de cobertura.",
    "IMPLEMENTATION": "Fase de implementação — cobertura sustentada acima de 40% do pico.",
    "ROUTINE": (
        "Fase de rotina — volume de cobertura abaixo de 40% do pico; política consolidada "
        "ou em desaceleração comunicacional."
    ),
}


@dataclass
class MonthPoint:
    """Um mês da série (soma das agências)."""

    month: date  # primeiro dia do mês
    article_count: int = 0
    by_agency: dict[str, int] = field(default_factory=dict)  # nome → artigos
    phase: str | None = None  # None = não classificado (mês corrente parcial)
    ratio: float = 0.0
    partial: bool = False  # mês de referência, ainda em curso

    @property
    def label(self) -> str:
        return self.month.strftime("%Y-%m")

    @property
    def table_label(self) -> str:
        return f"{self.label} (parcial)" if self.partial else self.label

    @property
    def dominant(self) -> str | None:
        if not self.by_agency:
            return None
        return max(self.by_agency, key=lambda name: (self.by_agency[name], name))


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def monthly_series(coverage: list[dict], until: date | None = None) -> list[MonthPoint]:
    """Soma as agências por mês e preenche com 0 os meses sem cobertura, do primeiro mês
    com cobertura até ``until`` (mês de referência, marcado como parcial) ou até o último
    mês com cobertura, o que vier depois."""
    by_month: dict[date, MonthPoint] = {}
    for point in coverage:
        try:
            month = period_start(point.get("period") or "").replace(day=1)
        except ValueError:
            continue
        mp = by_month.setdefault(month, MonthPoint(month))
        count = point.get("articleCount") or 0
        agency = point.get("agencyName") or point.get("agencyKey") or "Desconhecida"
        mp.article_count += count
        mp.by_agency[agency] = mp.by_agency.get(agency, 0) + count
    if not by_month:
        return []
    series = []
    month, last = min(by_month), max(by_month)
    if until is not None:
        until = until.replace(day=1)
        last = max(last, until)
    while month <= last:
        point = by_month.get(month) or MonthPoint(month)
        point.partial = month == until
        series.append(point)
        month = _next_month(month)
    return series


def classify_phases(series: list[MonthPoint]) -> MonthPoint | None:
    """Marca a fase de cada mês e devolve o mês de pico (o primeiro, em empate).

    - ANNOUNCED: o mês de maior volume;
    - IMPLEMENTATION: ≥ 40% do pico;
    - ROUTINE: abaixo disso.
    """
    if not series:
        return None
    peak = max(series, key=lambda p: (p.article_count, -p.month.toordinal()))
    for point in series:
        point.ratio = point.article_count / peak.article_count if peak.article_count else 0.0
        if point is peak:
            point.phase = "ANNOUNCED"
        elif point.ratio >= _IMPLEMENTATION_RATIO_THRESHOLD:
            point.phase = "IMPLEMENTATION"
        else:
            point.phase = "ROUTINE"
    return peak


def narrative_anchors(series: list[MonthPoint]) -> dict[str, str]:
    """Agência dominante (soma de artigos) em cada fase — âncora narrativa."""
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for point in series:
        if point.phase is None:  # mês parcial, fora da classificação
            continue
        for agency, count in point.by_agency.items():
            totals[point.phase][agency] += count
    return {
        phase: max(agencies, key=lambda a: (agencies[a], a))
        for phase, agencies in totals.items()
        if agencies
    }


async def _optional(coro):
    try:
        return await coro
    except Exception:  # metadados e artigos são opcionais: a tool segue sem eles
        return None


async def _peak_articles(
    client: GobusGraphQLClient, entity_id: str, name: str, peak: MonthPoint
) -> list[dict]:
    start = f"{peak.month.isoformat()}T00:00:00+00:00"
    end = f"{_next_month(peak.month).isoformat()}T00:00:00+00:00"
    data = await _optional(
        client.execute(
            _PEAK_ARTICLES_QUERY,
            {
                "entities": [entity_id],
                "startDate": start,
                "endDate": end,
                "limit": _PEAK_ARTICLES_LIMIT,
            },
        )
    )
    articles = ((data or {}).get("articles") or {}).get("articles") or []
    if articles:
        return articles
    # artigo sem a entidade canônica marcada: busca pelo nome, na mesma janela
    data = await _optional(
        client.execute(
            _PEAK_SEARCH_QUERY,
            {"query": name, "filter": {"startDate": start, "endDate": end}},
        )
    )
    return ((data or {}).get("search") or {}).get("articles") or []


async def get_policy_lifecycle(
    policy_name: str,
    client: GobusGraphQLClient,
    date_from: str = "2024-01-01",
    *,
    today: date | None = None,
) -> str:
    """Ciclo de vida comunicacional de uma política pública no portal Gov.BR.

    Resolve o nome da política, obtém a cobertura mensal (somando as agências) até o mês
    de referência e classifica cada mês fechado em ANNOUNCED (pico), IMPLEMENTATION (≥40%
    do pico) ou ROUTINE. A fase atual é a do último mês fechado; o mês corrente aparece
    como parcial. Identifica a agência dominante por mês e por fase e lista artigos do
    mês de pico.

    Args:
        policy_name: Nome ou alias da política (ex: "Pé-de-Meia").
        client: Cliente GraphQL.
        date_from: Data de início da série temporal (ISO). Padrão: "2024-01-01".
        today: D, dia de referência em BRT (injetável; padrão: hoje).

    Returns:
        Markdown com fases mensais, âncoras narrativos e perspectiva da fase atual.
    """
    search_data = await client.execute(
        _ENTITY_SEARCH_QUERY,
        {"query": policy_name, "entityType": "POLICY", "limit": 1},
    )
    hits = search_data.get("entitySearch") or []
    if not hits:
        return f"Política não encontrada: **{policy_name}**"

    entity = hits[0]
    entity_id = entity["entityId"]
    canonical_name = entity["canonicalName"]

    coverage_data, policy_data = await asyncio.gather(
        client.execute(
            _ENTITY_COVERAGE_QUERY,
            {"entityId": entity_id, "granularity": "MONTH", "dateFrom": date_from},
        ),
        _optional(client.execute(_POLICY_DETAILS_QUERY, {"entityId": entity_id})),
    )
    today = today or reference_date()
    series = monthly_series(coverage_data.get("entityCoverage") or [], until=today)
    if not series:
        return (
            f"**{canonical_name}**: dados insuficientes de cobertura para análise do "
            "ciclo de vida. Tente ampliar o período com um date_from anterior."
        )
    pd = (policy_data or {}).get("policyDetails")

    # o mês corrente é parcial: fica fora da classificação, salvo se for o único mês
    closed = [p for p in series if not p.partial]
    partial = next((p for p in series if p.partial), None)
    peak = classify_phases(closed or series)
    anchors = narrative_anchors(series)
    current = (closed or series)[-1]
    current_txt = "parcial" if current.partial else "último mês fechado"
    last_with_data = next((p for p in reversed(series) if p.article_count), current)
    articles = await _peak_articles(client, entity_id, canonical_name, peak)

    lines = [f"# Ciclo de Vida: {canonical_name}"]
    lines.append(
        f"\n**ID:** `{entity_id}` · **Fase atual:** {current.phase} "
        f"({current.label}, {current_txt})"
    )
    lines.append(
        f"**Pico:** {peak.label} ({peak.article_count} artigos) · "
        f"**Último mês com cobertura:** {last_with_data.table_label} · "
        f"**Total no período:** {sum(p.article_count for p in series)} artigos"
    )
    notices = []
    gap = _months_between(last_with_data.month, current.month)
    if gap > 0:
        months_txt = "1 mês fechado" if gap == 1 else f"{gap} meses fechados"
        notices.append(
            f"Sem cobertura desde {last_with_data.label}: {months_txt} sem artigos "
            f"(até {current.label})."
        )
    if partial is not None and partial is not peak and partial.article_count > peak.article_count:
        notices.append(
            f"O mês corrente (parcial) já supera o pico dos meses fechados: "
            f"{partial.article_count} artigos em {partial.label}."
        )
    if pd:
        if pd.get("domain"):
            lines.append(f"**Domínio:** {pd['domain']}")
        if pd.get("targetPopulation"):
            lines.append(f"**População-alvo:** {', '.join(pd['targetPopulation'])}")
        if pd.get("responsibleAgencies"):
            lines.append(f"**Agências responsáveis:** {', '.join(pd['responsibleAgencies'])}")
    for notice in notices:
        lines.append(f"\n> {notice}")

    lines.append("\n## Fases Identificadas (por mês, somando as agências)\n")
    lines.append("| Mês | Artigos | Fase | Agência Dominante |")
    lines.append("|-----|---------|------|-------------------|")
    for point in series:
        lines.append(
            f"| {point.table_label} | {point.article_count} | {point.phase or '—'} "
            f"| {point.dominant or '—'} |"
        )

    lines.append("\n## Âncoras Narrativos por Fase\n")
    for phase in ("ANNOUNCED", "IMPLEMENTATION", "ROUTINE"):
        if phase in anchors:
            lines.append(f"- **{phase}:** {anchors[phase]}")

    lines.append("\n## Perspectiva Atual\n")
    lines.append(
        f"A política **{canonical_name}** está na fase **{current.phase}** "
        f"({current_txt}: {current.label}, {current.article_count} artigos)."
    )
    lines.append(PHASE_DESCRIPTIONS[current.phase])
    if partial is not None and partial is not current:
        lines.append(
            f"Mês corrente ({partial.label}, parcial): {partial.article_count} artigos, "
            "fora da classificação."
        )

    if articles:
        lines.append(f"\n## Artigos Representativos (pico: {peak.label})\n")
        for art in articles[:3]:
            title = art.get("title") or "Sem título"
            when = (art.get("publishedAt") or "")[:10]
            agency = art.get("agencyName") or art.get("agency") or ""
            url = art.get("url") or ""
            lines.append(f"- [{title}]({url}) — {agency} · {when}")

    return "\n".join(lines)
