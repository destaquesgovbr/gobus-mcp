# Handoff — Experimento dos 10 Use Cases do Gobus MCP

## O que você precisa fazer

Executar 10 Use Cases usando as ferramentas MCP do servidor **Gobus** e produzir um relatório Markdown por UC, com resultado substantivo + log de auditoria das chamadas. Os relatórios servem para avaliar a qualidade do MCP, dos dados e dos prompts.

---

## Estado atual (tudo pronto, não precisa configurar nada)

- O servidor Gobus MCP está **conectado** nesta sessão via SSE (Cloud Run)
- As ferramentas aparecem como `mcp__gobus__*` nos deferred tools
- O diretório de saída já existe: `/Users/nitai/dev/destaquesgovbr/gobus-mcp/_experiments/uc-2026-06-24/`

---

## Ferramentas disponíveis

Antes de usar qualquer tool, carregue o schema com ToolSearch:
```
ToolSearch("select:mcp__gobus__gobus_search_news,mcp__gobus__gobus_get_article,mcp__gobus__gobus_resolve_entity,mcp__gobus__gobus_get_entity_profile,mcp__gobus__gobus_get_entity_network,mcp__gobus__gobus_get_agency_analytics,mcp__gobus__gobus_detect_trends")
```

### As 7 tools

| Tool | Parâmetros principais | O que faz |
|------|-----------------------|-----------|
| `gobus_search_news` | `query` (obrigatório), `agency_key=""`, `page=1`, `limit=10` | Busca artigos por texto e/ou agência |
| `gobus_get_article` | `unique_id` (obrigatório) | Artigo completo com conteúdo, entidades, métricas |
| `gobus_resolve_entity` | `query`, `entity_type=""`, `limit=5` | Resolve nome → ID canônico (ORG/PER/LOC/EVENT/POLICY/LAW) |
| `gobus_get_entity_profile` | `entity_name`, `entity_type=""`, `date_from=""`, `date_to=""` | Cobertura temporal + entidades relacionadas |
| `gobus_get_entity_network` | `entity_id`, `depth=1`, `limit=50` | Rede de co-menções (depth 1 ou 2) |
| `gobus_get_agency_analytics` | `agencies` (lista), `date_from`, `date_to`, `granularity="MONTH"` | Métricas por agência/período (volume, sentimento, legibilidade) |
| `gobus_detect_trends` | `window_days=7`, `baseline_days=28`, `growth_threshold=1.5`, `limit=10` | Temas em crescimento |

### Resource de agências (para UC-09)
Carregue via `ToolSearch("select:ReadMcpResourceTool")` e chame:
```
ReadMcpResourceTool(server_name="gobus", uri="gobus://agencies")
```

---

## Janela de dados — IMPORTANTE

- `news_features` (sentimento, legibilidade, trending): disponível desde **2024-06-18**, mas volume denso só a partir de **2026-03**
- `news_entities` (NER, canonical IDs): volume real **somente a partir de 2026-03** (antes: dezenas de registros, não representativo)
- Artigos brutos: 336k, do início dos anos 2000 até hoje

**Impacto nos UCs:** UCs que pediam dados de 2020-2024 foram adaptados — detalhes abaixo.

---

## Os 10 Use Cases

### UC-01 — Briefing Diário (Min. Saúde)
**Pergunta:** "O que o Ministério da Saúde publicou ontem?"
```
1. gobus_search_news(query="saúde", agency_key="saude", limit=10)
2. gobus_get_agency_analytics(agencies=["saude"], date_from="2026-06-17", date_to="2026-06-24", granularity="DAY")
```
Produzir: briefing executivo 200-300 palavras em PT.

---

### UC-02 — Comparativo Fazenda × Planejamento
**Pergunta original:** "Como comunicaram a Reforma Tributária em 2024?"
**Adaptação:** Janela jan–jun 2026 (única com sentiment disponível).
```
1. gobus_search_news(query="reforma tributaria", agency_key="fazenda", limit=10)
2. gobus_search_news(query="reforma tributaria", agency_key="planejamento", limit=10)
3. gobus_get_agency_analytics(agencies=["fazenda","planejamento"], date_from="2026-01-01", date_to="2026-06-24", granularity="MONTH")
```
Produzir: comparativo de enquadramento, volume e sentimento entre as duas agências.

---

### UC-03 — Trajetória "Mais Médicos"
**Pergunta original:** "Cobertura do Mais Médicos desde criação"
**Adaptação:** Dados de entidades disponíveis a partir de 2026-03; relatar limitação.
```
1. gobus_resolve_entity(query="Mais Médicos", entity_type="POLICY")
2. gobus_get_entity_profile(entity_name="Mais Médicos", entity_type="POLICY", date_from="2026-03-01")
3. gobus_search_news(query="Mais Médicos", limit=10)
```
Produzir: timeline de cobertura disponível + nota sobre limitação histórica.

---

### UC-04 — Radar de Tendências
**Pergunta:** "Quais temas estão acelerando esta semana vs. histórico?"
**Nota:** Com threshold 1.5 o resultado foi vazio — começar com 1.2 ou 1.0.
```
1. gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.2, limit=10)
   → Se vazio: gobus_detect_trends(..., growth_threshold=1.0)
2. gobus_search_news(query=<tema_top>, limit=5) para cada tema encontrado
```
Produzir: radar com temas, growth_score e artigos exemplares.

---

### UC-05 — Release sobre Emprego Formal (Min. Trabalho)
**Pergunta:** "Crie rascunho de release sobre emprego formal"
```
1. gobus_search_news(query="emprego formal CAGED", agency_key="trabalho", limit=10)
2. gobus_get_article(unique_id=<id>) — repetir para os 3 artigos mais relevantes
```
Produzir: release completo com título, lead, corpo, autoridade citada. Dados não confirmados → `[VERIFICAR]`.

---

### UC-06 — Rede Institucional (Min. Comunicações)
**Pergunta:** "Quais pessoas, projetos e leis aparecem com o Min. Comunicações?"
```
1. gobus_resolve_entity(query="Ministério das Comunicações", entity_type="ORG")
2. gobus_get_entity_network(entity_id=<id_canonico>, depth=2, limit=50)
3. gobus_search_news(query="Ministério das Comunicações", limit=5)
```
Produzir: narrativa da rede institucional com nós principais e tipo de relacionamento.

---

### UC-07 — Evolução do Sentimento em Saúde
**Pergunta original:** "Como evoluiu sentimento sobre saúde pública 2020-2022?"
**Adaptação:** Janela 2026-03 a 2026-06; explicar que dados de pandemia não existem.
```
1. gobus_get_agency_analytics(agencies=["saude"], date_from="2026-03-01", date_to="2026-06-24", granularity="MONTH")
2. gobus_search_news(query="saúde pública", limit=5) para contextualizar
```
Produzir: gráfico textual da evolução + nota técnica sobre ausência de dados históricos.

---

### UC-08 — Coordenação Cross-Agency
**Pergunta:** "Quais temas foram cobertos por 3+ agências em paralelo no último mês?"
```
1. gobus_detect_trends(window_days=30, baseline_days=90, growth_threshold=1.0, limit=20)
2. Para cada tema top-5: gobus_search_news(query=<tema>, limit=10) e identificar agências
```
Produzir: mapa de oportunidades de coordenação entre agências.

---

### UC-09 — Benchmark de Legibilidade
**Pergunta:** "Quais órgãos publicam conteúdo mais acessível?"
**Janela:** 2026-03-26 a 2026-06-24 (90 dias com features).
```
1. ReadMcpResourceTool(server_name="gobus", uri="gobus://agencies") → lista de codes
2. gobus_get_agency_analytics(agencies=[<lote>], date_from="2026-03-26", date_to="2026-06-24", granularity="MONTH")
   → repetir em lotes de 5 agências
```
Produzir: ranking Flesch por agência, top-5 mais acessíveis e bottom-5.

---

### UC-10 — Boletim Semanal para o Cidadão
**Pergunta:** "O que o governo publicou de mais importante essa semana?"
```
1. gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.0, limit=5)
2. gobus_search_news(query=<tema_top>, limit=5) para cada tema
3. gobus_get_article(unique_id=<top_artigos>) — 2-3 artigos completos
```
Produzir: boletim 400-500 palavras em linguagem acessível (nível Ensino Médio).

---

## Formato de cada arquivo de saída

Salvar em `/Users/nitai/dev/destaquesgovbr/gobus-mcp/_experiments/uc-2026-06-24/UC-NN.md`:

```markdown
# UC-NN — [Nome]
> **Data:** 2026-06-24 | **Status:** ✅ Completo / ⚠️ Parcial / ❌ Falha

## Briefing
[Pergunta original + adaptação se houver]

## Resultado
[Conteúdo substantivo — a resposta real ao use case]

---
## Log de Auditoria

| # | Ferramenta | Parâmetros principais | Resultado resumido |
|---|-----------|----------------------|-------------------|
| 1 | gobus_X | query="...", limit=10 | N artigos |

### Detalhe das chamadas
**Chamada 1 — gobus_X**
Parâmetros: { ... }
Resultado (resumo): ...
Observação: [latência, dados ausentes, surpresas]

## Gaps e Oportunidades de Melhoria
- [O que faltou: dados, tool, prompt]
- [Sugestão concreta]
```

---

## Ao final: produzir INDEX.md

Após todos os UCs, criar `/Users/nitai/dev/destaquesgovbr/gobus-mcp/_experiments/uc-2026-06-24/INDEX.md` com:
- Tabela de status dos 10 UCs
- Achados recorrentes (problemas que apareceram em múltiplos UCs)
- Dimensões de melhoria: dados, tool design, prompt quality, schema

---

## Estratégia de execução

Lance todos os 10 agentes **em paralelo** (um por UC) usando o Agent tool com `run_in_background=true`. Cada agente recebe apenas o briefing do seu UC específico, carrega os schemas das tools via ToolSearch e escreve o arquivo. Após todos concluírem, rode um agente de síntese para o INDEX.md.
