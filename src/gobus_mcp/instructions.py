"""Instruções do servidor (``initialize.instructions``): o que o host passa ao LLM antes
de qualquer tool. Curtas (≤ 1,5 KB), em pt-BR; as datas do defeso vêm do ``calendario``."""

from gobus_mcp.calendario import BLACKOUTS, BlackoutPeriod


def _blackout_line(period: BlackoutPeriod) -> str:
    return (
        f"- {period.label}: {period.start:%d/%m}–{period.end:%d/%m/%Y} (recuperação até "
        f"{period.recovery_until:%d/%m/%Y}). Compare janelas equivalentes e avise quando o "
        "período cair no defeso."
    )


SERVER_INSTRUCTIONS = "\n".join(
    [
        "Gobus: acervo de notícias do governo federal (Gov.BR), com entidades e métricas "
        "por agência. Somente leitura.",
        "- Pessoa, órgão, programa ou lugar: resolva antes com gobus_resolve_entity e use o "
        "entityId nas demais tools.",
        "- Cite artigos com link Markdown onde o fato aparece: [título](url), só com URLs "
        "devolvidas pelas tools. Sem URL, cite o unique_id e ofereça gobus_get_article.",
        "- gobus_search_news: date_from/date_to AAAA-MM-DD são dias inteiros em horário de "
        'Brasília (ambos inclusivos); query="*" lista tudo.',
        '- "indisponível" = sem dado, nunca zero. Antes de concluir ausência, consulte '
        "gobus://health/pipelines.",
        *(_blackout_line(p) for p in BLACKOUTS),
        "- Execute em paralelo as chamadas independentes.",
        "- Termine com 2–3 perguntas de continuação que usem outras tools do Gobus.",
    ]
)
