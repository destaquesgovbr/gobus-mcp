import re
from datetime import UTC, date, datetime

from gobus_mcp.calendario import BRT, brt_day_end, brt_day_start
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

# Só a data: estendida (AAAA-MM-DD) ou "basic" (AAAAMMDD).
_DATE_ONLY_RE = re.compile(r"^\d{4}-?\d{2}-?\d{2}$")


def _is_date_only(value: str) -> bool:
    return bool(_DATE_ONLY_RE.match(value))


def _filter_date(value: str, *, end: bool) -> tuple[str, datetime]:
    """``startDate``/``endDate`` do ``search()`` e o instante que ele representa.

    Só a data (``AAAA-MM-DD`` ou o "basic" ``AAAAMMDD``) vira o limite do dia em Brasília —
    o fim inclui o dia inteiro, já que o upstream compara ``published_at <= endDate`` e a
    data pura vira 00:00 UTC (``date_from == date_to`` voltava vazio). Data com hora passa
    como veio; no formato "basic" (``20261020T100000-0300``), vai no estendido. O instante
    sem fuso é UTC, como no upstream (``datetime.fromisoformat(...).timestamp()`` no Cloud
    Run). Valor inválido levanta ``ValueError``.
    """
    if _is_date_only(value):
        day = date.fromisoformat(value)
        bound = brt_day_end(day) if end else brt_day_start(day)
        return bound, datetime.fromisoformat(bound)
    moment = datetime.fromisoformat(value)
    text = value if value[4:5] == "-" else moment.isoformat()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return text, moment


def _fmt_moment(moment: datetime) -> str:
    return moment.astimezone(BRT).strftime("%d/%m/%Y %H:%M:%S BRT")


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

    ``date_from``/``date_to`` só com a data (``AAAA-MM-DD`` ou ``AAAAMMDD``) são dias
    inteiros em Brasília (ambos inclusivos); com hora, passam como vieram. Início depois
    do fim (com ou sem hora) devolve "Período inválido" sem consultar.
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
    moments: dict[str, datetime] = {}
    for field, value, end, key in (
        ("date_from", date_from, False, "startDate"),
        ("date_to", date_to, True, "endDate"),
    ):
        if not value:
            continue
        try:
            filter_dict[key], moments[field] = _filter_date(value, end=end)
        except ValueError:
            return _invalid_date(field, value)
    if len(moments) == 2 and moments["date_from"] > moments["date_to"]:
        return (
            f"Período inválido: `date_from` ({date_from}) é posterior a `date_to` ({date_to}): "
            f"o início ({_fmt_moment(moments['date_from'])}) vem depois do fim "
            f"({_fmt_moment(moments['date_to'])}). Inverta as datas."
        )
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
