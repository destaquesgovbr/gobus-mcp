# get_entity_network

Mostra a rede de co-menções **centrada numa entidade**: os vizinhos que mais aparecem junto com ela nas notícias, ranqueados pelo peso da conexão. Com `depth=2`, expande os vizinhos mais fortes e aponta as "pontes" (entidades alcançadas por mais de um vizinho). Use para mapear o entorno de um órgão, política ou pessoa. Exige o `entityId` canônico, normalmente obtido via [resolve_entity](resolve-entity.md).

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `entity_id` | `str` | Sim | — | ID canônico: QID (`"Q4294522"`) ou interno (`"dgb_pe-de-meia"`) |
| `depth` | `int` | Não | `1` | `1` = vizinhos diretos; `2` = mais o segundo grau a partir dos 5 vizinhos mais fortes |
| `limit` | `int` | Não | `50` | Vizinhos considerados (máx 200): os de maior peso |
| `max_nodes` | `int` | Não | `20` | Itens da lista ranqueada |
| `node_types` | `str` | Não | `""` | Tipos separados por vírgula (ex.: `"PER,ORG"`); com `LOC`, os lugares entram na lista |
| `include_generic` | `bool` | Não | `false` | Mostra as entidades genéricas, ocultas por padrão |

## Como a rede é montada

- **Fonte:** `relatedEntities(id, limit)`, que traz só as arestas que tocam o foco. O `entityNetwork` não é usado: ele devolve todos os nós alcançáveis sem ordem e corta as arestas entre quaisquer pares, então pares de hubs (Brasil ↔ Brasília, 10.733 artigos) expulsavam as conexões do foco.
- **Peso:** número de artigos em que as duas entidades aparecem juntas, em **todo o acervo** (não respeita janela de datas) e **sem deduplicar republicações** (o mesmo release publicado por várias agências conta várias vezes).
- **Ranking por associação** (GQL-1): cada vizinho vale `w · max(0, log2 lift)`, com `lift` = co-menção observada ÷ esperada pela frequência das duas entidades (`RelatedEntity.lift`), e só com `w ≥ 3` (abaixo, 0). O peso bruto premia quem aparece em tudo; o lift sozinho premia co-menções raras. Os candidatos são a **união** de dois pools: os `limit` de maior peso (`orderBy: WEIGHT, minWeight: 2`) e os `limit` de maior lift com `minWeight: 3` — o pool por lift sozinho perderia os vizinhos fortes (em 21/10/2026, o MEC era só o 65º vizinho do Pé-de-Meia por lift, e o 1º por associação). Cada linha mostra `650 artigos · 14,6× o esperado`, e a linha **Ranking:** do cabeçalho diz qual ranking valeu.
- **Peso bruto de reserva:** sem o lift — API sem o GQL-1 (a consulta volta para a forma antiga por 1 h) ou estatísticas do grafo ainda não calculadas (`lift` nulo em todas as linhas) —, a ordem é o peso bruto e o cabeçalho diz `**Ranking:** peso bruto (artigos em co-menção) — <motivo>`. A lista curada de genéricas vale nos dois casos.
- **Cabeçalho honesto:** "Mostrando X de Y vizinhos diretos", em que Y conta os vizinhos depois dos filtros; vira "Y+" quando o `limit` foi atingido (há mais vizinhos, todos com peso menor), com uma nota dizendo o peso de corte.
- **Lugares:** vizinhos do tipo `LOC` (UFs, capitais) saem da lista e vão para a linha "Lugares", com no máximo 5 e "+k lugares". Se `node_types` pede `LOC`, eles voltam para a lista, sem teto.
- **Genéricas:** ficam fora por padrão e aparecem numa linha "Ocultas como genéricas: …" com os pesos. `include_generic=true` traz todas de volta.

### Entidades genéricas

Lista curada em `analytics/generic_entities.py` (contagens do `entitySearch.articleCount` em 21/10/2026):

| Entidade | ID | Por quê |
|----------|----|---------|
| Brasil | `Q155` | o país do acervo inteiro (63.871 artigos) |
| Brasília | `Q2844` | dateline e sede do governo ("brasilia - df"; 33.284) |
| Governo Federal | `Q5440531` | o próprio emissor (aliases União, Governo do Brasil; 12.952) |
| Portal Gov.br | `dgb_portal-gov-br` | boilerplate de serviço (2.099); **em revisão**, às vezes é o serviço de fato |
| Diário Oficial da União (DOU) | `Q3712237` | boilerplate de ato publicado ("publicado no DOU"; 11.824); lift < 1 com os focos conferidos |

**Critério:** volume alto e **lift ≤ 1** nas entidades conferidas, isto é, a co-menção não passa do esperado ao acaso (`weight / (n_foco × n_genérica / 202.608)`, com o total de artigos do grafo). Ocultar não apaga a informação: a linha "Ocultas como genéricas" mostra cada uma com o peso, e `include_generic=true` traz todas de volta.

**Avaliação do DOU (21/10/2026, produção, só leitura):** o DOU estava fora da lista do PR-B e aparecia como vizinho e como "ponte" de quase tudo. Com `relatedEntities(limit: 60)` e as genéricas de então já ocultas:

| Foco (artigos) | Posição do DOU | Peso | Esperado ao acaso | Lift | Quem entra no top-20 |
|---|---|---|---|---|---|
| Pé-de-Meia (837) | fora dos 60 | — | 48,8 | — | nada muda |
| Bolsa Família (2.674) | 44º | 76 | 156,1 | 0,49 | nada muda |
| INSS (3.733) | 10º | 195 | 217,9 | 0,90 | Secretaria-Geral da Presidência (131) |
| MEC (10.794) | 15º | 577 | 629,9 | 0,92 | São Paulo (421) |

Em nenhum foco o DOU co-ocorre acima do acaso: ele marca o tipo de notícia (ato normativo publicado), não um assunto. Ocultá-lo libera uma vaga no top-20 do INSS e do MEC e tira o DOU das pontes do `depth=2`, onde ele ligava MEC, Enem, Inep e Camilo Santana só por ser onipresente; a contagem continua na linha das ocultas.

Continuam visíveis: as UFs (inclusive o Distrito Federal, `Q119158`), as demais capitais, as pessoas e os ministérios, tanto pelo QID (ex.: MEC, `Q4294522`) quanto pela entidade da própria agência (`dgb_{código}`: Secretaria-Geral, Fazenda, Casa Civil, Saúde…), que são vizinhos com sentido. A exclusão das `dgb_{código}` só vale na [coerência de mensagem](get-message-coherence.md). O foco nunca aparece na própria lista.

### Segundo grau (`depth=2`)

1. Pega os 5 primeiros da lista ranqueada (ou menos, se `max_nodes` for menor).
2. Busca em paralelo os 25 vizinhos de maior peso de cada um (só o pool por peso, reordenado pela associação; medido ao vivo: com 15, sobravam 1–3 entidades novas por vizinho; com 25, a rodada continua em ≤ 0,8 s). Com lift, cada item mostra `(peso · lift×, id)`.
3. Mostra, por vizinho, até 5 entidades **novas**: sem o foco, sem as genéricas e sem os vizinhos diretos já considerados; `node_types` também vale aqui.
4. Lista as **pontes**: entidades novas alcançadas por 2 ou mais vizinhos (as de mais vizinhos primeiro).

Um vizinho cuja consulta falha vira nota ("Não foi possível expandir …") e os demais seguem. O nó e cada consulta de vizinhos ficam 30 minutos no cache do servidor. A rede não consulta o catálogo de agências.

## Retorno

**Exemplo (Pé-de-Meia, `depth=2`, 21/10/2026, antes do GQL-1, abreviado):**

```
# Rede de entidades: Pé-de-Meia (POLICY)

`dgb_pe-de-meia` · Mostrando 25 de 46+ vizinhos diretos (pesos = artigos em co-menção em todo o acervo, inclui republicações)
**Ranking:** peso bruto (artigos em co-menção) — a API ainda não expõe o lift

## Vizinhos diretos
1. **Ministério da Educação (MEC)** (ORG) · 650 artigos em co-menção · `Q4294522`
2. **Exame Nacional do Ensino Médio (Enem)** (EVENT) · 306 artigos em co-menção · `Q5419278`
3. **Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira (Inep)** (ORG) · 295 artigos em co-menção · `Q6041403`
…
18. **Secretaria-Geral da Presidência da República** (ORG) · 41 artigos em co-menção · `dgb_secretariageral`
…
… +15 vizinhos (aumente `max_nodes`)

**Lugares:** Distrito Federal (70, `Q119158`), São Paulo (37, `dgb_sao-paulo`), Ceará (30, `dgb_ceara`), … +6 lugares

Ocultas como genéricas: República Federativa do Brasil (341), Portal Gov.br (139), Brasília (77), Governo Federal do Brasil (69) — use include_generic=true para incluí-las (país, dateline, o próprio emissor e boilerplate).

> O limite de 50 vizinhos foi atingido: há mais vizinhos, todos com peso ≤ 18. Aumente `limit` (máx 200).

## Segundo grau (via os 5 primeiros vizinhos)
- via **Ministério da Educação (MEC)** (650): Fundo Nacional de Desenvolvimento da Educação (FNDE) (1.300, `Q10286468`), Coordenação de Aperfeiçoamento de Pessoal de Nível Superior (CAPES) (1.030, `Q5167991`), …, Ministério da Saúde (617, `dgb_saude`), …
- via **Camilo Sobreira de Santana** (170): Fundo Nacional de Desenvolvimento da Educação (FNDE) (213, `Q10286468`), Fortaleza (106, `dgb_fortaleza`), …

**Pontes** (alcançadas por 2+ vizinhos): Fundo Nacional de Desenvolvimento da Educação (FNDE) (via …), …

**Para explorar:**
- `gobus_get_entity_profile(entity_name="dgb_pe-de-meia")` — série e órgãos do foco
- `gobus_get_entity_network(entity_id="Q4294522")` — a rede de Ministério da Educação (MEC)
- `gobus_search_news(query="Pé-de-Meia Ministério da Educação")` — artigos que citam os dois
```

Com o lift (GQL-1), as linhas viram `` 1. **Ministério da Educação (MEC)** (ORG) · 650 artigos · 14,6× o esperado · `Q4294522` `` e o cabeçalho, `**Ranking:** associação (artigos em co-menção × log2 do lift, com ≥ 3 artigos; …)`. Em `depth=1`, o rodapé termina com `gobus_get_entity_network(entity_id="…", depth=2)`.

Em produção (21/10/2026), `depth=2` leva ≤ 0,8 s e ~5–6,5 KB (uma rodada para o foco e uma rodada paralela para os 5 vizinhos).

## Exemplos

**Mapeamento de entorno:**
> "Com quem o Pé-de-Meia aparece associado nas notícias?"

**Só pessoas e órgãos:**
> "Quais pessoas e órgãos aparecem com o MEC? (node_types PER,ORG)"

**Segundo grau:**
> "Expanda a rede do Pé-de-Meia com profundidade 2 e mostre as pontes."

## Notas

- Os pesos são de todo o acervo; para um recorte de datas, use [get_entity_profile](get-entity-profile.md) (série mensal) ou [search_news](search-news.md).
- `depth` é limitado a 2 e `limit` a 200, mesmo que valores maiores sejam informados.
- Esta tool exige o ID canônico; se você só tem o nome, resolva primeiro com [resolve_entity](resolve-entity.md). O [get_entity_profile](get-entity-profile.md) aceita nome ou ID e já traz as relacionadas.
