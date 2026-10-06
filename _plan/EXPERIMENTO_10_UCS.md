# Plano: Gobus MCP — Experimento dos 10 Use Cases

## Status de infraestrutura (2026-06-24) ✅ TUDO PRONTO

| Item | Status | Detalhe |
|------|--------|---------|
| Cloud Run imagem real | ✅ | Revisão `00020-xxx`, FastMCP 2.9.x, SSE transport |
| Terraform lifecycle fix | ✅ | infra PR #209 mergeado — image nunca mais reseta |
| max_instance_count=1 | ✅ | infra PR #210 mergeado — evita race condition SSE |
| `~/.claude.json` | ✅ | `type: sse, url: .../sse` |
| MCP conectado | ✅ | `detect_trends` retornou JSON válido nesta sessão |
| Diretório de saída | ✅ | `gobus-mcp/_experiments/uc-2026-06-24/` criado |

---

## Janela de dados (confirmado via SQL direto ao Cloud SQL)

| Tabela | Cobertura real | Observação |
|--------|---------------|-----------|
| `news` | ~2000s–2026-06-24 | 336k artigos |
| `news_features` | 2024-06-18+ | 28.5k artigos (30.6% do total) |
| `news_entities` | **2026-03+ (volume real)** | Antes: dezenas de registros; volume denso só a partir de mar/26 |

---

## 10 Use Cases — parâmetros ajustados

### UC-01 — Briefing Diário da Agência (Min. Saúde)
**Pergunta:** "O que o Ministério da Saúde publicou ontem?"
**Tools:**
1. `gobus_search_news(query="saúde", agency_key="saude", limit=10)`
2. `gobus_get_agency_analytics(agencies=["saude"], date_from="2026-06-17", date_to="2026-06-24", granularity="DAY")`
**Output:** Briefing executivo 200-300 palavras em PT

### UC-02 — Comparativo Fazenda × Planejamento (Reforma Tributária)
**Pergunta original:** "Como comunicaram a Reforma Tributária em 2024?"
**Adaptação:** Janela jan–jun 2026 (features/sentiment disponíveis)
**Tools:**
1. `gobus_search_news(query="reforma tributaria", agency_key="fazenda", limit=10)`
2. `gobus_search_news(query="reforma tributaria", agency_key="planejamento", limit=10)`
3. `gobus_get_agency_analytics(agencies=["fazenda","planejamento"], date_from="2026-01-01", date_to="2026-06-24", granularity="MONTH")`
**Output:** Comparativo de enquadramento, volume e sentimento

### UC-03 — Trajetória "Mais Médicos"
**Pergunta original:** "Cobertura desde criação"
**Adaptação:** Cobertura disponível a partir de 2026-03; relatar limitação histórica
**Tools:**
1. `gobus_resolve_entity(query="Mais Médicos", entity_type="POLICY")`
2. `gobus_get_entity_profile(entity_name="Mais Médicos", entity_type="POLICY", date_from="2026-03-01")`
3. `gobus_search_news(query="Mais Médicos", limit=10)`
**Output:** Timeline de cobertura + nota sobre limitação histórica

### UC-04 — Radar de Tendências Emergentes
**Pergunta:** "Quais temas estão acelerando esta semana?"
**Nota:** `detect_trends` com threshold 1.5 retornou vazio — usar 1.0 ou 1.2
**Tools:**
1. `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.2, limit=10)`
2. Se vazio: `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.0, limit=10)`
3. `gobus_search_news(query=<tema_top>)` para cada tema
**Output:** Radar de temas com score de crescimento e artigos exemplares

### UC-05 — Rascunho de Release (Emprego Formal / Min. Trabalho)
**Pergunta:** "Crie rascunho sobre emprego formal usando artigos do Min. Trabalho"
**Tools:**
1. `gobus_search_news(query="emprego formal CAGED", agency_key="trabalho", limit=10)`
2. `gobus_get_article(unique_id=<top_3_ids>)` — 3 chamadas
**Output:** Release completo: título, lead, corpo, autoridade citada, tags [VERIFICAR]

### UC-06 — Mapeamento de Rede Institucional (Min. Comunicações)
**Pergunta:** "Quais entidades aparecem com o Min. Comunicações?"
**Tools:**
1. `gobus_resolve_entity(query="Ministério das Comunicações", entity_type="ORG")`
2. `gobus_get_entity_network(entity_id=<id>, depth=2, limit=50)`
3. `gobus_search_news(query="Ministério das Comunicações", limit=5)`
**Output:** Mapa da rede institucional com nós, arestas e peso

### UC-07 — Análise de Sentimento Saúde Pública
**Pergunta original:** "Como evoluiu sentimento 2020-2022 (pandemia)?"
**Adaptação:** Janela 2026-03 a 2026-06; documentar impossibilidade do período pandemia
**Tools:**
1. `gobus_get_agency_analytics(agencies=["saude"], date_from="2026-03-01", date_to="2026-06-24", granularity="MONTH")`
2. `gobus_search_news(query="saúde pública", limit=5)` para contexto
**Output:** Evolução mensal do sentimento + nota sobre limitação histórica

### UC-08 — Oportunidades de Coordenação Cross-Agency
**Pergunta:** "Quais temas foram cobertos por 3+ agências em paralelo sem coordenação?"
**Tools:**
1. `gobus_detect_trends(window_days=30, baseline_days=90, growth_threshold=1.0, limit=20)`
2. Para top 5 temas: `gobus_search_news(query=<tema>)` e verificar quais agências cobriram
**Output:** Mapa de oportunidades de coordenação

### UC-09 — Benchmark de Legibilidade por Agência
**Pergunta:** "Quais órgãos publicam conteúdo mais acessível?"
**Janela:** 2026-03-26 a 2026-06-24 (90 dias com features disponíveis)
**Tools:**
1. Ler resource `gobus://agencies` para obter lista de agency_keys
2. `gobus_get_agency_analytics(agencies=[<lote de 5>], date_from="2026-03-26", date_to="2026-06-24", granularity="MONTH")` — repetir em lotes
**Output:** Ranking de legibilidade (Flesch) por agência com top e bottom 5

### UC-10 — Boletim Semanal para o Cidadão
**Pergunta:** "O que o governo publicou de mais importante essa semana?"
**Tools:**
1. `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.0, limit=5)`
2. `gobus_search_news(query=<tema_top>)` para cada tema, pegar artigos mais vistos
3. `gobus_get_article(unique_id=<top>)` para 2-3 artigos com mais detalhes
**Output:** Boletim 400-500 palavras em linguagem acessível (nível EM)

---

## Formato de cada relatório (UC-NN.md)

```markdown
# UC-NN — [Nome do Use Case]
> **Data:** 2026-06-24 | **Status:** ✅ Completo / ⚠️ Parcial / ❌ Falha

## Briefing
[Pergunta original + adaptação aplicada se houver]

## Resultado
[Conteúdo substantivo — a resposta real ao use case]

---
## Log de Auditoria

| # | Ferramenta | Parâmetros principais | Resultado resumido |
|---|-----------|----------------------|-------------------|
| 1 | gobus_search_news | query="...", limit=10 | N artigos |

### Detalhe das chamadas
**Chamada 1 — gobus_search_news**
Parâmetros: { ... }
Resultado: [trecho relevante]
Observação: [latência, qualidade, dados ausentes]

## Gaps e Oportunidades de Melhoria
- [O que faltou: dados, tool, prompt]
- [Sugestão de melhoria]
```

---

## Diretório de saída

```
/Users/nitai/dev/destaquesgovbr/gobus-mcp/_experiments/uc-2026-06-24/
  UC-01.md  UC-02.md  ...  UC-10.md
  INDEX.md
```

---

## Como executar (nova sessão)

Ver `HANDOFF.md` neste mesmo diretório.
