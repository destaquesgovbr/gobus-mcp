"""Prompts do Gobus: cada um devolve o roteiro como ``str`` (uma mensagem de usuário).

No fastmcp 3.4 um prompt só pode devolver ``str``, ``Message`` ou lista deles; um
``list[dict]`` quebra o ``prompts/get``. Os argumentos chegam do host como texto (e o
Claude Desktop manda ``""`` nos opcionais em branco): os numéricos passam por ``_int_arg``.
"""


def _int_arg(value: int | str | None, default: int, lo: int, hi: int) -> int:
    """Inteiro de um argumento de prompt, limitado a ``[lo, hi]``.

    Vazio, ``None`` ou texto que não é inteiro → ``default``.
    """
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))
