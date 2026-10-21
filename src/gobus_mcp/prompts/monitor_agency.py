from datetime import date

from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.prompts import CITE_AS_LINKS, _calendar_note, _int_arg


def monitor_agency_prompt(
    agency_key: str,
    agency_name: str = "",
    days: int | str = 1,
    *,
    today: date | None = None,
) -> str:
    """Briefing diário de uma agência governamental.

    Args:
        agency_key: Chave da agência (ex: "mec")
        agency_name: Nome completo da agência (opcional)
        days: Janela de dias fechados para análise (default 1 = ontem; limitado a 1–31)
        today: Dia de referência D em BRT (padrão: hoje); a janela é ``[D−days, D−1]``
    """
    n = _int_arg(days, 1, 1, 31)
    window = closed_window(n, today or reference_date())
    date_from, date_to = window.start.isoformat(), window.end.isoformat()
    display = agency_name or agency_key
    period = f"do dia {date_to}" if n == 1 else f"de {date_from} a {date_to} ({n} dias fechados)"
    note = _calendar_note(window)
    note = f"\n{note}\n" if note else ""
    return f"""Crie um briefing de comunicação para a agência **{display}** {period}, em horário de Brasília.
{note}
Siga este roteiro:

## 1. Busca de publicações do período
> **Dica de paralelismo:** As chamadas `gobus_search_news` (step 1) e `gobus_get_agency_analytics`
> (step 2) são independentes entre si — execute-as em paralelo para reduzir latência.

Chame `gobus_search_news(query="*", agency_key="{agency_key}", date_from="{date_from}", date_to="{date_to}", limit=20)`.
A busca devolve até 20 artigos por página: se o total encontrado passar disso, peça `page=2`, `page=3`…

## 2. Análise de volume e performance
Chame `gobus_get_agency_analytics(agencies=["{agency_key}"], date_from="{date_from}", date_to="{date_to}", granularity="DAY")` para ver as métricas de publicação por dia (os dias do analytics são em UTC: a contagem pode diferir em poucos artigos da busca, que usa dias de Brasília).

## 3. Destaques
Identifique os artigos de maior impacto entre os resultados da busca (anúncios de
programas, valores, prazos e serviços ao cidadão).

## 4. Resumo narrativo
Com base nos dados, escreva um briefing executivo de 200-300 palavras cobrindo:
- Número de publicações e temas principais
- Artigos de destaque e por que estão em alta
- Sentimento geral das publicações (quando disponível)
- Recomendações para a equipe de comunicação

{CITE_AS_LINKS}

**Formato de saída:** Briefing em português, linguagem direta, adequada para assessor de comunicação."""
