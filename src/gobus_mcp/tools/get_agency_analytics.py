from datetime import date

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import agency_analytics_date_to
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import metric_coverage_status, sentiment_analytics_status
from gobus_mcp.readability import describe_flesch

_ANALYTICS_QUERY = """
query AgencyAnalytics(
    $agencies: [String!]!
    $dateFrom: String!
    $dateTo: String!
    $granularity: Granularity!
) {
    agencyAnalytics(
        agencies: $agencies
        dateFrom: $dateFrom
        dateTo: $dateTo
        granularity: $granularity
    ) {
        period
        agencyKey
        agencyName
        articleCount
        avgSentimentScore
        pctPositive
        pctNegative
        avgReadabilityFlesch
        avgWordCount
    }
}
"""


def _period(raw: str | None) -> str:
    """``'2026-09-01 00:00:00+00'`` → ``'2026-09-01'``."""
    return (raw or "")[:10]


def _row_metrics(row: dict) -> list[str]:
    """Métricas de uma linha; nulo vira "indisponível", nunca 0."""
    count = row.get("articleCount") or 0
    sent = row.get("avgSentimentScore")
    pct_pos = row.get("pctPositive")
    pct_neg = row.get("pctNegative")
    flesch = row.get("avgReadabilityFlesch")
    avg_wc = row.get("avgWordCount")

    metrics = [f"**{count}** artigos"]
    if sent is None:
        # sem score médio, o pctPositive 0.0 da API é artefato (não há rótulo de sentimento)
        metrics.append("sentimento indisponível")
    else:
        tone = f"sentimento {sent:.2f}"
        if pct_pos is not None:
            neg_part = f" / {pct_neg * 100:.0f}% neg" if pct_neg is not None else ""
            tone += f" · 😊 {pct_pos * 100:.0f}% pos{neg_part}"
        metrics.append(tone)
    if flesch is None:
        metrics.append("legibilidade indisponível")
    else:
        metrics.append(f"legibilidade {describe_flesch(flesch)}")
    if avg_wc is None:
        metrics.append("📝 palavras/artigo indisponível")
    else:
        metrics.append(f"📝 {avg_wc:.0f} palavras/artigo")
    return metrics


def _api_date_to(date_to: str, granularity: str) -> str:
    """O ``date_to`` do usuário é inclusivo em toda granularidade; a API trata o ``dateTo``
    de MONTH/WEEK como exclusivo (00:00), então soma 1 dia. Data inválida segue como veio
    (a API devolve o erro de formato)."""
    try:
        last_day = date.fromisoformat(date_to)
    except ValueError:
        return date_to
    return agency_analytics_date_to(last_day, granularity)


async def _unknown_agencies(agencies: list[str], catalog: AgencyCatalog) -> list[str]:
    """Mensagens de validação das chaves que não estão no catálogo."""
    messages = []
    for key in agencies:
        try:
            check = await catalog.validate(key)
        except Exception:  # catálogo fora do ar: sem sugestão
            return []
        if not check.ok:
            messages.append(f"- {check.message}")
    return messages


async def get_agency_analytics(
    agencies: list[str],
    date_from: str,
    date_to: str,
    client: GobusGraphQLClient,
    granularity: str = "MONTH",
    *,
    catalog: AgencyCatalog | None = None,
) -> str:
    """Métricas de publicação de uma ou mais agências num período.

    Args:
        agencies: Lista de agency_keys (ex: ["mec", "saude"])
        date_from: Data de início ISO (ex: "2024-01-01")
        date_to: Data de fim ISO, inclusiva em toda granularidade (ex: "2024-12-31")
        granularity: DAY | WEEK | MONTH (default: MONTH)
        catalog: catálogo de agências (nomes humanos e validação das chaves)

    Returns:
        Markdown com tabela de métricas por agência e período. Métrica nula aparece como
        "indisponível" (nunca 0); Flesch na faixa única (0/25/50/75), limitado a 0–100.
    """
    catalog = catalog or AgencyCatalog(client)
    data = await client.execute(
        _ANALYTICS_QUERY,
        {
            "agencies": agencies,
            "dateFrom": date_from,
            "dateTo": _api_date_to(date_to, granularity),
            "granularity": granularity.upper(),
        },
    )
    rows = data.get("agencyAnalytics") or []

    if not rows:
        lines = [f"Nenhum dado encontrado para {', '.join(agencies)} em {date_from}–{date_to}"]
        lines.extend(await _unknown_agencies(agencies, catalog))
        return "\n".join(lines)

    lines = [
        f"# Analytics: {', '.join(agencies)}\n**{date_from} → {date_to}** "
        f"(granularity: {granularity})\n"
    ]
    for status in (
        metric_coverage_status("readability", rows, "avgReadabilityFlesch"),
        sentiment_analytics_status(rows),
    ):
        if status.status != "ok":
            lines.append(f"> {status.message}")

    current_period = None
    for row in rows:
        period = _period(row.get("period"))
        if period != current_period:
            current_period = period
            lines.append(f"\n## {current_period}")
        key = row.get("agencyKey") or ""
        agency = await catalog.display_name(key, row.get("agencyName"))
        lines.append(f"- **{agency}**: {' · '.join(_row_metrics(row))}")

    return "\n".join(lines)
