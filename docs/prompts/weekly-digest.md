# weekly_digest

Boletim semanal em linguagem cidadã sobre o que o governo federal publicou na semana. Atende o caso de uso [UC-10](../casos-de-uso.md) e é voltado para o cidadão comum — texto simples, sem jargão, pronto para newsletter ou redes sociais.

## Workflow

O prompt guia o LLM por 4 passos sequenciais:

1. **Temas em alta** — [`detect_trends`](../tools/detect-trends.md) com `window_days=7` e `baseline_days=28` — identifica os temas mais relevantes da semana.
2. **Artigos mais vistos** — [`search_news`](../tools/search-news.md) ordenado por `view_count` — encontra os artigos mais populares da semana.
3. **Notícias representativas** — [`search_news`](../tools/search-news.md) + [`get_article`](../tools/get-article.md) — para os 3 temas em maior crescimento, busca exemplos concretos e lê os 2 mais relevantes de cada.
4. **Boletim em linguagem cidadã** — síntese — o LLM escreve um boletim de 400-500 palavras com título datado, destaques da semana, o mais visto, temas emergentes e links para saber mais.

## Como ativar

No Claude, envie:

> "O que o governo publicou de mais importante essa semana?"

ou

> "Monta um boletim semanal do governo em linguagem simples."

## Parâmetros

Este prompt não recebe parâmetros — sempre cobre a semana corrente (janela de 7 dias contra baseline de 28 dias).
