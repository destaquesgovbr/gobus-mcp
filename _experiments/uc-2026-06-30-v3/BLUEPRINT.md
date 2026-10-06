# Gobus MCP — RFC de Evolução v3
> Gerado em: 2026-06-30 | Baseado em: EXPERIMENTO_V3 (10 UCs)

---

## Sumário Executivo

O EXPERIMENTO_V3 executou 10 use cases de análise estratégica usando personas distintas — do Sismógrafo de proto-crises ao Decifrador de indicadores económicos — e chegou a um resultado paradoxal: **cada UC produziu análise substantiva de qualidade, mas nenhum deles usou os tools MCP**. Todos os 9 UCs operacionais falharam 100% nas chamadas `mcp__gobus__*` (`-32602 Invalid request parameters`) e operaram via GraphQL direta.

Esse paradoxo é a primeira e principal conclusão: **os dados e queries existentes já têm capacidade analítica para responder perguntas complexas** — silêncio coordenado da PF no eixo crime (UC-01), arco retórico do Pé-de-Meia em 4 fases (UC-02), difusão bimodal de narrativa militar com reinfecção exógena (UC-04), e o fato de que São Paulo é mencionado como protagonista de notícias 6,2× mais que toda a Região Norte (UC-05). O problema não é cobertura de features: é confiabilidade de transporte e four pipelines mortos.

**Três camadas de evolução:**

1. **Repair (< 2 semanas):** fix transporte MCP (`.mcp.json` `/sse` → `/mcp`) + três pipelines mortos (`trendingScore`, sentimento, Flesch). Sem isso, nenhum tool novo chega ao utilizador.
2. **Amplify (1–2 meses):** encapsular os 9 padrões analíticos descobertos manualmente nos UCs em tools MCP com nomes e assinaturas estáveis. Todos reusam queries GraphQL existentes — o trabalho é de agregação e encapsulamento, não de pipeline novo.
3. **Transform (3+ meses):** tools que exigem schema novo (`Article.entities[]`) ou janela de dados mais longa (>1 ano NER), mais as 9 MCP Apps `ui://` que transformam output textual em componentes interativos.

**Estado atual da plataforma (confirmado pelo UC-10):**
- 6.399 artigos nos últimos 30 dias, 140 agências ativas, 25 temas, 213 artigos/dia em média
- `platformStats` não existe como query GraphQL — usar `analyticsKpis(range:{days})`
- `Article` não expõe `entities`, `wordCount` nem `publicationHour` — três campos de alto valor calculáveis a custo baixo

---

## Bugs Críticos a Corrigir Primeiro

Estes bugs são pré-requisitos de tudo. A ordem de prioridade importa.

### 1. Transporte MCP — sessão SSE não persiste entre chamadas de subagente
- **Sintoma:** `-32602 Invalid request parameters` em 100% das chamadas em todos os 9 UCs (UC-01 ao UC-09), inclusive sem parâmetros.
- **Causa raiz:** o `.mcp.json` aponta para `/sse` (spec 2024-11-05); cada chamada de subagente abre uma nova conexão HTTP, mas o session ID da sessão SSE anterior já não existe no servidor — state lost. O endpoint `/mcp` (Streamable HTTP stateless, spec 2025-03-26) já está exposto pelo servidor e é imune a este problema, porque não há estado de sessão entre requests.
- **Fix:** alterar o `.mcp.json` na raiz do workspace de `"/sse"` → `"/mcp"`. Custo: 10 minutos. Impacto: destrava todos os tools novos e existentes.
- **KPI:** taxa de sucesso de tool-call em subagente de **0% → ≥99%**.

### 2. Pipeline `trendingScore` morto
- **Sintoma:** `trendingScore = null` em 100% dos artigos de junho/2026 (UC-07). `sort: TRENDING` e `sort: VIEWS` tornaram-se no-ops. `viewCount` existe em < 13/50 artigos amostrados, com máximo de 7 views — irrelevante.
- **Impacto:** `gobus_detect_anomalies`, `gobus_forecast_trends`, `gobus_score_article` e qualquer análise de engajamento dependem deste campo. UC-07 teve de usar proxy Flesch+wordCount.
- **Fix:** reativar o job de cálculo de `trendingScore`; auditar quando parou (dados existem para mar–mai com valores degenerados ~7.0); adicionar monitor de "campo 100% null por N dias" como alerta de pipeline.
- **KPI:** `trendingScore` não-nulo em **≥95%** dos artigos.

### 3. Sentimento sempre 0% positivo
- **Sintoma:** `avgSentimentScore = null` e `pctPositive = 0.0` em 100% das agências e períodos testados em todos os 10 UCs.
- **Impacto:** UC-01 (proto-crise) ficou cego ao eixo de *tom* — silêncio coordenado + tom negativo seria um sinal muito mais forte de crise iminente. A plataforma não tem eixo de sentimento operacional.
- **Fix:** auditar o passo de normalização do léxico PT-BR; testar com artigos sabidamente positivos (vitórias da seleção, anúncios de benefícios); recalibrar threshold da binarização positivo/neutro/negativo.

### 4. Flesch com valores abaixo do piso teórico
- **Sintoma:** valores como -46.6 (aviso do INSS para idosos, UC-08), -22.9 (Defesa, UC-08), -96 (nota institucional, UC-07). O piso da escala Flesch-Kincaid adaptada ao PT-BR é definido acima de 0 por construção matemática.
- **Fix:** clamp de Flesch ao piso observado empiricamente (0.0) + auditoria dos 50 artigos com valores mais negativos para identificar padrão de tokenização (siglas, hifenização, abreviações governamentais). O *ranking relativo* entre agências já é robusto — o fix melhora interpretabilidade absoluta.
- **Nota:** o teto real de todo o governo é 17.2 (Secom) — mesmo depois do fix, a escala "fácil ≥75" continuará inacessível. O clamp não oculta essa realidade; melhora apenas os valores impossíveis.

---

## Novos Tools MCP

Todos estes tools são composições de queries GraphQL já existentes — não exigem novos endpoints na `graphql-api`, apenas lógica de agregação no servidor MCP. A coluna "GraphQL subjacente" detalha as queries que cada tool chamaria.

| Tool | Assinatura | Caso de uso principal | GraphQL subjacente | Esforço |
|------|-----------|----------------------|-------------------|---------|
| `gobus_detect_anomalies` | `(sensitivity="high\|medium\|low", domainFilter="")`  | Detectar silêncio coordenado (ex: PF muda enquanto MJ fala de crime) E picos abruptos. UC-01: `trendingThemes` 3d estava cego — o sinal real estava em `trendingEntities × agencyAnalytics` da agência-dona. | `trendingEntities(limit=15)` cruzado com `agencyAnalytics(DAY)` da agência canónica por entidade; score de silêncio = `volumeRatioEntidade ÷ atividadeAgênciaDona` | M |
| `gobus_forecast_trends` | `(horizonDays=21, weekendCorrection=True)` | Previsão multi-sinal com correção de borda de calendário. UC-06 confirmou: produto multiplicativo 3d×7d×21d é frágil em fim de semana (todos os temas < 1.0); a métrica certa é **momentum direction** (derivada entre janelas). | `trendingThemes` em 3 janelas (3d/7d/21d) + `trendingEntities` para âncoras + `entityCoverage(WEEK)` para step-up confirmado | M |
| `gobus_score_article` | `(uniqueId: str)` | Score de qualidade editorial: legibilidade (Flesch), concisão (wordCount), registro (serviço vs. institucional). UC-07: comprimento e dificuldade são independentes (corr=0.05) — "encurtar" não resolve, é o *registro* que importa. NÃO usar `trendingScore`/`viewCount` (mortos). | `article.features { readabilityFlesch wordCount }` + heurística serviço/institucional sobre título+tema | M |
| `gobus_get_readability_recommendations` | `(agencyKey: str)` | Ranking de legibilidade + 3 recomendações acionáveis (pior artigo de exemplo, regra de estilo, ação imediata). UC-08: nenhuma das 14 agências atinge Flesch≥50; melhor é Secom a 17.2. | `agencyAnalytics(MONTH)` + `articles(sort:DATE, features)` para exemplos extremos + `trendingThemes(agency=X)` para tema dominante | S |
| `gobus_get_message_coherence` | `(theme: str, agencies: list[str])` | Índice de coerência inter-agência (1–5) por tema. UC-03: Defesa=4/5 (crise força coordenação), Minorias=3/5, Justiça=2/5. Dispersão de Flesch revela divergência de *forma* mesmo quando o *objetivo* é alinhado. | `articles(filter:{themeLabel}, limit=50)` + `agencyAnalytics(WEEK)` para timing + dispersão de Flesch por agência; classificador de enquadramento (heurística lexical: resultado/anúncio/desafio) | M |
| `gobus_get_diffusion_map` | `(theme: str, dateFrom: str)` | Curva de adoção: paciente zero, intervalos 1→5→10 agências, super-spreaders de volume vs. alcance. UC-04: censipam foi o índice (D+0), defesa é o reservatório, agencia_brasil/tvbrasil são os vetores de amplificação (entram em D+12/D+26). | `articles(filter:{themeLabel, startDate}, sort:DATE)` + `min(publishedAt) group by agency` + join com `agencyAnalytics(VOLUME)` | L |
| `gobus_get_policy_lifecycle` | `(policyName: str)` | Fases de comunicação de uma política pública (anúncio → regulamentação → implementação → rotina) + pivôs retóricos. UC-02: Pé-de-Meia migrou de "justiça social" (2024) para "educação financeira e Tesouro Direto" (2025). | `entitySearch(type=POLICY)` + `entityCoverage(MONTH)` + `search` por janelas de fase | L |
| `gobus_get_entity_lead_lag` | `(entityIdA: str, entityIdB: str, lookbackDays: int = 90)` | Correlação cruzada temporal semanal entre entidades. UC-09: BC↔Fazenda são **coincidentes** (lag=0, r=0.49), não leading. MDIC tem viés leading fraco (+1 semana, r=0.34) mas provável espúrio. O sinal real antecedente está no *conteúdo* (relatórios Focus ~1 semana antes do Copom), não na topologia de co-menção. | `entityCoverage(granularity=WEEK)` para ambas as entidades + cálculo de cross-correlação z-score | L |

**Nota sobre dependências:** `gobus_detect_anomalies` e `gobus_forecast_trends` degradam para proxy (Flesch+wordCount+volume) se `trendingScore` continuar nulo — e devem avisar explicitamente no output quando isso acontece.

---

## Novos Resources MCP

| Resource URI | Conteúdo | Atualização sugerida | Esforço |
|-------------|----------|---------------------|---------|
| `gobus://equity-audit` | Índice de cobertura geográfica por **entidade LOC canônica** (NER, não full-text). Expõe a divergência: por full-text Norte+Nordeste parece equânime (ratio 1.11×), mas por entidade LOC o Sudeste cobre 4.25× mais. SUDAM=0 artigos em H1/2026, FUNAI=0 em fev–abr. | Semanal | M |
| `gobus://readability-report` | Ranking pré-computado Flesch × volume × faixa-alvo por agência + trend 3 meses + gap vs. meta (≥50 para conteúdo de serviço). | Mensal | S |
| `gobus://coverage-gaps` | Temas e agências com maior descasamento mandato↔publicação — SUDAM (Amazônia Legal, 59% do território) com 0 artigos, FUNAI com zeros prolongados, habitação e minorias com apenas 1.0–1.1% do total. | Semanal | M |
| `gobus://health/pipelines` | Estado operacional dos pipelines: `trendingScore` (% null), sentimento (média de pctPositive, esperado >20%), Flesch (% com valores impossíveis), `viewCount` (% não-null). Alerta quando pipeline degrada. | Horária | S |

---

## MCP Apps (ui://)

MCP Apps é uma extensão oficial do protocolo MCP (jan 2026) que permite ao servidor retornar recursos `ui://` — componentes HTML/JS auto-contidos renderizados em iframe pelo cliente. O componente não pode fazer fetch a APIs externas (CSP estrita) — os dados são embutidos como JSON no `<script>` do HTML, ou lidos via tool-calls que o App dispara por `postMessage`.

| App | Tipo de componente | Dados de entrada | Interações principais | Esforço |
|-----|--------------------|-----------------|----------------------|---------|
| `ui://readability-dashboard` | Tabela ranqueada + exemplos | `gobus://readability-report` + `gobus_get_readability_recommendations` | Filtrar agência/tema; clicar linha → artigo pior com trecho ilegível destacado + sugestão de reescrita | S |
| `ui://anomaly-radar` | Gauge radial D3 por domínio (Saúde, Segurança, Economia, Defesa…) | `gobus_detect_anomalies` | Clique em gauge → drill-down entidade↔agência-ausente; toggle pico/silêncio | M |
| `ui://forecast-radar` | Spider/radar Chart.js por tema, com badge de momentum direction | `gobus_forecast_trends` | Hover → série histórica 3 janelas; toggle correção de fim de semana; ver amplificadores de calendário | M |
| `ui://article-scorecard` | Semáforo visual (verde/amarelo/vermelho) por dimensão | `gobus_score_article(uniqueId)` | Benchmark vs. mediana da agência e vs. Agência Brasil (padrão-ouro); side-by-side de 2 artigos | M |
| `ui://coherence-matrix` | Heatmap agência × dimensão (enquadramento, Flesch, timing) | `gobus_get_message_coherence` | Clique numa célula → os 2 releases divergentes lado a lado; isolar dimensão | M |
| `ui://equity-map` | Coroplético SVG do Brasil por intensidade de cobertura LOC | `gobus://equity-audit` | Toggle full-text vs. entidade NER para mostrar divergência 1.11× → 4.25×; filtrar por tema/agência-mandato; hover estado → stats de cobertura | L |
| `ui://diffusion-timeline` | Timeline horizontal D+0…D+N por agência animada | `gobus_get_diffusion_map` | Scrub temporal play/pause; tamanho do nó = volume habitual; cor = early/late/republisher; clicar nó → artigos do dia | L |
| `ui://policy-timeline` | Swimlane por fase (anúncio/regulamentação/implementação/rotina) | `gobus_get_policy_lifecycle` | Hover por fase → volume relativo + âncoras narrativas + amostras de texto; seta de pivô retórico | L |
| `ui://correlation-chart` | Gráfico de cross-correlação com slider de defasagem | `gobus_get_entity_lead_lag` | Slider ±4 semanas; overlay das duas séries normalizadas; badge "leading / coincidente / lagging" | L |

---

## Melhorias de Schema (graphql-api)

Campos descobertos como ausentes pelos UCs — cada um bloqueou uma análise inteira.

| Campo novo | Tipo GraphQL | Justificativa (UC que descobriu o gap) | Esforço |
|-----------|-------------|----------------------------------------|---------|
| `Article.entities: [Entity!]!` | Lista de entidades NER canônicas do artigo | UC-03 (coerência — "que entidades cada agência menciona por tema?"), UC-04 (difusão temporal), UC-05 (equidade — qual região é *protagonista*, não apenas mencionada). O NER existe na tabela `news_features` mas não é exposto. Campo de **maior impacto** do conjunto. | M |
| `Article.wordCount: Int` | Contagem de palavras | UC-07: comprimento e legibilidade são independentes (corr=0.05); encurtar sem reescrever não resolve. Existe como `ArticleFeatures.wordCount` mas não acessível via `search`/`articles`. | S |
| `Article.publicationHour: Int` | Hora de publicação (0–23) derivada de `publishedAt` | UC-07 (janela horária de impacto não validada por falta deste campo), UC-04 (desempate de paciente zero intra-dia — `publishedAt` com timestamp já existe). Derivável no resolver sem custo de storage. | S |
| `Entity.firstMentionDate: DateTime` | Primeira data de menção no corpus | UC-02: rastrear quando uma política "nasce" comunicacionalmente. Sem este campo, a série temporal começa apenas a partir da janela NER (mar/2026+). | M |
| `firstSeenByAgency` por tema/entidade | `[AgencyFirstSeen!]` | UC-04: `entityNetwork` é estático (sem timestamps nas arestas) — inútil para reconstruir ordem de difusão. Hoje calculado client-side sobre todos os artigos; pré-agregar por tema+agência reduziria carga. | M |
| `Agency.isRepublisher: Boolean` | Flag para agências republicadoras (agencia_brasil, tvbrasil, ebc) | UC-03/04: estes três estão no mesmo plano que ministérios no catálogo, inflando diversidade de emissores e distorcendo análises de coerência e difusão. Flag simples resolve com join. | S |

---

## Novas Páginas Panorama DGB (Streamlit)

O Panorama DGB já cobre: volume, sentimento, entidades, legibilidade, engagement (Umami), mapa semântico UMAP, treemap/sunburst/sankey, bump chart de rankings, heatmap 24h×7d, network de co-ocorrência, scatter readability×volume, funnel de engagement.

**Gaps confirmados pelos UCs:**

### 1. Radar de Proto-Crises (UC-01)
Painel de monitoramento de anomalias comunicacionais com dois modos: **picos abruptos** (volume muito acima do baseline) e **silêncios coordenados** (tema com alta entidade-atividade + agência-dona silenciosa). O achado central do UC-01 — PF com apenas 11 artigos em junho enquanto MJ narrava 125 sobre o mesmo eixo de segurança — é exatamente o tipo de sinal que um dashboard de volume puro invisibiliza.
- Componente central: gauge radial por domínio + log de "silêncios suspeitos" da semana
- Dados: `trendingEntities × agencyAnalytics(DAY)` + tabela de entidade→agência-dona

### 2. Mapa de Equidade (UC-05)
O achado mais contraintuitivo do experimento: por menção full-text, a cobertura parece equânime (Norte+Nordeste 12.409 vs Sudeste+Sul 13.753, ratio 1.11×). Por entidade LOC canônica NER, a realidade é São Paulo=1.978, Região Norte=320 — ratio 6.2×. A Amazônia Legal (59% do território) teve 117 artigos em Q2.
- Componente central: coroplético SVG do Brasil com toggle full-text↔entidade NER
- O toggle *demonstra a divergência* em vez de escondê-la — é a pedagogia do achado
- Filtros: tema, agência-mandato, período

### 3. Benchmark de Legibilidade (UC-07, UC-08)
A totalidade do governo federal escreve em faixa "muito difícil" (Flesch < 25). Nenhuma das 14 agências testadas atinge sequer "médio" (Flesch ≥50). A melhor é Secom a 17.2; a pior com alto volume é CGU a -1.2. Um aviso do INSS para idosos pontuou -46.6. Artigos de serviço direto ao cidadão ("direitos benefícios") têm Flesch médio 6.2 — igualmente inacessíveis.
- Componente central: barchart horizontal com faixa-alvo marcada (≥50 para serviço, ≥30 para institucional)
- Hover: artigo mais e menos legível da agência com trecho responsável pela queda
- Evolução trimestral: tendência do Flesch ao longo de 12 meses

### 4. Ciclo de Vida de Políticas (UC-02)
Timeline de fases comunicacionais de uma política pública — o pivô retórico do Pé-de-Meia de "justiça social" (2024) para "educação financeira e Tesouro Direto" (2025) é visível na série temporal mas invisível nos dashboards de volume.
- Componente central: swimlane horizontal por fase com entidades âncora por fase
- Busca por política: aceita nome da política, resolve para entity POLICY, plota o arco
- Depende de: `Entity.firstMentionDate` (schema novo) + canonicalização de POLICYs

---

## Roadmap

### Fase 1 — Quick Wins (≤ 2 semanas)
*Não depende de schema novo. Desbloqueia tudo que vem depois.*

1. Fix transporte MCP: `.mcp.json` `/sse` → `/mcp` no workspace raiz. (10 min — impacto imediato nos 8 tools existentes)
2. `gobus_get_readability_recommendations` — usa Flesch existente, só ordena + exemplos. (1–2 dias)
3. `ui://readability-dashboard` — primeira MCP App como prova de conceito do pipeline ui://. (2–3 dias)
4. Fix sentimento: auditoria léxico PT-BR + reprocessamento. (2–3 dias)
5. Fix Flesch: clamp de valores negativos impossíveis. (1 dia)
6. Resources `gobus://health/pipelines` e `gobus://readability-report`. (1 dia cada)

### Fase 2 — Core Features (1–2 meses)
*Tools analíticos de alto impacto sobre dados existentes, após fixes da Fase 1.*

1. Fix pipeline `trendingScore` (com monitor de null). (1–3 dias pipeline + alertas)
2. `gobus_detect_anomalies` + `ui://anomaly-radar`. (1 semana)
3. `gobus_forecast_trends` (momentum + correção borda) + `ui://forecast-radar`. (1 semana)
4. `gobus_score_article` + `ui://article-scorecard`. (1 semana)
5. Schema: `Article.entities[]`, `Article.wordCount`, `Article.publicationHour`, `Agency.isRepublisher`. (2–3 dias por campo)
6. `gobus://equity-audit` resource. (2–3 dias)
7. Página Panorama "Radar de Proto-Crises" (Streamlit). (1 semana)
8. Página Panorama "Mapa de Equidade" (Streamlit). (1 semana)

### Fase 3 — Advanced (3+ meses)
*Requer schema novo (`Article.entities`) ou janela de dados longa (>1 ano NER).*

1. `gobus_get_message_coherence` + `ui://coherence-matrix`. (depende de `Article.entities`)
2. `gobus_get_diffusion_map` + `firstSeenByAgency` + `ui://diffusion-timeline`. (depende de `Article.entities` + campo temporal)
3. `gobus_get_policy_lifecycle` + `ui://policy-timeline`. (depende de `Entity.firstMentionDate` + canonicalização)
4. `gobus_get_entity_lead_lag` + `ui://correlation-chart`. (janela NER hoje = 18 semanas; robusto apenas com >52)
5. Página Panorama "Benchmark de Legibilidade". (pode antecipar para Fase 2 se depender só de Flesch)
6. Página Panorama "Ciclo de Vida de Políticas". (depende de schema Fase 3)

---

## KPIs de Sucesso

| Área | Hoje | Meta Fase 1 | Meta Fase 2 | Meta Fase 3 |
|------|------|------------|------------|------------|
| Taxa tool-call em subagente | 0% | ≥99% | ≥99% | ≥99% |
| `trendingScore` não-nulo | 0% artigos | — | ≥95% artigos | ≥95% artigos |
| Sentimento positivo funcional | 0% | Bug corrigido | Distribuição realista | — |
| Flesch dentro do intervalo teórico | ~85% | 100% (clamp) | 100% + piso revisado | — |
| Padrões inferenciais cobertos por tool | 0/9 | 2/9 | 6/9 | 9/9 |
| MCP Apps `ui://` em produção | 0 | 1 | 4 | 9 |
| Campos críticos expostos via API | 0/4 | 0/4 | 4/4 (`entities`, `wordCount`, `publicationHour`, `isRepublisher`) | + `firstSeenByAgency`, `firstMentionDate` |
| Workarounds GraphQL manuais por UC | 9/9 | 0/9 | 0/9 | 0/9 |
| Novas páginas Panorama | 0 | 0 | 2 (anomalias + equidade) | 4 |
| Tempo para resposta analítica complexa | N queries manuais | — | 1–2 tool-calls | 1 tool-call + 1 MCP App |

**KPI de transparência (não de produto):** razão de cobertura NER São Paulo/Região Norte (hoje 6.2×) monitorizada e exposta pelo `gobus://equity-audit`. Não é uma meta de produto — é um KPI de verdade sobre a comunicação governamental que a plataforma passa a tornar visível.

---

## Nota sobre MCP Apps

**MCP Apps** é a extensão oficial do protocolo MCP (jan 2026) que permite ao servidor entregar não apenas dados textuais mas **interfaces interativas** renderizadas pelo cliente. O mecanismo são os **UI resources** com URI `ui://`: o servidor declara um resource cujo conteúdo é HTML/JS auto-contido; o cliente MCP renderiza num iframe/superfície isolada em vez de mostrar texto bruto.

O fluxo completo: (1) uma tool retorna, junto do resultado textual, uma referência ao `ui://` resource correspondente; (2) o cliente busca o resource via `resources/read`; (3) renderiza o componente e estabelece um canal `postMessage`; (4) interações do utilizador (ajustar janela do radar, clicar numa célula da matriz) disparam novas tool-calls sem sair da superfície — criando um loop REPL visual sem overhead de sessão.

**O que precisaria ser implementado no servidor FastMCP do Gobus:**

1. **Pré-requisito absoluto:** corrigir o bug de transporte (Fase 1). Apps com sessão SSE quebrada são inutilizáveis.
2. **Registar UI resources:** `@mcp.resource("ui://...")` que retorna HTML/CSS/JS auto-contido. CSS e JS de libraries (Chart.js, D3) devem ser inlineados — a CSP do iframe bloqueia CDN externos.
3. **Declarar associação tool→UI:** cada tool analítica anexa no seu retorno a referência ao `ui://` correspondente + o payload JSON que o componente consome.
4. **Implementar canal de interação:** handlers para tool-calls disparadas pelo App via `postMessage` — drill-down, ajuste de parâmetros, comparação de artigos.
5. **Versionamento:** Apps como resources estáticos versionados pelo servidor; breaking changes nos dados devem bumpar a versão do `ui://` resource.

**Recomendação de início:** começar por `ui://readability-dashboard` (Fase 1), que depende apenas do Flesch existente e não exige tool-call loop — é HTML estático gerado pelo servidor com os dados embutidos. Prova o pipeline MCP Apps com custo mínimo antes de investir nos Apps L que dependem de interatividade e schema novo.

---

*RFC gerado a partir do EXPERIMENTO_V3 (2026-06-30), baseado em 10 use cases com 9 personas analíticas. Os achados quantitativos (6.2×, 4.25×, Flesch=-46.6, SUDAM=0, FUNAI=0 fev–abr, trendingScore=100% null) são dados reais coletados via GraphQL API de produção.*
