"""Formatação compartilhada do Markdown das tools: link, rótulo de agência e inteiros."""

from urllib.parse import urlsplit

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
