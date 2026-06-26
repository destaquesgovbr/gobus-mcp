def monitor_agency_prompt(agency_key: str, agency_name: str = "", days: int = 1) -> list[dict]:
    """Briefing diário de uma agência governamental.

    Args:
        agency_key: Chave da agência (ex: "mec")
        agency_name: Nome completo da agência (opcional)
        days: Janela de dias para análise (default 1)
    """
    display = agency_name or agency_key
    return [{
        "role": "user",
        "content": {"type": "text", "text": f"""Crie um briefing de comunicação para a agência **{display}** dos últimos {days} dia(s).

Siga este roteiro:

## 1. Busca de publicações recentes
> **Dica de paralelismo:** As chamadas `search_news` (step 1) e `get_agency_analytics`
> (step 2) são independentes entre si — execute-as em paralelo para reduzir latência.

Use `search_news` com agency_key="{agency_key}" para buscar as últimas publicações.

## 2. Análise de volume e performance
Use `get_agency_analytics` com agencies=["{agency_key}"] e granularity=DAY para ver métricas de publicação.

## 3. Destaques em alta
Identifique artigos com trending_score > 1.0 nos resultados da busca.

## 4. Resumo narrativo
Com base nos dados, escreva um briefing executivo de 200-300 palavras cobrindo:
- Número de publicações e temas principais
- Artigos de destaque e por que estão em alta
- Sentimento geral das publicações (quando disponível)
- Recomendações para a equipe de comunicação

**Formato de saída:** Briefing em português, linguagem direta, adequada para assessor de comunicação."""}
    }]
