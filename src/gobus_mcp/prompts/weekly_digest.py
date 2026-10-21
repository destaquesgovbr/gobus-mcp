from datetime import date

from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.prompts import CITE_AS_LINKS, _calendar_note


def weekly_digest_prompt(*, today: date | None = None) -> str:
    """Boletim semanal para o cidadão — o que o governo fez esta semana.

    Args:
        today: Dia de referência D em BRT (padrão: hoje); a semana é ``[D−7, D−1]``
    """
    week = closed_window(7, today or reference_date())
    start_fmt = "%d/%m" if week.start.year == week.end.year else "%d/%m/%Y"
    period = f"{week.start.strftime(start_fmt)} a {week.end.strftime('%d/%m/%Y')}"
    date_from, date_to = week.start.isoformat(), week.end.isoformat()
    note = _calendar_note(week)
    note = f"\n{note}\n" if note else ""
    return f"""Crie um boletim semanal acessível sobre o que o governo federal publicou na semana de {period} (dias fechados, horário de Brasília).
{note}
## Roteiro de produção

### 1. Temas em alta
Use `gobus_detect_trends` com window_days=7 e baseline_days=28 para identificar os temas mais relevantes da semana.

### 2. Panorama da semana
Use `gobus_get_agency_summary` com days=7 para as 2 ou 3 agências que mais aparecem nos temas do passo 1 e obtenha volume e temas em alta de cada uma.

### 3. Notícias representativas
Para os 3 temas em maior crescimento, chame `gobus_search_news(query="<termos do tema>", date_from="{date_from}", date_to="{date_to}")` para encontrar exemplos concretos. Use `gobus_get_article` nos 2 mais relevantes de cada tema.

> **Dica de paralelismo:** Para os temas retornados por `gobus_detect_trends` (step 1),
> as chamadas `gobus_search_news` de cada tema (step 3) são independentes entre si
> e podem ser executadas em paralelo.

### 4. Boletim em linguagem cidadã
Escreva um boletim de 400-500 palavras com:

**Título:** "O que o governo fez esta semana — {period}"

**Destaques da semana:** 3-5 pontos principais em linguagem simples (nível ensino médio)

**Quem mais publicou:** As agências do passo 2 e seus temas, com 2-3 linhas cada.

**Temas emergentes:** O que está crescendo no governo esta semana e por quê pode importar para o cidadão.

**Para saber mais:** Links para os artigos mais relevantes.

{CITE_AS_LINKS}

**Formato:** Linguagem simples, direta, sem jargão técnico. Adequada para ser publicada em redes sociais ou newsletter."""
