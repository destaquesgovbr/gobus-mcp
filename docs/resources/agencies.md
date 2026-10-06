# gobus://agencies

Lista das agências do acervo do Destaques Gov.BR com **nome humano** e **código** (`agency_key`). É a referência para descobrir o código usado nas tools que filtram por agência.

**URI:** `gobus://agencies`
**Fonte:** catálogo de agências (`AgencyCatalog`): códigos e `isRepublisher` de `agencies`; nomes de `agencyAnalytics.agencyName` (a API devolve `label == code`). Cache de 24 h no servidor.

## Formato

Markdown em ordem alfabética de nome, com as **republicadoras** (EBC, Agência Brasil, TV Brasil) em seção própria.

```
# Agências Governamentais (156)

Use o código entre crases em `agency_key` / `agencies` das tools.

- **Advocacia-Geral da União** (`agu`)
- **Ministério da Saúde** (`saude`)
- **Ministério do Trabalho e Emprego** (`trabalho-e-emprego`)
…

## Republicadoras

Republicam conteúdo de outros órgãos; as análises de cobertura as tratam à parte.

- **Agência Brasil** (`agencia_brasil`)
- **Empresa Brasil de Comunicação** (`ebc`)
- **TV Brasil** (`tvbrasil`)
```

## Quando usar

Carregue este resource antes de invocar tools que recebem `agency_key` ou `agencies` (`gobus_search_news`, `gobus_get_agency_analytics`, `gobus_get_agency_summary`, `gobus_get_readability_recommendations`, `gobus_detect_trends`). As tools também validam o código e sugerem o certo: `"ms"` → `saude`, `"trabalho"`/`"mte"` → `trabalho-e-emprego`; `tcu`, `camara`, `senado` e `ibge` estão fora do catálogo.
