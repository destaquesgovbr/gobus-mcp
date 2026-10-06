# EXPERIMENTO_V3 — Gobus MCP: Inteligência Estratégica e MCP Apps

## Contexto

O V2 confirmou a robustez dos 10 tools e catalogou padrões do ciclo comunicacional do governo. O V3 muda o ângulo: cada UC responde a uma pergunta estratégica que o Panorama DGB (dashboard Streamlit) **não responde hoje** — análise preditiva, coerência inter-agência, equidade, difusão de narrativas, ciclo de vida de políticas. O output de cada UC inclui, além da análise substantiva, um **blueprint de implementação**: que tool/resource/MCP App tornaria este insight disponível em tempo real.

---

## Limitações de dados (invariantes)

| Fonte | Janela segura |
|-------|--------------|
| `news` | ~336k artigos (~2000–hoje) |
| `news_features` (Flesch, sentiment, viewCount) | 2024-06-18+ |
| `news_entities` (NER + entity network) | 2026-03-01+ |
| Sentimento | Sempre 0% positivo — bug persistente; documentar nos relatórios |
| Artigos MOCK | Ainda em produção (issue #3) — ignorar títulos com `[MOCK]` |
| Data de referência | 2026-06-30 |

---

## Os 10 Use Cases — Análise Estratégica Profunda

---

### UC-01 — "O Sismógrafo" — Proto-Crises e Anomalias Comunicacionais

**Pergunta:** Onde estão os sinais fracos de ruptura comunicacional antes de se tornarem crises?

**Prompt para agente:**
```
Você é um analista de risco comunicacional. Sua missão: detectar anomalias de volume e sentimento que precedem crises.

1. Em paralelo:
   - `gobus_detect_trends(window_days=3, baseline_days=21, growth_threshold=2.0, limit=10)` — picos abruptos (janela ultra-curta)
   - `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.5, limit=15)` — tendência semanal

2. Para temas que aparecem em AMBAS as listas (crescimento sustentado E abrupto):
   `gobus_search_news(query=<tema>, date_from="2026-06-24", limit=10)` — verifique o tom.
   Anote: quais agências estão publicando? Quais estão conspicuamente ausentes?

3. Identifique o padrão de "silêncio coordenado": tema com alto crescimento + ausência de agência "dona" (ex: tema saúde sem MH ou Fiocruz). Para cada silêncio:
   `gobus_get_agency_analytics(agencies=[<agência_ausente>], date_from="2026-06-01", date_to="2026-06-30", granularity="DAY")`
   — verifique se a agência parou de publicar ou apenas evita o tema.

4. Para o tema de maior anomalia: `gobus_resolve_entity(query=<tema>, limit=5)` + `gobus_get_entity_network(entity_id=<id_principal>, depth=1, max_nodes=10)`
   — mapeie quem está no epicentro da narrativa.

Output: Relatório de risco de 450 palavras em 3 seções — (A) Tabela de anomalias detectadas (tema, growthScore 3d vs 7d, padrão de silêncio), (B) Análise do epicentro de cada anomalia (entidades centrais, agências presentes/ausentes), (C) Classificação de risco: 🔴 Proto-crise (silêncio + aceleração brusca) / 🟡 Atenção (crescimento sem silêncio) / 🟢 Tendência normal.

**Blueprint MCP:** `gobus_detect_anomalies(sensitivity="high|medium|low")` → MCP App `ui://anomaly-radar` com gauge por domínio (saúde, economia, segurança...) e drill-down por clique.
```

---

### UC-02 — "O Genealogista" — Ciclo de Vida de Política Pública

**Pergunta:** Como uma política pública nasce, amadurece e entra em rotina comunicacional — e onde está esse ciclo agora?

**Prompt para agente:**
```
Você é um historiador da comunicação pública. Reconstitua o arco narrativo completo de uma grande política.

1. `gobus_detect_trends(window_days=90, baseline_days=365, growth_threshold=0.5, limit=10)` — identifique políticas com presença sustentada (não apenas picos). Escolha a de maior volume médio no período.

2. `gobus_resolve_entity(query=<política_identificada>, entity_type="POLICY", limit=3)`

3. `gobus_get_entity_profile(entity_name=<política>, date_from="2024-06-01")` — série temporal completa de cobertura.

4. Segmente a série em fases manualmente pela análise dos picos e vales:
   - Fase 1 Anúncio (primeiro pico), Fase 2 Regulamentação, Fase 3 Implementação, Fase 4 Resultados/Avaliação
   Para cada fase identificada (máx 4), em paralelo:
   `gobus_search_news(query=<política>, date_from=<início_fase>, date_to=<fim_fase>, limit=5)`

5. Para as 2 fases mais intensas: `gobus_get_article(unique_id=<id_mais_trending_por_fase>)` (2 artigos total)

6. `gobus_get_entity_network(entity_id=<id_política>, depth=1, max_nodes=15, node_types="ORG,PER")` — quem são os "âncoras narrativos"?

Output: Cronologia narrativa de 500 palavras estruturada como (1) Mapa de fases com datas e volumes relativos, (2) Entidades âncora por fase (quem liderou cada etapa), (3) Arco retórico (como a linguagem mudou: promessa → instrução → resultado), (4) Fase atual e o que os dados sugerem para os próximos 30 dias.

**Blueprint MCP:** Resource `gobus://policy/<entity_id>/lifecycle` → MCP App `ui://policy-timeline` com swimlane interativo mostrando volume/fase/âncoras por hover.
```

---

### UC-03 — "O Diplomata" — Coerência de Mensagem Inter-Agência

**Pergunta:** Quando o governo fala sobre o mesmo tema em voz múltipla, está em sintonia ou em contradição?

**Prompt para agente:**
```
Você é um auditor de coerência narrativa. Avalie o alinhamento de mensagem entre agências sobre temas partilhados.

1. `gobus_detect_trends(window_days=14, baseline_days=56, growth_threshold=1.0, limit=10)` — top 10 temas.

2. Para cada um dos 5 temas com maior growthScore, em paralelo:
   `gobus_search_news(query=<tema>, date_from="2026-06-01", limit=15)` — extraia agências + amostras de texto.

3. Identifique os 3 temas com maior diversidade de agências publicantes (ex: "emprego" coberto por MTE, SENARC, IPEA, Casa Civil, MEC...).

4. Para cada um desses 3 temas, faça análise de coerência:
   - Quais entidades (PER/ORG) cada agência menciona ao falar do tema?
   - O Flesch médio varia muito entre agências no mesmo tema?
   - Há diferenças de enquadramento (uma agência fala de "resultados", outra de "desafios")?

5. Para o tema mais incoerente: `gobus_get_agency_analytics(agencies=[<lista_de_agências_do_tema>], date_from="2026-06-01", date_to="2026-06-30", granularity="WEEK")` — veja se os picos de publicação são coordenados ou independentes.

Output: Auditoria de coerência de 450 palavras com (A) Índice de coerência por tema (1-5: 1=contradição aberta, 5=mensagem unificada), (B) Mapa de divergências: quem diz o quê de diferente, (C) Hipóteses para as divergências (competição de pauta, audiências diferentes, falta de coordenação), (D) Recomendação de protocolo de alinhamento.

**Blueprint MCP:** `gobus_get_message_coherence(theme, agencies)` → MCP App `ui://coherence-matrix` com heatmap interativo de alinhamento por agência × dimensão (entidades, tom, Flesch, timing).
```

---

### UC-04 — "O Epidemiologista" — Difusão de Narrativas no Ecossistema Gov

**Pergunta:** Como um tema se propaga de uma agência para todo o governo — quem é o "paciente zero" e quem são os "super-spreaders"?

**Prompt para agente:**
```
Você é um epidemiologista da informação governamental. Mapeie a difusão de uma narrativa pelo ecossistema.

1. `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=1.5, limit=5)` — escolha o tema de maior aceleração.

2. `gobus_search_news(query=<tema_top>, date_from="2026-06-01", date_to="2026-06-30", limit=50)` — colete o máximo possível com timestamps.
   Ordene mentalmente por data de publicação: qual agência publicou PRIMEIRO? Quais publicaram em sequência?

3. Identifique o "intervalo de difusão": quantos dias levou para o tema ir da 1ª agência a 5 agências? 10 agências?

4. Para as 5 agências que publicaram mais cedo, em paralelo:
   `gobus_get_agency_analytics(agencies=[<5_early_adopters>], date_from="2026-06-01", date_to="2026-06-30", granularity="DAY")`
   — são as que normalmente publicam mais ou são exceção?

5. `gobus_resolve_entity(query=<tema_top>, limit=3)` + `gobus_get_entity_network(entity_id=<id_principal>, depth=1, max_nodes=12, node_types="ORG")` — a rede de co-menção ORG reflete a ordem de difusão?

Output: Análise epidemiológica de 400 palavras com (A) Linha do tempo de difusão (D+0 a D+N com agências por dia), (B) Perfil dos "early adopters" vs. "late majority", (C) Super-spreaders identificados (agências cujo template de cobertura é copiado), (D) Velocidade de difusão vs. baseline histórico. Tabela: agência × dia_de_adoção × volume_publicado.

**Blueprint MCP:** `gobus_get_diffusion_map(theme, date_from)` → MCP App `ui://diffusion-timeline` com animação de propagação sobre grafo de agências.
```

---

### UC-05 — "O Cartógrafo da Equidade" — Representatividade Geográfica e Temática

**Pergunta:** Quais regiões, populações e temas estão sistematicamente ausentes da comunicação governamental?

**Prompt para agente:**
```
Você é um auditor de equidade comunicacional. Identifique padrões de sub-representação sistemática.

1. Em paralelo:
   - `gobus_search_news(query="Norte Nordeste Amazônia Pará Maranhão Piauí", date_from="2026-01-01", limit=20)` — cobertura regiões historicamente marginalizadas
   - `gobus_search_news(query="Sul Sudeste São Paulo Rio Grande do Sul", date_from="2026-01-01", limit=20)` — baseline comparativo
   - `gobus_search_news(query="povos indígenas quilombolas comunidades tradicionais ribeirinhos", date_from="2026-01-01", limit=20)`
   - `gobus_search_news(query="pessoas com deficiência acessibilidade inclusão", date_from="2026-01-01", limit=10)`

2. Calcule proporções de cobertura e compare com dados demográficos conhecidos (Norte = 8% PIB mas X% cobertura?).

3. `gobus_resolve_entity(query="Norte do Brasil Amazônia", entity_type="LOC", limit=5)` → para a entidade LOC principal:
   `gobus_get_entity_profile(entity_name=<loc_norte>, date_from="2026-03-01")` — série temporal de menções.

4. Identifique temas com cobertura desproporcional. Para os 3 temas mais sobre-representados vs. 3 mais sub-representados:
   `gobus_search_news(query=<tema>, date_from="2026-03-01", limit=5)` — quem publica? Quem não publica?

5. Para a agência com maior gap de equidade (esperada cobertura por mandato, ausente na prática):
   `gobus_get_agency_summary(agency_key=<agência>, days=90)`

Output: Relatório de equidade de 500 palavras com (A) Índice de cobertura geográfica (Norte/Nordeste/Centro-Oeste vs. Sul/Sudeste), (B) Invisibilidade de populações específicas, (C) Mapa de gaps temáticos por mandato de agência, (D) Top 5 oportunidades de cobertura negligenciada com recomendação de agência responsável.

**Blueprint MCP:** Resource `gobus://equity-audit` → MCP App `ui://equity-map` com coroplético do Brasil por intensidade de cobertura + filtros por tema/período.
```

---

### UC-06 — "O Oráculo" — Previsão Multi-Sinal (Horizonte 21 Dias)

**Pergunta:** Combinando velocidade, redes de entidades e padrões sazonais, o que vai dominar a agenda nas próximas 3 semanas?

**Prompt para agente:**
```
Você é um analista de inteligência preditiva de pautas. Produza um forecast fundamentado em múltiplos sinais.

1. Em paralelo (3 janelas temporais para calcular aceleração de 2ª ordem):
   - `gobus_detect_trends(window_days=3, baseline_days=14, growth_threshold=1.0, limit=15)` — ultra-curto
   - `gobus_detect_trends(window_days=7, baseline_days=28, growth_threshold=0.8, limit=15)` — curto
   - `gobus_detect_trends(window_days=21, baseline_days=84, growth_threshold=0.6, limit=15)` — médio

2. Para cada tema: calcule o "score de aceleração composto" = (growthScore_3d / growthScore_7d) × growthScore_21d.
   Temas com score > 1 estão acelerando consistentemente — candidatos fortes.

3. Para os top 4 candidatos, em paralelo:
   `gobus_resolve_entity(query=<tema>, limit=3)` — identifique entidades âncora.

4. Para as entidades âncora principais (máx 2 por tema), em paralelo:
   `gobus_get_entity_profile(entity_name=<entidade>, summary_only=True)` — verifica se a entidade em si está crescendo ou estável.

5. Contexto calendário (sem tool — use conhecimento próprio): há eventos programados nas próximas 3 semanas que amplificariam algum destes temas? (Reuniões do G20, votações no Congresso, datas comemorativas, COP30 preparativos, divulgação de indicadores econômicos...)

6. Para o tema com maior probabilidade de pico: `gobus_search_news(query=<tema>, date_from="2026-06-23", limit=5)` — o que já está sendo publicado como preparação?

Output: Radar de pautas de 450 palavras com tabela de 5 temas (colunas: tema, score_composto, entidade_âncora, amplificador_calendário, janela_provável_de_pico, confiança: alta/média/baixa) + narrativa explicativa de cada previsão + 1 parágrafo sobre limitações do modelo.

**Blueprint MCP:** `gobus_forecast_trends(horizon_days=21)` → MCP App `ui://forecast-radar` com gráfico radar de confiança por tema e timeline de picos previstos.
```

---

### UC-07 — "O Alquimista" — Receita do Artigo de Alto Impacto

**Pergunta:** O que diferencia estruturalmente o artigo mais lido do que ninguém acessa?

**Prompt para agente:**
```
Você é um reverse-engineer de conteúdo governamental. Identifique os padrões dos artigos de máximo impacto.

1. `gobus_search_news(query="", date_from="2026-06-01", date_to="2026-06-30", limit=50)` — coletando um universo base amplo.
   Ordene os resultados por trendingScore (se disponível nos metadados) ou identifique os mais recentes de agências de alto volume.

2. Para os 5 artigos de maior trendingScore e os 5 de menor (controlo), em paralelo:
   `gobus_get_article(unique_id=<id>)` — colete: tamanho (palavras), presença de imagem, hora de publicação, agência, tema.

3. Compare high vs. low performers em:
   - Comprimento médio (palavras) — artigos longos ou curtos performam melhor?
   - Hora de publicação (manhã / tarde / noite / madrugada?)
   - Agência (há um "efeito prestígio" de certas fontes?)
   - Tema (temas de serviço vs. institucional?)
   - Densidade de entidades (artigos com mais PER/ORG mencionadas têm mais engagement?)

4. `gobus_get_agency_analytics(agencies=["saude","mec","fazenda","trabalho","planalto","mre"], date_from="2026-06-01", date_to="2026-06-30", granularity="DAY")` — quais agências consistentemente publicam nos horários de maior tráfego?

5. Escolha a agência de melhor performance por padrão e a de pior: `gobus_get_agency_summary(agency_key=<melhor>, days=30)` + `gobus_get_agency_summary(agency_key=<pior>, days=30)`

Output: Receita de 450 palavras em formato de ficha técnica — (A) "Ingredientes do artigo de alto impacto": comprimento ideal, janela horária, densidade de entidades, tipo de tema; (B) Top 3 agências que mais sistematicamente seguem a receita; (C) Top 3 agências com maiores gaps vs. receita; (D) Score de acionabilidade: o que cada agência pode mudar amanhã para melhorar impacto.

**Blueprint MCP:** `gobus_score_article(unique_id)` → MCP App `ui://article-scorecard` com score visual por dimensão (timing, length, entities, theme) e sugestões inline.
```

---

### UC-08 — "O Estrategista de Legibilidade" — Diagnóstico Acionável de Acessibilidade

**Pergunta:** Quão próxima ou distante está a linguagem governamental da que o cidadão médio consegue compreender?

**Prompt para agente:**
```
Você é um especialista em comunicação pública acessível. Produza um diagnóstico e plano de ação concreto.

1. Em paralelo (amostra ampla de agências por tipo):
   - `gobus_get_agency_analytics(agencies=["saude","mec","mma","trabalho","fazenda"], date_from="2026-01-01", date_to="2026-06-30", granularity="MONTH")`
   - `gobus_get_agency_analytics(agencies=["planejamento","mre","mj","defesa","ciencia"], date_from="2026-01-01", date_to="2026-06-30", granularity="MONTH")`
   - `gobus_get_agency_analytics(agencies=["secom","agu","cgu","tcu","fnde"], date_from="2026-01-01", date_to="2026-06-30", granularity="MONTH")`

2. Referência Flesch (escala brasileira): ≥75 = fácil (Ensino Fundamental), 50-74 = médio (Ensino Médio), 25-49 = difícil (universitário), <25 = muito difícil (especialistas). Classifique cada agência.

3. Identifique as 3 agências mais complexas (Flesch mais baixo) por volume de publicação alto — essas têm o maior impacto negativo em cidadãos comuns.

4. Para cada uma dessas 3 agências, em paralelo:
   `gobus_detect_trends(agency_key=<agência>, window_days=30, baseline_days=90, growth_threshold=0.5, limit=5)` — quais temas ela mais publica nos quais a legibilidade poderia ser melhorada?

5. Para a agência de melhor Flesch com alto volume: `gobus_get_agency_summary(agency_key=<melhor>, days=60)` — o que ela faz diferente?

6. `gobus_search_news(query="direitos benefícios serviços cidadão", date_from="2026-01-01", limit=10)` — artigos de serviço direto ao cidadão têm melhor Flesch do que os institucionais?

Output: Diagnóstico de legibilidade de 500 palavras com (A) Ranking de agências por Flesch × volume (quem mais prejudica cidadãos por baixa legibilidade?), (B) Análise do gap: Flesch atual vs. ideal por audiência-alvo, (C) Case study: o que a agência "campeã" faz diferente, (D) Plano de ação: 3 recomendações específicas para cada uma das 3 piores agências, com exemplos reais de como simplificar.

**Blueprint MCP:** Resource `gobus://readability-report` + `gobus_get_readability_recommendations(agency_key)` → MCP App `ui://readability-dashboard` com benchmark interativo e exemplos de simplificação por hover.
```

---

### UC-09 — "O Decifrador" — Entidades como Termómetro de Política Económica

**Pergunta:** Padrões de co-menção de entidades económicas antecipam eventos de política — ou apenas os refletem?

**Prompt para agente:**
```
Você é um analista de inteligência económica. Teste se menções de entidades são indicadores leading ou lagging.

1. `gobus_resolve_entity(query="Banco Central do Brasil", entity_type="ORG")` + `gobus_resolve_entity(query="Ministério da Fazenda", entity_type="ORG")` + `gobus_resolve_entity(query="SELIC taxa juros", limit=3)`

2. Para cada entidade resolvida (máx 3), em paralelo:
   `gobus_get_entity_profile(entity_name=<entidade>, date_from="2026-03-01")` — série temporal de menções semana a semana.

3. Identifique os picos de menção. Para cada pico: `gobus_search_news(query=<entidade>, date_from=<semana_anterior_ao_pico>, date_to=<semana_do_pico>, limit=8)` — o que estava sendo publicado ANTES do pico? Era antecipação ou reação?

4. `gobus_get_entity_network(entity_id=<id_banco_central>, depth=1, max_nodes=15, node_types="ORG,PER")` — identifique as entidades que co-aparecem com Banco Central. Essas entidades têm os seus próprios picos de menção antes ou depois dos picos do BC?

5. Para as 3 entidades mais correlacionadas na rede: `gobus_get_entity_profile(entity_name=<entidade>, date_from="2026-03-01", summary_only=True)` — confirme se o padrão temporal é leading, lagging ou simultâneo.

6. `gobus_search_news(query="COPOM reunião taxa juros inflação", date_from="2026-05-01", limit=5)` — valide empiricamente com eventos conhecidos (reuniões COPOM).

Output: Análise de 450 palavras como relatório de inteligência económica — (A) Mapa de lead/lag entre entidades económicas (tabela: entidade, relação com BC: leading N dias / lagging N dias / simultâneo), (B) Os 2 eventos mais bem capturados pelo sinal de menções, (C) Os 2 eventos que a análise de menções teria falhado em prever, (D) Hipótese: qual entidade tem o maior poder preditivo no ecossistema gov? Com que horizonte?

**Blueprint MCP:** `gobus_get_entity_lead_lag(entity_id_a, entity_id_b, lookback_days=90)` → MCP App `ui://correlation-chart` com gráfico de cross-correlação interativo com slider de defasagem temporal.
```

---

### UC-10 — "O Arquiteto" — Blueprint Estratégico do Gobus MCP v3

**Pergunta:** Com tudo o que aprendemos nos 9 UCs anteriores, o que deve mudar na plataforma para que este nível de análise seja disponível em tempo real?

**Prompt para agente:**
```
Você é o arquiteto de produto da plataforma Gobus MCP. Sintetize os achados dos UCs anteriores num blueprint de evolução.

ATENÇÃO: Este UC é meta-analítico. Você vai executar algumas chamadas para confirmar hipóteses, mas o output é essencialmente de design de produto.

1. Em paralelo (recolha de dados para embasar propostas):
   - `gobus://platform-stats` — estado atual da plataforma
   - `gobus_detect_trends(window_days=7, baseline_days=28, limit=10)` — temas atuais
   - `gobus://agencies` — inventário de agências disponíveis
   - `gobus://taxonomy-queries` — taxonomia atual

2. Com base nos dados e nos padrões dos UCs anteriores, proponha:

**Novos Tools MCP (prioridade alta):**
- Descreva o tool, assinatura, caso de uso e GraphQL query necessária de alto nível
- Candidatos: `gobus_detect_anomalies(domain, sensitivity)`, `gobus_get_policy_lifecycle(entity_id)`,
  `gobus_measure_coherence(theme, agencies)`, `gobus_score_article(unique_id)`,
  `gobus_forecast_trends(horizon_days)`, `gobus_get_diffusion_map(theme, date_from)`,
  `gobus_get_readability_recommendations(agency_key)`, `gobus_get_entity_lead_lag(entity_id_a, entity_id_b)`

**Novos Resources MCP (prioridade média):**
- Candidatos: `gobus://equity-audit`, `gobus://readability-report`, `gobus://coverage-gaps`,
  `gobus://policy/<entity_id>/lifecycle`

**MCP Apps (transformadores de UX):**
- Para cada App: resource `ui://...`, tipo de componente (D3, Chart.js, Leaflet), interações-chave, dados de entrada, esforço (S/M/L)
- Candidatos: `ui://anomaly-radar`, `ui://policy-timeline`, `ui://coherence-matrix`,
  `ui://diffusion-timeline`, `ui://equity-map`, `ui://forecast-radar`,
  `ui://article-scorecard`, `ui://readability-dashboard`, `ui://correlation-chart`

**Novos Prompts MCP:**
- `prompt_crisis_briefing()` — executa UC-01 automaticamente
- `prompt_policy_audit(policy_name)` — executa UC-02 automaticamente
- `prompt_equity_report()` — executa UC-05 automaticamente

**Melhorias de Schema (graphql-api):**
- Campos em falta que os UCs tentaram inferir: `article.publicationHour`, `article.wordCount`,
  `entity.firstMentionDate`, `theme.policyLifecyclePhase`

**Novas páginas Panorama DGB (Streamlit):**
- Mapa de equidade geográfica (coroplético do Brasil)
- Radar de proto-crises com alertas configuráveis
- Timeline interativa de política pública
- Benchmark de legibilidade com recomendações acionáveis

Output: Blueprint de produto de 600 palavras estruturado como RFC — (A) Sumário executivo (impacto esperado de cada melhoria), (B) Tabela de priorização impacto × esforço × dependências, (C) Roadmap em 3 fases (Quick Wins ≤2 semanas / Core Features 1-2 meses / Advanced 3+ meses), (D) Requisitos técnicos por item, (E) KPIs para medir sucesso pós-implementação.

**Blueprint MCP:** Este UC É o blueprint. O output deste UC é o input direto para o backlog de desenvolvimento.
```

---

## Como executar

### Arquivos de saída

```
gobus-mcp/_experiments/uc-2026-06-30-v3/
  INDEX.md            ← status de cada UC (✅ / ⚠️ / ❌) + top 3 insights cross-UC
  UC-01.md … UC-10.md
  BLUEPRINT.md        ← extrato do UC-10 formatado como RFC de produto
```

### Estratégia de execução

Spawnar subagentes em paralelo por lote:

- **Lote A (paralelo):** UC-01, UC-03, UC-06, UC-08 — análise de estado atual + qualidade
- **Lote B (paralelo):** UC-02, UC-04, UC-07, UC-09 — análise temporal + estrutural
- **UC-05 (após Lote A+B):** contexto de equidade enriquecido pelos achados anteriores
- **UC-10 (último):** síntese — executar após todos os outros completos

Cada subagente recebe:
- Contexto: secção "Limitações de dados" acima
- Instrução: o prompt completo do UC (copy-paste literal)
- Data de referência: 2026-06-30
- Output: escrever em `UC-NN.md` com formato abaixo

### Formato de cada UC-NN.md

```markdown
# UC-NN — [Nome do Personagem] — [Subtítulo]
> **Data:** 2026-06-30 | **Status:** ✅ Completo / ⚠️ Parcial / ❌ Falha

## Briefing
[Pergunta-gatilho]

## Resultado
[Conteúdo substantivo — a resposta real ao use case]

---
## Log de Auditoria

| # | Tool | Parâmetros principais | Resultado resumido |
|---|------|-----------------------|-------------------|

## Blueprint de Implementação
- **Tool/Resource proposto:** `nome_do_tool(params)`
- **MCP App:** `ui://nome-do-componente` — tipo e interações
- **Esforço estimado:** S / M / L
- **Dependência de schema:** [campo novo necessário na graphql-api, se houver]

## Gaps e Surpresas
- [O que faltou, surpreendeu ou contradiz hipóteses]
```

### Verificação pós-experimento

1. `INDEX.md` com status de todos os 10 UCs + top 3 insights cross-UC
2. `BLUEPRINT.md` com tabela de priorização extraída do UC-10
3. UC-06 confirma que o score composto multi-janela funciona melhor do que single-window
4. UC-01 identifica pelo menos 1 proto-crise real ou silêncio estratégico documentado
5. UC-10 produz pelo menos 5 propostas de tools/apps priorizadas por impacto × esforço
