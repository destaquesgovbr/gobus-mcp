"""Formatação compartilhada do Markdown das tools: link, rótulo de agência, inteiros, plural,
datas e texto de erro."""

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


def agency_label(code: str | None, name: str | None) -> str:
    """Rótulo de agência: ``[código] Nome``, só ``[código]`` ou só o nome."""
    if code and name:
        return f"[{code}] {name}"
    if code:
        return f"[{code}]"
    return name or ""


def fmt_int(n: int) -> str:
    """Inteiro com ponto de milhar (pt-BR): ``1234567`` → ``1.234.567``."""
    return f"{n:,}".replace(",", ".")


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
