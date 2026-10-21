# search_news

Busca notícias no acervo do Gov.BR por texto livre e, opcionalmente, por agência. É o ponto de entrada mais comum: use para encontrar artigos sobre um tema e obter os `uniqueId` necessários para ler o conteúdo completo via [get_article](get-article.md).

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `query` | `str` | Sim | — | Texto livre para busca full-text; `"*"` lista todas as publicações (use com `agency_key` e/ou datas) |
| `agency_key` | `str` | Não | — | Chave da agência para filtrar (ex: `"mec"`, `"saude"`) |
| `date_from` | `str` | Não | — | Primeiro dia, `AAAA-MM-DD`, inclusivo (dia inteiro em Brasília) |
| `date_to` | `str` | Não | — | Último dia, `AAAA-MM-DD`, inclusivo (dia inteiro em Brasília); `date_from == date_to` = um único dia |
| `page` | `int` | Não | `1` | Página de resultados |
| `limit` | `int` | Não | `10` | Resultados por página (máx 50) |

## Retorno

Retorna Markdown com um cabeçalho de total de artigos encontrados (ponto de milhar) e paginação, seguido de um bloco por artigo com o **título como link Markdown** `[título](url)`, agência, data de publicação (dia de Brasília), resumo e `uniqueId`. Sem URL `http(s)`, o título sai em texto puro. Artigos em alta recebem um indicador de trending.

**Exemplo de saída:**

```
# Resultados: vacinação

**1.243 artigos encontrados** (página 1)

## [Campanha Nacional de Vacinação contra a Gripe é prorrogada](https://www.gov.br/saude/...)
**[saude] Ministério da Saúde** · 2024-05-12
A campanha foi estendida até o fim de maio devido à baixa adesão...
ID: `ms-2024-05-12-vacinacao-gripe`

## [Ministério distribui mais de 80 milhões de doses](https://www.gov.br/saude/...)
**[saude] Ministério da Saúde** · 2024-05-08
O quantitativo cobre todos os grupos prioritários da campanha...
ID: `ms-2024-05-08-doses-vacina`
```

## Exemplos

**Briefing de ministério:**
> "O que o Ministério da Saúde publicou sobre vacinação este mês?"

**Tudo o que uma agência publicou num dia:**
> `gobus_search_news(query="*", agency_key="mec", date_from="2026-10-20", date_to="2026-10-20")`

**Pesquisa temática ampla:**
> "Busque notícias sobre energia solar no acervo do Gov.BR"

**Navegação paginada:**
> "Mostre a próxima página de resultados sobre reforma tributária"

## Notas

- O filtro de agência usa `filter: {agencies: [...]}` no schema; informe a `agency_key` (código curto da agência), não o nome completo.
- **Datas em Brasília, fim inclusivo:** o `search()` da graphql-api compara `published_at >= startDate` e `published_at <= endDate` (segundos inteiros), e uma data pura vira 00:00 UTC — com `date_from == date_to` a busca voltava vazia. Por isso a tool converte `AAAA-MM-DD` nos limites do dia em Brasília: `date_from` → `T00:00:00-03:00` e `date_to` → `T23:59:59-03:00` (o dia entra inteiro e o seguinte fica fora). Data com hora (ex.: `2026-10-20T09:00:00-03:00`) passa como veio.
- Data inválida (ex.: `20/10/2026`) ou `date_from` depois de `date_to` devolve uma mensagem, sem consultar a API.
- `query` vazia vira `"*"` (o `search()` rejeita texto vazio).
- A data exibida é o dia de publicação em Brasília (a API devolve UTC; um artigo das 23h30 de 20/10 aparece em 20/10, não em 21/10).
- O `search()` da API devolve até 20 artigos por página; para listar mais, use `page`.
- `limit` acima de 50 é limitado a 50 pelo servidor.
- O indicador de trending só aparece quando `trendingScore` é maior que 1.0.
