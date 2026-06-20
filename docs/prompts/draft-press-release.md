# draft_press_release

Gera um rascunho de release de imprensa a partir de artigos já publicados no acervo. Atende o caso de uso [UC-05](../casos-de-uso.md) e serve redatores de assessoria que precisam de um ponto de partida factual e rastreável.

## Workflow

O prompt guia o LLM por 4 passos sequenciais:

1. **Pesquisa de base** — [`search_news`](../tools/search-news.md) com `query=topic` (e `agency_key`, se informado) — encontra os artigos de referência mais relevantes.
2. **Aprofundamento** — [`get_article`](../tools/get-article.md) nos 3 mais relevantes — obtém o conteúdo completo.
3. **Síntese de fatos** — análise — extrai dados e estatísticas, ações anunciadas, declarações de autoridades e impactos para a população.
4. **Rascunho do release** — síntese — o LLM escreve título, lead, corpo, citação e notas para editores, marcando com `[VERIFICAR]` todo dado não confirmado.

## Como ativar

No Claude, envie:

> "Crie um rascunho de release sobre emprego formal usando artigos do Ministério do Trabalho."

ou

> "Faça um release sobre vacinação com base nas notícias do Ministério da Saúde."

## Parâmetros

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `topic` | Tema ou assunto do release | `"emprego formal"` |
| `agency_key` | Filtrar artigos por agência (opcional) | `"mte"` |
| `limit` | Número de artigos de referência a usar (default `5`) | `5` |

## Notas

- O rascunho é factual mas não auditado: toda citação ou dado inferido vem marcado com `[VERIFICAR]`. Revise antes de publicar.
