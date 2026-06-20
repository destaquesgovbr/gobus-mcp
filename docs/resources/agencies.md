# gobus://agencies

Lista completa das agências governamentais cadastradas no acervo do Destaques Gov.BR, com nome de exibição e código curto (`code`). É a referência canônica para descobrir qual `agency_key` usar nas tools que filtram por agência.

**URI:** `gobus://agencies`
**Atualização:** consultado ao vivo na `graphql-api` a cada leitura (sem cache local).

## Formato

Markdown com uma lista ordenada alfabeticamente por nome. Cada item traz o nome de exibição e, entre parênteses, o código curto usado como `agency_key`.

```
# Agências Governamentais

- **Ministério da Educação** (`mec`)
- **Ministério da Fazenda** (`fazenda`)
- **Ministério da Saúde** (`ms`)
- **Ministério do Trabalho e Emprego** (`mte`)
- **Ministério dos Transportes** (`transportes`)
```

## Quando usar

Carregue este resource antes de invocar qualquer tool que receba `agency_key` ou `agencies` (`search_news`, `get_agency_analytics`, `monitor_agency`, `draft_press_release`). Ele dá ao LLM o mapeamento entre o nome falado pelo usuário ("Ministério da Saúde") e o código aceito pela API (`ms`), evitando filtros vazios por chave incorreta.
