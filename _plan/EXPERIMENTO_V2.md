# EXPERIMENTO_V2 — Gobus MCP: Semântica Profunda

## Contexto

O `EXPERIMENTO_10_UCS.md` validou que a plataforma funciona e catalogou 13 falhas. O `PLANO_V2` corrigiu tudo: filtros de data, agency_key, Flesch numérico, rede com caps, `get_agency_summary`, `taxonomy-queries`, skill `.claude/skills/gobus.md`, `summary_only`, hints de paralelismo. A `graphql-api` ganhou `generate_series` para DAY (lacunas preenchidas com 0).

**O que muda no V2:** os prompts de cada UC são desenhados como *skills executáveis* — instruções que um agente pode seguir diretamente para extrair valor semântico que não seria obtido por chamadas avulsas. O foco não é testar os tools, mas descobrir coisas reais sobre a comunicação governamental.

---

## Limitações de dados (invariantes)

| Fonte | Janela segura |
|-------|--------------|
| `news` | 336k artigos (~2000–hoje) |
| `news_features` (Flesch, sentiment, viewCount) | 2024-06-18+ |
| `news_entities` (NER + entity network) | 2026-03-01+ |
| Sentimento | **Bug persistente** — sempre 0% positivo (não corrigido, documentar nos relatórios) |
| Artigos MOCK | Ainda em produção (issue #3) — ignorar resultados com `[MOCK]` no título |

---

## Os 10 Use Cases — Prompts como Skills

### UC-01 — "O Cartógrafo" — Hubs de Poder Institucional

**Pergunta:** Quais entidades funcionam como pontes entre diferentes áreas do governo?

**Prompt para agente:**
```
Você é um analista de redes institucionais. Sua missão: identificar os hubs de poder na comunicação do governo federal por co-menção em artigos oficiais.

1. `gobus_detect_trends(window_days=30, baseline_days=90, growth_threshold=1.0, limit=15)` — temas mais ativos.

2. Para cada um dos 3 temas de maior growthScore, em paralelo:
   `gobus_resolve_entity(query=<tema>, entity_type="ORG", limit=3)`

3. Para cada entidade ORG única (máx 6), em paralelo:
   `gobus_get_entity_network(entity_id=<id>, depth=1, max_nodes=15, node_types="ORG")`

4. Agregue: conte quantas vezes cada nó aparece como vizinho em redes diferentes. Nós com maior frequência cruzada = super-hubs.

5. Para os 3 super-hubs: `gobus_get_entity_profile(entity_name=<nome>, summary_only=True)`

Output: Análise de 400 palavras em formato de mapa narrativo — (a) hub central, (b) conectores de 2º nível, (c) setores mais interligados, (d) tabela com score de centralidade aproximado.
```

---

### UC-02 — "O Arqueólogo" — Cronologia Diária de um Evento

**Pergunta:** Como evoluiu a narrativa governamental dia a dia em torno do tema mais quente da semana?

**Prompt para agente:**
```
Você é um arqueólogo da comunicação. Use granularidade DAY para reconstituir a evolução cronológica de um evento.

1. `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.2, limit=5)` — pegue o tema de maior growthScore.

2. Em paralelo:
   - `gobus_search_news(query=<tema_top>, date_from="2026-06-01", date_to="2026-06-29", limit=20)`
   - `gobus_get_agency_analytics(agencies=["saude","mec","fazenda","trabalho","mma"], date_from="2026-06-01", date_to="2026-06-29", granularity="DAY")`

3. Para os 3 artigos mais recentes, em paralelo: `gobus_get_article(unique_id=<id>)`

4. Cruze: em quais dias o volume subiu? Quais agências lideraram em cada fase? Qual foi o arco narrativo?

Output: Cronologia jornalística de 350 palavras com marcos D+1, D+2..., volume por dia, e síntese do arco narrativo (anúncio → desdobramentos → reação).
```

---

### UC-03 — "O Detetive" — Mapa de Silêncios Estratégicos

**Pergunta:** Onde a comunicação governamental está ausente quando deveria estar presente?

**Prompt para agente:**
```
Você é um detetive de gaps comunicacionais. Encontre temas em alta onde agências "donas" do assunto estão ausentes.

1. `gobus_detect_trends(window_days=14, baseline_days=56, growth_threshold=1.0, limit=20)` — top 20 temas.

2. Leia `gobus://taxonomy-queries` — mapeie categorias às agências esperadas (saúde → saude, educação → mec, etc.).

3. Para os 5 temas com maior growthScore, em paralelo:
   `gobus_search_news(query=<tema>, date_from="2026-06-01", limit=10)` — extraia quais agências aparecem.

4. Para cada tema: identifique a agência "dona" esperada. Está publicando? Se não, é o gap.

5. Para os 2 maiores gaps: `gobus_get_agency_analytics(agencies=[<agência_ausente>], date_from="2026-06-01", date_to="2026-06-29", granularity="WEEK")`

Output: Relatório de inteligência comunicacional de 400 palavras com 5 oportunidades de comunicação perdidas — (a) tema trending, (b) agência ausente, (c) quem está falando em lugar dela, (d) recomendação de ação.
```

---

### UC-04 — "O Taxonomista" — Almanaque Semanal por Categoria

**Pergunta:** O que foi mais importante esta semana em cada setor do governo?

**Prompt para agente:**
```
Você é o editor-chefe de um almanaque governamental de 15 setores.

1. Leia `gobus://taxonomy-queries` — obtenha as 15 categorias e seus termos principais.

2. Em PARALELO (todos de uma vez): `gobus_search_news(query=<termo_principal_da_categoria>, date_from="2026-06-22", date_to="2026-06-29", limit=3)` para cada uma das 15 categorias.

3. Selecione o artigo com maior trendingScore (ou mais recente) por categoria.

4. Para os 5 artigos de maior trendingScore no total: `gobus_get_article(unique_id=<id>)`

Output: Almanaque semanal com 15 seções (uma por categoria), cada uma com título, agência, data e trecho de 50 palavras. Encerre com resumo editorial de 150 palavras sobre os temas dominantes da semana. Formato de boletim executivo.
```

---

### UC-05 — "O Etnógrafo" — Perfil Narrativo Profundo de Ator Institucional

**Pergunta:** Como o governo fala sobre o Ministério da Fazenda — com que entidades, em que contextos?

**Prompt para agente:**
```
Você é um etnógrafo da linguagem governamental. Construa um perfil narrativo multidimensional.

1. `gobus_resolve_entity(query="Ministério da Fazenda", entity_type="ORG")`

2. Em paralelo após obter entityId:
   - `gobus_get_entity_profile(entity_name="Ministério da Fazenda", date_from="2026-03-01")`
   - `gobus_get_entity_network(entity_id=<id>, depth=1, max_nodes=20, node_types="ORG,PER")`
   - `gobus_search_news(query="Ministério da Fazenda reforma tributária fiscal", date_from="2026-06-01", limit=10)`

3. Para os 2 artigos mais recentes: `gobus_get_article(unique_id=<id>)`

4. Para as 3 entidades mais conectadas na rede: `gobus_get_entity_profile(entity_name=<nome>, summary_only=True)`

Output: Ficha de inteligência institucional de 500 palavras em 5 dimensões — (1) Identidade, (2) Rede de co-menções, (3) Presença temporal, (4) Discurso dominante, (5) Influência cruzada (em que outros perfis aparece).
```

---

### UC-06 — "O Compositor" — Convergências Temáticas Inesperadas

**Pergunta:** Quais pares de temas aparentemente não relacionados são cobertos pelas mesmas agências?

**Prompt para agente:**
```
Você é um analista de convergência temática. Encontre conexões não-óbvias na cobertura governamental.

1. `gobus_detect_trends(window_days=14, baseline_days=56, growth_threshold=1.0, limit=15)` — top 15 temas.

2. Para os top 10 temas, em paralelo:
   `gobus_search_news(query=<tema>, date_from="2026-06-01", limit=5)` — extraia as agências por tema.

3. Construa matriz mental: agência → temas cobertos. Identifique agências que cobrem 3+ temas distintos.

4. Para a agência mais "multi-temática": `gobus_get_agency_summary(agency_key=<key>, days=30)`

5. Para os 2 pares de temas mais inesperadamente conectados: identifique entidade comum via `gobus_resolve_entity(<conceito_ponte>)` + `gobus_get_entity_network`.

Output: Análise de convergência de 400 palavras — (1) Matriz de cobertura multi-temática, (2) Os 3 pares de temas mais surpreendentes, (3) Hipótese explicativa para cada convergência. Formato de análise estratégica.
```

---

### UC-07 — "O Cronista" — Narrativa de Impacto de Política Pública

**Pergunta:** Qual política pública teve maior presença comunicacional nos últimos 90 dias?

**Prompt para agente:**
```
Você é o cronista das políticas públicas federais. Identifique a política-estrela e reconstitua sua narrativa.

1. Em paralelo:
   - `gobus_detect_trends(window_days=90, baseline_days=180, growth_threshold=0.8, limit=10)`
   - `gobus_search_news(query="Bolsa Família INSS previdência benefício social", date_from="2026-03-26", limit=10)`
   - `gobus_search_news(query="CAGED emprego formal carteira trabalho salário", date_from="2026-03-26", limit=10)`

2. Identifique a política mais mencionada (cruze resultados).

3. `gobus_resolve_entity(query=<política_identificada>, entity_type="POLICY")`

4. Em paralelo:
   - `gobus_get_entity_profile(entity_name=<política>, date_from="2026-03-01")`
   - `gobus_get_agency_analytics(agencies=["mps","trabalho","fazenda","planejamento"], date_from="2026-03-01", date_to="2026-06-29", granularity="MONTH")`

Output: Crônica jornalística de 500 palavras — origem da pauta, quem liderou a narrativa, marcos comunicacionais, agências aliadas vs. ausentes, perspectiva futura por dados de tendência.
```

---

### UC-08 — "O Estrategista" — Benchmarking Estratégico de Agência

**Pergunta:** Como o Ministério do Meio Ambiente se posiciona em comparação ao ecossistema governamental?

**Prompt para agente:**
```
Você é um consultor de comunicação estratégica. Benchmarking completo da agência-alvo vs. governo.

Agência-alvo: Ministério do Meio Ambiente (agency_key="mma")

1. Em paralelo:
   - `gobus_get_agency_summary(agency_key="mma", days=90)`
   - `gobus_detect_trends(window_days=30, baseline_days=90, growth_threshold=1.0, limit=10, agency_key="mma")`
   - `gobus_get_agency_analytics(agencies=["mec","saude","fazenda","trabalho","planejamento","mma"], date_from="2026-03-26", date_to="2026-06-29", granularity="MONTH")`

2. `gobus_search_news(query="meio ambiente COP30 clima amazônia", date_from="2026-03-01", limit=10)`

3. Para o artigo mais trending da agência-alvo: `gobus_get_article(unique_id=<id>)`

Output: Relatório de benchmarking de 450 palavras em 5 dimensões — (1) Volume comparativo, (2) Legibilidade vs. governo, (3) Temas proprietários vs. compartilhados, (4) Score de tendência, (5) Recomendações estratégicas. Dados numéricos em destaque.
```

---

### UC-09 — "O Profeta" — Antecipação de Pautas

**Pergunta:** Baseado nos dados, quais temas devem ganhar força nas próximas semanas?

**Prompt para agente:**
```
Você é um analista preditivo de pautas governamentais. Use padrões de crescimento para antecipar agenda.

1. Em paralelo:
   - `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.0, limit=15)` — curto prazo
   - `gobus_detect_trends(window_days=30, baseline_days=90, growth_threshold=0.8, limit=15)` — médio prazo

2. Identifique temas presentes em AMBAS as janelas (crescimento sustentado) — candidatos fortes.

3. Para os 3 temas de crescimento sustentado, em paralelo:
   - `gobus_search_news(query=<tema>, date_from="2026-06-01", limit=5)`
   - `gobus_resolve_entity(query=<tema>, limit=3)` — entidades-âncora

4. Para a entidade-âncora principal de cada tema: `gobus_get_entity_profile(entity_name=<nome>, summary_only=True)`

Output: Radar de pautas de 400 palavras — para cada tema candidato: (a) score de aceleração (razão entre taxas das duas janelas), (b) entidades-âncora, (c) agências cobrindo, (d) janela provável de pico, (e) recomendação editorial. Formato de inteligência de mercado.
```

---

### UC-10 — "O Sintetizador" — Estado da Comunicação Governamental

**Pergunta:** Como está a saúde comunicacional do governo federal hoje?

**Prompt para agente:**
```
Você é o diretor de inteligência comunicacional do governo. Produza um briefing executivo semanal.

1. Em paralelo:
   - `gobus://platform-stats`
   - `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.0, limit=10)`
   - `gobus_get_agency_analytics(agencies=["saude","mec","fazenda","trabalho","mma","planejamento","mre"], date_from="2026-06-01", date_to="2026-06-29", granularity="WEEK")`

2. Identifique agência de melhor e pior desempenho (volume × legibilidade Flesch).

3. Em paralelo:
   - `gobus_get_agency_summary(agency_key=<melhor>, days=30)`
   - `gobus_get_agency_summary(agency_key=<pior>, days=30)`

4. `gobus_search_news(query=<tema_mais_trending>, date_from="2026-06-22", limit=5)`

Output: Briefing presidencial de 500 palavras "Estado da Comunicação — Semana [N]" com: (1) KPIs da plataforma, (2) Agenda temática dominante, (3) Ranking de agências, (4) Destaque da semana, (5) Alerta da semana. Conciso, orientado a decisão.
```

---

## Como executar

### Arquivos de saída

```
gobus-mcp/_experiments/uc-2026-06-29/
  INDEX.md          ← status de cada UC (✅ / ⚠️ / ❌)
  UC-01.md … UC-10.md
```

### Estratégia de execução

Spawnar subagentes (background, paralelo onde possível):
- **Lote A (paralelo):** UC-01, UC-02, UC-04, UC-10 — não dependem entre si
- **Lote B (paralelo):** UC-03, UC-06, UC-08, UC-09 — independentes
- **Lote C (sequencial):** UC-05, UC-07 — requerem `resolve_entity` primeiro

Cada subagente recebe:
- Contexto: limitações de dados desta seção
- Instrução: o prompt completo do UC (copy-paste literal)
- Output: escrever em `UC-NN.md`

### Formato de cada UC-NN.md

```markdown
# UC-NN — [Nome do Personagem] — [Subtítulo]
> **Data:** 2026-06-29 | **Status:** ✅ Completo / ⚠️ Parcial / ❌ Falha

## Briefing
[Pergunta-gatilho]

## Resultado
[Conteúdo substantivo — a resposta real ao use case]

---
## Log de Auditoria

| # | Tool | Parâmetros principais | Resultado resumido |
|---|------|-----------------------|-------------------|

## Gaps e Oportunidades
- [O que faltou, surpreendeu ou pode melhorar]
```

### Verificação pós-experimento

1. `INDEX.md` com status de todos os 10 UCs
2. UC-02 confirma séries DAY completas com zeros (valida P3.11 — `generate_series`)
3. Anotar ocorrências de artigos MOCK e sentimento zerado
4. Identificar os 3 insights mais surpreendentes para memory
