# monitor_agency

Briefing diário de comunicação para uma agência governamental. Atende o caso de uso [UC-01](../casos-de-uso.md) e é voltado para assessores de comunicação que precisam saber, todo dia, o que o seu órgão publicou e o que está repercutindo.

## Workflow

O prompt guia o LLM por 4 passos sequenciais:

1. **Busca de publicações recentes** — [`gobus_search_news`](../tools/search-news.md) com `agency_key` — recupera as últimas publicações da agência na janela de dias informada.
2. **Análise de volume e performance** — [`gobus_get_agency_analytics`](../tools/get-agency-analytics.md) com `agencies=[agency_key]` e `granularity=DAY` — extrai métricas diárias de publicação.
3. **Destaques** — análise dos resultados da busca — identifica os artigos de maior impacto (anúncios de programas, valores, prazos e serviços ao cidadão). O `trendingScore` por artigo está nulo no acervo e não é usado.
4. **Resumo narrativo** — síntese — o LLM escreve um briefing executivo de 200-300 palavras cobrindo volume, temas principais, artigos de destaque, sentimento geral e recomendações para a equipe.

## Como ativar

No Claude, envie:

> "O que o Ministério da Saúde publicou ontem?"

ou

> "Me dá um briefing de comunicação do MEC dos últimos 3 dias."

## Parâmetros

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `agency_key` | Chave (código curto) da agência | `"mec"` |
| `agency_name` | Nome completo da agência (opcional, melhora o texto) | `"Ministério da Educação"` |
| `days` | Janela de dias para análise (default `1`) | `3` |
