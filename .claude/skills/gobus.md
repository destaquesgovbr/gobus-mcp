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
| UC-01 | "O que saiu hoje/ontem no MEC?" | `gobus_search_news` (agency_key + date_from) | `gobus_get_agency_analytics` (em paralelo) |
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

## Regras de Orquestração

### Regra 1: Sempre `gobus_resolve_entity` antes de operações de entidade
`gobus_get_entity_profile` e `gobus_get_entity_network` precisam do entityId canônico (Wikidata QID).
Nunca use nomes literais diretamente — sempre resolva primeiro.

### Regra 2: UC-01 — perguntas "o que saiu hoje/ontem"
→ Use `gobus_search_news` com agency_key + date_from (ontem ou hoje ISO).
→ Execute `gobus_get_agency_analytics` em paralelo para métricas de volume.

### Regra 3: UC-04 — perguntas sobre tendências
→ Use `gobus_detect_trends` com window_days=7 e baseline_days=28.
→ Para cada tema encontrado, execute `gobus_search_news` buscando os termos do tema.
→ Consulte `gobus://taxonomy-queries` para obter termos de busca corretos por categoria.

### Regra 4: Paralelismo
- `gobus_search_news` + `gobus_get_agency_analytics` para a mesma agência: **paralelo**
- `gobus_get_entity_profile` + `gobus_get_entity_network` após resolver entityId: **paralelo**
- `gobus_search_news` para temas diferentes em UC-04: **paralelo entre temas**

### Regra 5: Controle de contexto para redes grandes
- `gobus_get_entity_network` com depth=2: sempre use `max_nodes ≤ 15`
- `gobus_get_entity_profile` quando só precisar de resumo: use `summary_only=True`

## Glossário Mínimo

| Termo | Significado |
|-------|-------------|
| `agency_key` | Código da agência (ex: "saude", "mec") — listar em gobus://agencies; código inválido devolve sugestão ("ms" → "saude") |
| `entity_id` | ID canônico Wikidata no formato "Q<número>" (ex: "Q4294522") |
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
