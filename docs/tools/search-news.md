# search_news

Busca notícias no acervo do Gov.BR por texto livre e, opcionalmente, por agência. É o ponto de entrada mais comum: use para encontrar artigos sobre um tema e obter os `uniqueId` necessários para ler o conteúdo completo via [get_article](get-article.md).

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `query` | `str` | Sim | — | Texto livre para busca semântica/full-text |
| `agency_key` | `str` | Não | — | Chave da agência para filtrar (ex: `"mec"`, `"ms"`) |
| `page` | `int` | Não | `1` | Página de resultados |
| `limit` | `int` | Não | `10` | Resultados por página (máx 50) |

## Retorno

Retorna Markdown com um cabeçalho de total de artigos encontrados e paginação, seguido de um bloco por artigo com título, agência, data de publicação, resumo, URL e `uniqueId`. Artigos em alta recebem um indicador de trending.

**Exemplo de saída:**

```
# Resultados: vacinação

**1.243 artigos encontrados** (página 1)

## Campanha Nacional de Vacinação contra a Gripe é prorrogada
**Ministério da Saúde** · 2024-05-12 🔥 trending=3.2
A campanha foi estendida até o fim de maio devido à baixa adesão...
🔗 https://www.gov.br/saude/...  ID: `ms-2024-05-12-vacinacao-gripe`

## Ministério distribui mais de 80 milhões de doses
**Ministério da Saúde** · 2024-05-08
O quantitativo cobre todos os grupos prioritários da campanha...
🔗 https://www.gov.br/saude/...  ID: `ms-2024-05-08-doses-vacina`
```

## Exemplos

**Briefing de ministério:**
> "O que o Ministério da Saúde publicou sobre vacinação este mês?"

**Pesquisa temática ampla:**
> "Busque notícias sobre energia solar no acervo do Gov.BR"

**Navegação paginada:**
> "Mostre a próxima página de resultados sobre reforma tributária"

## Notas

- O filtro de agência usa `filter: {agencies: [...]}` no schema; informe a `agency_key` (código curto da agência), não o nome completo.
- `limit` acima de 50 é limitado a 50 pelo servidor.
- O indicador de trending só aparece quando `trendingScore` é maior que 1.0.
