# get_entity_profile

Monta o perfil completo de uma entidade a partir do seu nome: dados canônicos, cobertura temporal (quantos artigos e menções por mês) e entidades relacionadas por co-menção. Use para entender a presença de uma entidade na mídia ao longo do tempo sem precisar resolver o ID manualmente antes.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `entity_name` | `str` | Sim | — | Nome ou alias da entidade |
| `entity_type` | `str` | Não | — | Tipo — `ORG`, `PER`, `LOC`, `EVENT`, `POLICY`, `LAW` |
| `date_from` | `str` | Não | — | Data de início no formato ISO (ex: `"2024-01-01"`) |
| `date_to` | `str` | Não | — | Data de fim no formato ISO (ex: `"2024-12-31"`) |

## Retorno

Retorna Markdown com cabeçalho da entidade (nome canônico, tipo, ID, Wikidata, total de artigos, aliases, descrição), uma seção de cobertura mensal com artigos/menções e sentimento médio, e uma seção de entidades relacionadas por co-menção.

**Exemplo de saída:**

```
# Ministério da Educação (ORG)
**ID:** `Q1808456` · [Wikidata](https://www.wikidata.org/wiki/Q1808456)
**Artigos:** 8.412
**Aliases:** MEC, Min. Educação

Órgão do governo federal responsável pela política nacional de educação.

## Cobertura (1.204 artigos, 3.890 menções)
- **2024-03** — 112 artigos (Ministério da Educação) · sentimento 0.18
- **2024-04** — 98 artigos (Ministério da Educação) · sentimento 0.05

## Entidades relacionadas (co-menção)
- **Fundo Nacional de Desenvolvimento da Educação** (ORG) · 240 artigos
- **Camilo Santana** (PER) · 187 artigos
```

## Exemplos

**Briefing de presença na mídia:**
> "Faça um perfil do Ministério da Saúde no último ano"

**Recorte temporal:**
> "Como foi a cobertura do MEC entre janeiro e junho de 2024?"

**Mapa de associações:**
> "Com quais pessoas e órgãos o Ministério da Economia mais aparece junto?"

## Notas

- Esta tool executa **3 queries GraphQL em sequência**: `entitySearch` (resolve o nome no primeiro resultado), `entityCoverage` (cobertura temporal) e `relatedEntities` (relacionadas). É mais pesada que as demais; espere maior latência.
- A cobertura usa granularidade mensal (`MONTH`) e a saída mostra os últimos 12 períodos.
- As entidades relacionadas são limitadas às 8 mais fortes na saída.
- Como a entidade é resolvida pelo primeiro resultado da busca, use `entity_type` para desambiguar nomes comuns.
