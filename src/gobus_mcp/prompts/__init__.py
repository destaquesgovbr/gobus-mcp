"""Prompts do Gobus: cada um devolve o roteiro como ``str`` (uma mensagem de usuário).

No fastmcp 3.4 um prompt só pode devolver ``str``, ``Message`` ou lista deles; um
``list[dict]`` quebra o ``prompts/get``. Os argumentos chegam do host como texto (e o
Claude Desktop manda ``""`` nos opcionais em branco): os numéricos passam por ``_int_arg``.
"""

from datetime import date

from gobus_mcp.calendario import BLACKOUTS, DateRange

CITE_AS_LINKS = (
    "**Citações:** cite cada artigo como link Markdown `[título](url)` no ponto em que o "
    "fato aparece, usando só as URLs devolvidas pelas tools (sem URL, cite o `unique_id`)."
)


def _int_arg(value: int | str | None, default: int, lo: int, hi: int) -> int:
    """Inteiro de um argumento de prompt, limitado a ``[lo, hi]``.

    Vazio, ``None`` ou texto que não é inteiro → ``default``.
    """
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def _fmt(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _calendar_note(window: DateRange) -> str:
    """Aviso de uma linha quando a janela toca o defeso eleitoral ou a recuperação que o
    segue; ``""`` fora deles."""
    for period in BLACKOUTS:
        if period.start <= window.end and window.start <= period.end:
            return (
                f"> **Atenção:** o período cai no {period.label.lower()} "
                f"({_fmt(period.start)} a {_fmt(period.end)}): o volume é menor e há agências "
                "caladas; compare só com janelas equivalentes e diga isso no texto."
            )
        if period.end < window.end and window.start <= period.recovery_until:
            return (
                "> **Atenção:** o período cai na recuperação pós-defeso (até "
                f"{_fmt(period.recovery_until)}): agências retomando a publicação; não compare "
                "com o defeso e diga isso no texto."
            )
    return ""
