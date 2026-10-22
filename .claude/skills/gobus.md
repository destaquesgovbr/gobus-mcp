---
name: gobus
description: >
  Orquestra as tools do gobus-mcp para responder perguntas sobre atividade do governo federal
  brasileiro. Use quando o usuário perguntar sobre notícias, agências, entidades ou tendências
  do portal Gov.BR.
---

# Gobus MCP — Guia de Orquestração

## Mapa de Use Cases → Tools

| UC | Pergunta típica | Tool principal | Tools auxiliares |
|----|----------------|----------------|-----------------|
| UC-01 | "O que saiu hoje/ontem no MEC?" | `gobus_search_news` (query="*", agency_key, date_from + date_to) | `gobus_get_agency_analytics` (em paralelo) |
| UC-02 | "Quero ler este artigo completo" | `gobus_get_article` (unique_id) | — |
| UC-03 | "Quem é [entidade] no gov.br?" | `gobus_resolve_entity` → `gobus_get_entity_profile` | `gobus_get_entity_network` (em paralelo com perfil) |
| UC-04 | "Quais temas estão crescendo?" | `gobus_detect_trends` | `gobus_search_news` por tema (paralelo entre temas) |
| UC-05 | "Com quem [entidade] aparece associada?" | `gobus_resolve_entity` → `gobus_get_entity_network` | — |
| UC-06 | "Faça um boletim semanal" | prompt `prompt_weekly_digest` | — |
| UC-07 | "Escreva um release sobre [tema]" | prompt `prompt_draft_press_release` | — |
| UC-08 | "Compare MEC e Saúde no último mês" | `gobus_get_agency_analytics` (agencies=[...]) | — |
| UC-09 | "Trace a trajetória de [entidade]" | prompt `prompt_trace_entity` | — |
| UC-10 | "Resumo rápido da agência X" | `gobus_get_agency_summary` | — |
| UC-11 | "Os textos da agência X são fáceis de ler?" | `gobus_get_readability_recommendations` | `gobus_score_article` (um artigo) |
| UC-12 | "Em que fase está a política X?" | `gobus_get_policy_lifecycle` | `gobus_resolve_entity` (entity_type="POLICY") |
| UC-13 | "As agências falam em sintonia sobre X?" | `gobus_get_message_coherence` (entity_id ou theme) | `gobus_resolve_entity` (entityId), `gobus_search_news` (artigos de um par divergente) |

## Regras de Orquestração

### Regra 1: Sempre `gobus_resolve_entity` antes de operações de entidade
`gobus_get_entity_network` precisa do entityId canônico (QID `Q…` ou interno `dgb_…`).
`gobus_get_entity_profile` aceita o ID (vai direto, sem busca fuzzy) ou o nome (1º resultado
da busca) — prefira o ID resolvido, que evita homônimos.

### Regra 2: UC-01 — perguntas "o que saiu hoje/ontem"
→ Use `gobus_search_news(query="*", agency_key=..., date_from=D, date_to=D)` com o dia em
  AAAA-MM-DD: as datas são dias inteiros em horário de Brasília, ambas inclusivas.
→ Execute `gobus_get_agency_analytics(..., granularity="DAY")` com as mesmas datas, em paralelo
  (dias UTC: a contagem pode diferir em poucos artigos).
→ Ou use o prompt `prompt_monitor_agency`, que já escreve as chamadas com as datas.

### Regra 3: UC-04 — perguntas sobre tendências
→ Use `gobus_detect_trends` com window_days=7 e baseline_days=28.
→ Para cada tema encontrado, execute `gobus_search_news` buscando os termos do tema.
→ Consulte `gobus://taxonomy-queries` para obter termos de busca corretos por categoria.

### Regra 4: Paralelismo
- `gobus_search_news` + `gobus_get_agency_analytics` para a mesma agência: **paralelo**
- `gobus_get_entity_profile` + `gobus_get_entity_network` após resolver entityId: **paralelo**
- `gobus_search_news` para temas diferentes em UC-04: **paralelo entre temas**

### Regra 5: Rede e perfil de entidades
- `gobus_get_entity_network` é centrada no foco: vizinhos por associação (artigos em co-menção
  em todo o acervo × log2 do lift, "650 artigos · 14,6× o esperado"; peso bruto quando a API
  não traz o lift — a linha **Ranking:** diz qual valeu). depth=2 expande os 5 primeiros
  (~5–6,5 KB); `limit` = vizinhos considerados (máx 200), `max_nodes` = itens da lista
- Genéricas (Brasil, Brasília, Governo Federal, Portal Gov.br) ficam ocultas e listadas à
  parte; use `include_generic=true` só se a pergunta for sobre elas. Ministérios e secretarias
  (inclusive `dgb_{agência}`) sempre aparecem
- `gobus_get_entity_profile`: o cabeçalho soma o período inteiro (próprias + republicações);
  quando só precisar de resumo, use `summary_only=True`

### Regra 6: Citações
- Cite cada artigo como link Markdown `[título](url)` no ponto em que o fato aparece, só com
  URLs devolvidas pelas tools (`gobus_search_news`, `gobus_get_article` e os artigos dos temas
  em alta já trazem o título como link). Sem URL, cite o `unique_id` e ofereça `gobus_get_article`.

### Regra 7: Para explorar e legibilidade
- As tools de texto terminam com "**Para explorar:**" (até 3 chamadas prontas, tiradas do
  resultado): use-as para as perguntas de continuação
- Legibilidade = Flesch pt-BR (Martins): 0–25 muito difícil · 25–50 difícil · 50–75 fácil ·
  75–100 muito fácil; meta de serviço 50; notícia de governo fica perto de 25 (mediana do
  acervo 25,2, na divisa entre difícil e muito difícil), e o exibido é limitado a 0–100. Com
  o aviso "Flesch pt-BR indisponível", os valores são da fórmula inglesa (legado)

## Glossário Mínimo

| Termo | Significado |
|-------|-------------|
| `agency_key` | Código da agência (ex: "saude", "mec") — listar em gobus://agencies; código inválido devolve sugestão ("ms" → "saude") |
| `entity_id` | ID canônico: QID Wikidata "Q<número>" (ex: "Q4294522") ou interno "dgb_…" (ex: "dgb_pe-de-meia") |
| `granularity` | Agrupamento temporal: "DAY", "WEEK" ou "MONTH" |
| `window_days` | Janela RECENTE em detect_trends (quantos dias "agora") |
| `baseline_days` | Período de REFERÊNCIA em detect_trends (quantos dias de histórico) |
| `growth_threshold` | Razão mínima sem sobreposição (artigos/dia na janela ÷ nos dias anteriores do baseline); 1.5 = 50% a mais |
| `growthScore` | Cálculo da API, com o baseline **incluindo** a janela — a tool também mostra a razão sem sobreposição |
| "indisponível" | Fonte de dados sem valor (nunca 0) — confira `gobus://health/pipelines` |

## Resources disponíveis

- `gobus://agencies` — lista completa de agências e suas chaves
- `gobus://themes` — taxonomia de temas do portal
- `gobus://platform-stats` — estatísticas gerais (últimos 30 dias)
- `gobus://taxonomy-queries` — dicionário categoria → termos de busca efetivos
- `gobus://readability-report` — legibilidade por agência (JSON, janela efetiva)
- `gobus://health/pipelines` — saúde das fontes de dados (JSON): consulte antes de interpretar ausências
- `ui://readability-dashboard` — dashboard HTML de legibilidade
