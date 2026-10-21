from datetime import date, datetime

from gobus_mcp.calendario import brt_day_end, brt_day_start
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.formatting import agency_label, brt_day, fmt_int, md_link

_SEARCH_QUERY = """
query SearchNews($query: String!, $filter: ArticleFilter, $page: Int) {
  search(query: $query, filter: $filter, page: $page) {
    articles {
      uniqueId title agencyName agency publishedAt summary url
      features { trendingScore viewCount }
    }
    found page
  }
}
"""


def _is_date_only(value: str) -> bool:
    return len(value) == 10


def _filter_date(value: str, *, end: bool) -> str:
    """``startDate``/``endDate`` do ``search()``.

    Só a data (``AAAA-MM-DD``) vira o limite do dia em Brasília — o fim inclui o dia
    inteiro, já que o upstream compara ``published_at <= endDate`` e a data pura vira
    00:00 UTC (``date_from == date_to`` voltava vazio). Data com hora passa como veio.
    Valor inválido levanta ``ValueError``.
    """
    if _is_date_only(value):
        day = date.fromisoformat(value)
        return brt_day_end(day) if end else brt_day_start(day)
    datetime.fromisoformat(value)
    return value


def _invalid_date(field: str, value: str) -> str:
    return (
        f"Data inválida em `{field}`: `{value}`. Use AAAA-MM-DD (ex.: 2026-10-20), que cobre "
        "o dia inteiro em horário de Brasília, ou data e hora ISO com fuso "
        "(ex.: 2026-10-20T09:00:00-03:00)."
    )


async def search_news(
    query: str,
    client: GobusGraphQLClient,
    agency_key: str | None = None,
    page: int = 1,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Busca artigos por texto livre (``"*"`` = todos), agência e período.

    ``date_from``/``date_to`` só com a data são dias inteiros em Brasília (ambos
    inclusivos); com hora, passam como vieram.
    """
    query = query.strip() or "*"  # search() rejeita query vazia; "*" lista tudo
    label = "todas as publicações" if query == "*" else query
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()
    effective_limit = min(limit, 50)
    variables: dict = {"query": query, "page": page}

    filter_dict: dict = {}
    if agency_key:
        filter_dict["agencies"] = [agency_key]
    for field, value, end, key in (
        ("date_from", date_from, False, "startDate"),
        ("date_to", date_to, True, "endDate"),
    ):
        if not value:
            continue
        try:
            filter_dict[key] = _filter_date(value, end=end)
        except ValueError:
            return _invalid_date(field, value)
    if _is_date_only(date_from) and _is_date_only(date_to) and date_from > date_to:
        return f"Período inválido: `date_from` ({date_from}) é posterior a `date_to` ({date_to})."
    if filter_dict:
        variables["filter"] = filter_dict

    data = await client.execute(_SEARCH_QUERY, variables)
    result = data.get("search") or {}
    articles = (result.get("articles") or [])[:effective_limit]
    found = result.get("found") or 0

    if not articles:
        msg = f"Nenhum resultado encontrado para: **{label}**"
        if agency_key:
            msg += f"\n\n> Chave `{agency_key}` não encontrou artigos. Consulte `gobus://agencies` para códigos válidos."
        return msg

    lines = [f"# Resultados: {label}\n\n**{fmt_int(found)} artigos encontrados** (página {page})\n"]
    for art in articles:
        pub_at = brt_day(art.get("publishedAt"))
        agency_str = agency_label(art.get("agency"), art.get("agencyName"))
        features = art.get("features") or {}
        trending = features.get("trendingScore")
        trending_str = f" 🔥 trending={trending:.1f}" if trending and trending > 1.0 else ""
        lines.append(
            f"## {md_link(art['title'], art.get('url'))}\n"
            f"**{agency_str}** · {pub_at}{trending_str}\n"
            f"{art.get('summary') or ''}\n"
            f"ID: `{art.get('uniqueId', '')}`\n"
        )

    return "\n".join(lines)
