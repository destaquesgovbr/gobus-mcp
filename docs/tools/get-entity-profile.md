# get_entity_profile

Monta o perfil completo de uma entidade: dados canônicos, a série mensal inteira de cobertura (artigos próprios × republicações), as agências que mais publicaram, as cópias idênticas entre agências e as entidades relacionadas por co-menção. Aceita o ID canônico ou o nome.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `entity_name` | `str` | Sim | — | ID canônico (`"Q4294522"`, `"dgb_pe-de-meia"`) ou nome/alias |
| `entity_type` | `str` | Não | — | Tipo para desambiguar o nome: `ORG`, `PER`, `LOC`, `EVENT`, `POLICY`, `LAW` |
| `date_from` | `str` | Não | — | Data de início ISO (ex.: `"2026-01-01"`); sem ela, todo o acervo |
| `date_to` | `str` | Não | — | Data de fim ISO, **inclusiva** (ex.: `"2026-10-20"`) |
| `summary_only` | `bool` | Não | `false` | Só os totais e as 3 relacionadas mais fortes |

## Como o perfil é montado

1. **Entidade:** ID canônico (`Q…`/`dgb_…`) vai direto ao `entity(id)`, sem busca fuzzy; nome passa pelo `entitySearch(limit: 1)` (use `entity_type` para desambiguar).
2. **Em paralelo**, cada parte degradando sozinha (uma falha vira nota na seção, as demais seguem):
    - `entityCoverage(MONTH)` com `dateTo` = último dia + 1: o resolver compara `published_at <= dateTo::timestamptz` e a data pura vira 00:00 UTC, o que cortaria o último dia;
    - `relatedEntities(limit: 40)`;
    - contagem de cópias idênticas (`EntityDedupCounts`; a falha vira nota no fim);
    - catálogo de agências (republicadoras e códigos).

### Cabeçalho e série mensal

- **Cabeçalho:** "N artigos de A agências + R republicações · M menções", a soma de **todas** as linhas mês × agência do período. As republicadoras (Agência Brasil, TV Brasil, …) ficam em R e fora de A.
- **Tabela `Mês | Artigos | Republicações`:** um mês por linha, de `date_from` (ou do primeiro mês com artigo) até `date_to` (ou hoje), com 0 nos meses sem artigo. O mês corrente, ou cortado pela janela, aparece como "parcial". Até 24 meses; os anteriores viram totais anuais ("2023", "2024 (jan–out)"). A soma da tabela é igual ao cabeçalho.
- **Agências que mais publicaram:** as 5 não republicadoras com mais artigos, com a fatia sobre N.

### Cópias idênticas

O mesmo release costuma sair em várias agências (INSS, Previdência, Secom, AGU…) sem marca de republicação. A única deduplicação exata disponível é a do índice de busca (Typesense), que agrupa por `content_hash`: `articles(filter: {entityCanonical, dedup})` conta os textos distintos, e a diferença para a contagem sem `dedup` são as cópias.

Quando há cópia, o perfil ganha **uma linha** logo abaixo do cabeçalho: "16 cópias idênticas entre agências desde 20/05/2026 (índice de busca)." Sem cópia, a linha não aparece.

**Limitações** (ficam aqui, não na saída):

- Só conteúdo **idêntico** conta. Republicações costumam mudar algo no texto (boilerplate, assinatura, links), então a diferença é rara: em 21/10/2026, desde 20/05, Pé-de-Meia teve 189 → 189 textos distintos, INSS 371 → 370 e Brasil 7.506 → 7.496. Releases reescritos não são detectados; isso exigiria detecção de quase-duplicatas no upstream.
- O índice só marca a entidade desde **20/05/2026** (`ENTITY_CANONICAL_INDEX_SINCE`): a contagem começa em `max(date_from, 20/05/2026)` e não roda quando o período termina antes.
- A contagem do índice e a do `entityCoverage` (Postgres) podem diferir: o índice pode atrasar.

### Entidades relacionadas

As 8 mais fortes por co-menção, **em todo o acervo** (os pesos não respeitam o período), sem as [entidades genéricas](get-entity-network.md#entidades-genericas) (Brasil, Brasília, Governo Federal, Portal Gov.br e Diário Oficial da União), que aparecem numa linha "Ocultas como genéricas" (para vê-las na lista, use [get_entity_network](get-entity-network.md) com `include_generic=true`). Ministérios e secretarias, inclusive as entidades das próprias agências (`dgb_{código}`), continuam na lista.

## Retorno

**Exemplo (Pé-de-Meia, 01/01–20/10/2026, em 21/10/2026, abreviado):**

```
# Pé-de-Meia (POLICY)
**ID:** `dgb_pe-de-meia` · —
**Aliases:** Pé-de-Meia, pe-de-meia, Programa Pé-de-Meia, Pé de Meia

**Período:** 01/01/2026 a 20/10/2026
**327 artigos de 18 agências + 51 republicações · 1.214 menções**

## Cobertura mensal
| Mês | Artigos | Republicações |
|-----|---------|---------------|
| 2026-01 | 4 | 0 |
| 2026-02 | 8 | 1 |
…
| 2026-10 (parcial) | 1 | 6 |

## Agências que mais publicaram
1. Ministério da Educação (`mec`) — 183 artigos (56%)
2. Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira (`inep`) — 78 artigos (24%)
…

## Entidades relacionadas (co-menção, todo o acervo)
- **Ministério da Educação (MEC)** (ORG) · 650 artigos em co-menção · `Q4294522`
- **Exame Nacional do Ensino Médio (Enem)** (EVENT) · 306 artigos em co-menção · `Q5419278`
…

Ocultas como genéricas: República Federativa do Brasil (341), Portal Gov.br (139), Brasília (77), …
```

O Pé-de-Meia não tem cópia idêntica desde 20/05, então a linha de cópias não aparece. No mesmo recorte, o Brasil (`Q155`) mostra, logo abaixo do cabeçalho:

```
10 cópias idênticas entre agências de 20/05/2026 a 20/10/2026 (índice de busca).
```

## Exemplos

**Briefing de presença na mídia:**
> "Faça um perfil do Ministério da Saúde no último ano"

**Recorte temporal:**
> "Como foi a cobertura do Pé-de-Meia entre janeiro e outubro de 2026?"

**Mapa de associações:**
> "Com quais pessoas e órgãos o MEC mais aparece junto?"

## Notas

- Em produção, o perfil completo leva ~0,5 s (a busca pelo nome, quando há, mais uma rodada paralela).
- O `articleCount` do `entitySearch` (todo o acervo) não aparece mais: o cabeçalho é sempre a soma do período pedido.
