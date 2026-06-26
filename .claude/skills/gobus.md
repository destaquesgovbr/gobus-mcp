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
| UC-01 | "O que saiu hoje/ontem no MEC?" | `search_news` (agency_key + date_from) | `get_agency_analytics` (em paralelo) |
| UC-02 | "Quero ler este artigo completo" | `get_article` (unique_id) | — |
| UC-03 | "Quem é [entidade] no gov.br?" | `resolve_entity` → `get_entity_profile` | `get_entity_network` (em paralelo com perfil) |
| UC-04 | "Quais temas estão crescendo?" | `detect_trends` | `search_news` por tema (paralelo entre temas) |
| UC-05 | "Com quem [entidade] aparece associada?" | `resolve_entity` → `get_entity_network` | — |
| UC-06 | "Faça um boletim semanal" | prompt `weekly_digest` | — |
| UC-07 | "Escreva um release sobre [tema]" | prompt `draft_press_release` | — |
| UC-08 | "Compare MEC e Saúde no último mês" | `get_agency_analytics` (agencies=[...]) | — |
| UC-09 | "Trace a trajetória de [entidade]" | prompt `trace_entity` | — |
| UC-10 | "Resumo rápido da agência X" | `get_agency_summary` | — |

## Regras de Orquestração

### Regra 1: Sempre `resolve_entity` antes de operações de entidade
`get_entity_profile` e `get_entity_network` precisam do entityId canônico (Wikidata QID).
Nunca use nomes literais diretamente — sempre resolva primeiro.

### Regra 2: UC-01 — perguntas "o que saiu hoje/ontem"
→ Use `search_news` com agency_key + date_from (ontem ou hoje ISO).
→ Execute `get_agency_analytics` em paralelo para métricas de volume.

### Regra 3: UC-04 — perguntas sobre tendências
→ Use `detect_trends` com window_days=7 e baseline_days=28.
→ Para cada tema encontrado, execute `search_news` buscando os termos do tema.
→ Consulte `gobus://taxonomy-queries` para obter termos de busca corretos por categoria.

### Regra 4: Paralelismo
- `search_news` + `get_agency_analytics` para a mesma agência: **paralelo**
- `get_entity_profile` + `get_entity_network` após resolver entityId: **paralelo**
- `search_news` para temas diferentes em UC-04: **paralelo entre temas**

### Regra 5: Controle de contexto para redes grandes
- `get_entity_network` com depth=2: sempre use `max_nodes ≤ 15`
- `get_entity_profile` quando só precisar de resumo: use `summary_only=True`

## Glossário Mínimo

| Termo | Significado |
|-------|-------------|
| `agency_key` | Chave curta de agência (ex: "saude", "mec") — listar em gobus://agencies |
| `entity_id` | ID canônico Wikidata no formato "Q<número>" (ex: "Q4294522") |
| `granularity` | Agrupamento temporal: "DAY", "WEEK" ou "MONTH" |
| `window_days` | Janela RECENTE em detect_trends (quantos dias "agora") |
| `baseline_days` | Período de REFERÊNCIA em detect_trends (quantos dias de histórico) |
| `growthScore` | count(window) / count(baseline) — > 1.5 indica tendência real |

## Resources disponíveis

- `gobus://agencies` — lista completa de agências e suas chaves
- `gobus://themes` — taxonomia de temas do portal
- `gobus://platform-stats` — estatísticas gerais (últimos 30 dias)
- `gobus://taxonomy-queries` — dicionário categoria → termos de busca efetivos
