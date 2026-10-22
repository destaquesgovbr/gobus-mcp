"""Formatação compartilhada do Markdown das tools: link, rótulo de agência, números, plural,
datas, texto de erro e o rodapé "Para explorar"."""

import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from urllib.parse import urlsplit

from gobus_mcp.calendario import BRT

_SAFE_SCHEMES = frozenset({"http", "https"})


def md_link(text: str, url: str | None) -> str:
    """Link Markdown ``[text](url)`` para citar artigos.

    Só aceita URL ``http(s)``; sem URL válida devolve o texto puro. O texto tem os
    espaços normalizados e ``[``, ``]`` e ``\\`` escapados; a URL com espaço ou parênteses
    vai entre ``<…>`` e os sinais ``<``/``>`` dela são codificados.
    """
    label = " ".join((text or "").split())
    target = (url or "").strip()
    if not target or any(c in target for c in "\r\n") or not _is_http(target):
        return label
    target = target.replace("<", "%3C").replace(">", "%3E")
    if any(c in target for c in " ()"):
        target = f"<{target}>"
    label = label or target.strip("<>")
    escaped = label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return f"[{escaped}]({target})"


def _is_http(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in _SAFE_SCHEMES and bool(parts.netloc)


def article_ref(article: dict, max_title: int | None = None) -> str:
    """Artigo numa linha de lista: ``[título](url) · `id``` (sem URL, só o título; sem id,
    só o link). ``max_title`` corta o título."""
    title = article.get("title") or "Sem título"
    if max_title is not None:
        title = title[:max_title]
    uid = article.get("uniqueId") or ""
    link = md_link(title, article.get("url"))
    return f"{link} · `{uid}`" if uid else link


def agency_label(code: str | None, name: str | None) -> str:
    """Rótulo de agência: ``[código] Nome``, só ``[código]`` ou só o nome."""
    if code and name:
        return f"[{code}] {name}"
    if code:
        return f"[{code}]"
    return name or ""


def article_agency(article: Mapping, names: Mapping[str, str]) -> tuple[str | None, str | None]:
    """``(código, nome)`` do órgão de um artigo (gobus-mcp#17).

    O código vem de ``agencyKey`` (``ArticleSummary``, GQL-1), de ``agency`` (``Article``)
    ou, sem os dois, de ``agencyName`` (o ``ArticleSummary`` antigo carrega a key nele). O
    nome é o do catálogo (``names`` = ``AgencyCatalog.display_names()``, resolvido uma vez
    por resposta); senão, o ``agencyName`` da API quando não é o próprio código (o
    ``search()`` devolve nulo: graphql-api#34).
    """
    code = article.get("agencyKey") or article.get("agency") or article.get("agencyName")
    api_name = article.get("agencyName")
    name = (names.get(code) if code else None) or (api_name if api_name != code else None)
    return code, name


def fmt_int(n: int) -> str:
    """Inteiro com ponto de milhar (pt-BR): ``1234567`` → ``1.234.567``."""
    return f"{n:,}".replace(",", ".")


def fmt_decimal(value: float, digits: int = 1) -> str:
    """Decimal pt-BR: ``4.14`` → ``4,1``; ``1234.5`` → ``1.234,5``."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def plural(count: int, singular: str, plural_form: str) -> str:
    """Contagem com o substantivo concordando: ``1 artigo``, ``1.234 artigos``."""
    return f"{fmt_int(count)} {singular if count == 1 else plural_form}"


def fmt_date(day: date) -> str:
    """Data no formato ``DD/MM/AAAA``."""
    return day.strftime("%d/%m/%Y")


def error_text(exc: BaseException) -> str:
    """Texto de uma exceção para notas da saída: a mensagem, ou o nome da classe sem ela."""
    return str(exc) or type(exc).__name__


def brt_day(published_at: str | None) -> str:
    """Dia ``AAAA-MM-DD`` de uma data ISO da API, em Brasília (a busca filtra por dia de
    Brasília). Sem fuso, o dia como veio; valor ilegível, os 10 primeiros caracteres."""
    if not published_at:
        return ""
    try:
        moment = datetime.fromisoformat(published_at)
    except ValueError:
        return published_at[:10]
    if moment.tzinfo is None:
        return moment.date().isoformat()
    return moment.astimezone(BRT).date().isoformat()


# ── rodapé "Para explorar" ──────────────────────────────────────────────────

FOLLOW_UPS_TITLE = "**Para explorar:**"
FOLLOW_UPS_MAX = 3
FOLLOW_UPS_MAX_BYTES = 400

FollowUp = tuple[str, str]  # (chamada concreta, por quê)


def tool_call(tool: str, **args: object) -> str:
    """Chamada concreta de tool: ``gobus_x(a="b", n=2, flag=true)``.

    Valores em JSON (strings entre aspas, ``true``/``false``, listas); ``None`` e ``""``
    ficam de fora. Crases viram aspas simples (a chamada vai em código inline).
    """
    parts = [
        f"{name}={json.dumps(value, ensure_ascii=False)}"
        for name, value in args.items()
        if value is not None and value != ""
    ]
    return f"{tool}({', '.join(parts)})".replace("`", "'")


def follow_ups(items: Iterable[FollowUp | None]) -> str:
    """Rodapé com até ``FOLLOW_UPS_MAX`` chamadas concretas, em até ``FOLLOW_UPS_MAX_BYTES``
    (UTF-8, título incluído). Item vazio ou repetido é ignorado; item que não cabe é
    pulado (o seguinte ainda pode entrar). Sem item, devolve ``""``."""
    lines = [FOLLOW_UPS_TITLE]
    used = len(FOLLOW_UPS_TITLE.encode())
    seen: set[str] = set()
    for item in items:
        if len(lines) > FOLLOW_UPS_MAX:
            break
        if not item or not item[0] or item[0] in seen:
            continue
        call, why = item
        line = f"- `{call}` — {why}" if why else f"- `{call}`"
        size = len(line.encode()) + 1  # + quebra de linha
        if used + size > FOLLOW_UPS_MAX_BYTES:
            continue
        seen.add(call)
        lines.append(line)
        used += size
    return "\n".join(lines) if len(lines) > 1 else ""


def with_follow_ups(markdown: str, items: Iterable[FollowUp | None]) -> str:
    """``markdown`` + linha em branco + rodapé (sem rodapé, ``markdown`` intacto)."""
    footer = follow_ups(items)
    return f"{markdown.rstrip()}\n\n{footer}" if footer else markdown
