# gobus://taxonomy-queries

Dicionário estático **categoria de tema → termos de busca** que funcionam bem no `gobus_search_news`. Liga os temas devolvidos por `gobus_detect_trends` a buscas concretas.

**URI:** `gobus://taxonomy-queries`
**Fonte:** constante `TAXONOMY_QUERIES` em `resources/taxonomy_queries.py` (sem chamada à graphql-api).

## Formato

```
# Dicionário de Termos por Categoria Taxonômica

Use em `gobus_search_news` para buscar artigos de cada categoria detectada por `gobus_detect_trends`.

## Saúde
`saúde pública` · `SUS` · `vacinação` · `hospital` · `medicamento`

## Educação
`educação` · `escola` · `universidade` · `ENEM` · `bolsa estudo`
…
```

## Quando usar

Depois de `gobus_detect_trends`: para cada tema em alta, rode `gobus_search_news` (em paralelo entre temas) com os termos da categoria.
