import asyncio
import re
from collections import Counter
from datetime import UTC, date, datetime

from gobus_mcp.calendario import BRT, brt_day_end, brt_day_start
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.formatting import (
    FollowUp,
    agency_label,
    brt_day,
    fmt_int,
    md_link,
    tool_call,
    with_follow_ups,
)

PAGE_SIZE = 20  # o search() da graphql-api devolve 20 por página (fixo, sem limit)
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

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


def api_pages(page: int, limit: int) -> tuple[range, int]:
    """Páginas da API (de ``PAGE_SIZE``) que cobrem a página ``page`` da tool (de ``limit``
    artigos) e quantos artigos pular no começo da primeira delas.

    A página ``p`` da tool traz os resultados ``(p−1)·limit + 1 … p·limit``: com o limit
    padrão (10), a página 2 vem da 2ª metade da página 1 da API, e não da página 2 da API
    (que começa no 21º resultado)."""
    offset = (page - 1) * limit
    first = offset // PAGE_SIZE + 1
    last = (offset + limit - 1) // PAGE_SIZE + 1
    return range(first, last + 1), offset - (first - 1) * PAGE_SIZE


async def _fetch(client: GobusGraphQLClient, variables: dict, page: int, limit: int):
    """``(artigos da página da tool, found)``: a 1ª página da API dá o ``found``; as
    seguintes, só as que existem, vêm em paralelo."""
    pages, skip = api_pages(page, limit)
    data = await client.execute(_SEARCH_QUERY, {**variables, "page": pages[0]})
    result = data.get("search") or {}
    found = result.get("found") or 0
    articles = list(result.get("articles") or [])
    more = [p for p in pages[1:] if (p - 1) * PAGE_SIZE < found]
    if more:
        extra = await asyncio.gather(
            *(client.execute(_SEARCH_QUERY, {**variables, "page": p}) for p in more)
        )
        for data in extra:
            articles.extend((data.get("search") or {}).get("articles") or [])
    return articles[skip : skip + limit], found


def _follow_ups(
    articles: list[dict],
    *,
    query: str,
    agency_key: str | None,
    date_from: str,
    date_to: str,
    page: int,
    limit: int,
    found: int,
) -> list[FollowUp]:
    """Ler o 1º resultado, resumir o órgão que mais aparece e a próxima página com o mesmo
    ``limit`` (ou, na última, resolver a entidade buscada)."""
    items: list[FollowUp] = []
    first = articles[0].get("uniqueId")
    if first:
        items.append((tool_call("gobus_get_article", unique_id=first), "texto do 1º resultado"))
    agencies = Counter(a.get("agency") for a in articles if a.get("agency"))
    if agencies and not agency_key:
        top = agencies.most_common(1)[0][0]
        items.append(
            (tool_call("gobus_get_agency_summary", agency_key=top), "resumo do órgão mais citado")
        )
    if found > page * limit:
        next_page = tool_call(
            "gobus_search_news",
            query=query,
            agency_key=agency_key,
            date_from=date_from,
            date_to=date_to,
            page=page + 1,
            limit=None if limit == DEFAULT_LIMIT else limit,
        )
        items.append((next_page, "próxima página"))
    elif query != "*":
        items.append(
            (tool_call("gobus_resolve_entity", query=query), "entidade para perfil e rede")
        )
    return items


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
    do fim (com ou sem hora) devolve "Período inválido" sem consultar. A página ``page``
    tem ``limit`` artigos (até 50), montada das páginas de 20 da API (``api_pages``).
    """
    query = query.strip() or "*"  # search() rejeita query vazia; "*" lista tudo
    label = "todas as publicações" if query == "*" else query
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()
    page = max(page, 1)
    effective_limit = max(1, min(limit, MAX_LIMIT))
    variables: dict = {"query": query}

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

    articles, found = await _fetch(client, variables, page, effective_limit)

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

    follow = _follow_ups(
        articles,
        query=query,
        agency_key=agency_key,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=effective_limit,
        found=found,
    )
    return with_follow_ups("\n".join(lines), follow)
