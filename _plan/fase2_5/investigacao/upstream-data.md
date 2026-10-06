> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — relatório de investigação, gerado em 2026-10-05 por agente read-only (wf_98f5ad51-e18). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Relatório: fontes de dados das frentes (2), (3) e (5)

Todos os trechos foram lidos de `origin/main` via `git show`/`git grep`, depois de `git fetch`. Os números vêm do GraphQL público, consultado em 2026-10-05 por volta de 22h UTC.

## 0. Problemas que mudam o plano

1. **A classificação por LLM parou por volta de 26/09.** Tema, sentimento e resumo saem de uma única chamada, em `data-science/src/news_enrichment/worker/handler.py:191-193`, e essa chamada não está mais produzindo resultado.
   - Os 1.121 artigos de 27/09 a 05/10 têm 0 tema e 0 sentimento, também no Postgres.
   - De 15 a 25/09, 1.722 de 1.733 artigos tinham sentimento.
   - `analyticsKpis(days:7)` devolve `activeThemes: 0`, e `themeArticleCounts(days:7)` devolve `[]`.
   - `trendingThemes(windowDays:7, growthThreshold:0)` devolve `[]`.
   - Consequência: `detect_trends`, `forecast_trends`, `detect_anomalies` (parte de temas) e `get_agency_summary` estão vazios hoje.
   - Entidades NER continuam chegando: 97% dos artigos recentes têm entidades e cerca de 95% têm `canonicalId`.
2. **O campo `trendingScore` dos artigos está nulo em 100% das amostras** (6×100 artigos, de maio a outubro).
   - Ou o DAG `compute_trending` não está gravando, ou o `fato_noticias` no BigQuery está velho. Não dá para verificar sem gcloud.
   - `readabilityFlesch` e `wordCount` só existem de março a junho de 2026 (backfill do commit 9c90bb0). Estão nulos desde julho.
3. **O sentimento lido pelo graphql-api está sempre nulo**, por divergência de chave.
   - O worker grava `features->'sentiment' = {label, score}` (`handler.py:266-291`).
   - O SQL do graphql-api lê `features->>'sentiment_score'` e `features->>'sentiment_label'` em `postgres.py:326-345`, `348-391` e `393-412`.
   - Resultado em `agencyAnalytics` e `entityCoverage`: `avgSentimentScore` é sempre `null` e `pctPositive`/`pctNegative` são sempre `0.0`. Isso engana quem lê. Verifiquei em 12 meses × 7 agências.

## A. trendingEntities

**Resolver.** `graphql-api/src/graphql_api/schema/resolvers/entities.py:167-186` limita com `min(limit, 50)`. A busca está em `datasources/postgres.py:1034-1038`, e o SQL em `postgres.py:479-486`:
```sql
SELECT entity_id, canonical_name, type, trending_score, volume_ratio, window_count, window_agencies, computed_at::text
FROM entity_trending_scores ORDER BY trending_score DESC LIMIT $1
```
**Tabela** (`data-platform/scripts/migrations/025_entity_trending_scores.sql:6-19`):
- A chave primária é `entity_id`, e `computed_at` tem default `NOW()`.
- Só há índice em `trending_score DESC`.
- Não existem `run_id`, `baseline_count` nem `window_end`.

**Job.**
- O DAG `src/data_platform/dags/compute_entity_trending.py` roda com `schedule="0 */6 * * *"`.
- O fuso do Composer é `America/Sao_Paulo` (`infra/terraform/composer.tf:61`), então as execuções caem às 03, 09, 15 e 21h UTC.
- A chamada é `load_snapshot(date_end=date.today(), compute_embeddings=False)` → `compute_scores` → `upsert_trending_scores`.
- `jobs/trend_detection/persist.py:10-23` faz `INSERT … ON CONFLICT (entity_id) DO UPDATE` linha a linha, numa única transação (`engine.begin()`).
- **Nunca há DELETE nem retenção.** Com `scores` vazio, a função retorna antes de mexer na tabela (`persist.py:32-33`).

**Por que linhas de 25/06 continuam aparecendo.** A entidade que sai do conjunto pontuado mantém para sempre a última linha gravada. O resolver ordena só por score, sem filtrar pela última execução.
- Ao vivo, o top-50 cobre 32 datas distintas de `computed_at`, de 25/06 a 05/10. Só 2 das 50 linhas são da última execução (`2026-10-05 21:00:20.644118+00`).
- Todos os horários são 21:0x UTC: é a última execução de cada dia UTC que toca a linha.
- **Confirmado:** linhas da mesma execução têm `computed_at` idêntico até o microssegundo, porque `NOW()` devolve o timestamp da transação. Exemplo: 4 linhas com `2026-09-04 21:03:26.145773+00`. Isso permite filtrar pela última execução sem mudar o schema.

**Por que `volumeRatio` chega a 8571×.**
- Em `signals.py:113`: `baseline_daily = bc/28 if bc > 0 else 0.001`. Em `persist.py:43`: `vr = (wc/7)/baseline_daily`.
- Com `bc = 0`, `vr = wc × 142,857`. Para o Censo Escolar 2025 (wc=60): `vr = 8571,4`, calculado em 03/07.
- Com `ba = 0`, o score (`scorer.py:43-48`) fica ≈ `0,6·vr + 0,25·wa` = 5144,1, que confere com o valor ao vivo.
- O menor `vr` possível com bc=0 é 428,6 (wc=3). Todas as 50 linhas do top têm vr ≥ 714, ou seja, **as 50 têm baseline zero**. Uma entidade com baseline real (vr entre 1,5 e 20) nunca entra no top.
- No caso do Censo, 57 dos 60 artigos são de 26/06: um burst padronizado do INEP ("<UF> acompanha avanço do ensino médio público", 27 UFs) mais o MEC. Há duplicatas: 35 títulos distintos em 50.
- O Mais Médicos Especialistas segue o mesmo padrão: 26 artigos de `saude` em 27/08.

**Filtros do commit fea9acd em produção.** O `scorer.py` de produção é idêntico ao de fea9acd, a menos de comentários (diff feito). Os filtros que estão lá:
- `window_count < 3`
- tipo LOC
- `wa <= ba`
- `vr <= 1,5`
- `ba > 20`
- pesos 0,40 / 0,25 / 0,20 / 0,15

**Mas o `semantic_novelty` vale sempre 0.** O DAG passa `compute_embeddings=False` (commit 04393a5), então 15% do peso está morto. O `new_edge_count` é calculado e não é usado.
- O oráculo da pesquisa automática (`signals.py:208-218`) usa o mesmo piso de 0,001. É autorreferente, então o NDCG nunca penalizou o problema.
- Corrida: `project_entity_graph` faz TRUNCATE + reconstrução de `news_entities` na mesma janela `0 */6`. É uma única transação, então os leitores bloqueiam e não veem dados parciais, mas podem ler um snapshot de até 6h atrás.

**Correção proposta.**
1. **No resolver, imediato e sem migração** (`postgres.py:479`):
   ```sql
   WITH last_run AS (SELECT MAX(computed_at) ts FROM entity_trending_scores)
   SELECT … FROM entity_trending_scores, last_run WHERE computed_at = last_run.ts
   ORDER BY trending_score DESC LIMIT $1
   ```
2. **No job** (`persist.py`), na mesma transação e depois do loop: `DELETE FROM entity_trending_scores WHERE computed_at < NOW()`. Isso dá semântica de snapshot. Também é preciso tirar o `return 0` antecipado, ou decidir explicitamente o comportamento com lista vazia. Trocar o execute por linha por executemany.
3. **Baseline** (`signals.py:113` e o oráculo em `:213-218`): suavização de Laplace, `vr = ((wc+1)/7)/((bc+1)/28)`.
   - Censo: 8571 → 244. Entidade nova com wc=3: 16. Entidade estabelecida (wc=20, bc=40): 2,05.
   - Mais `log1p(vr)` no score e uma flag `is_new = (bc == 0)`.
   - Persistir `baseline_count`/`baseline_agencies` (migração 029) e expor no `TrendingEntityResult`.
4. **Proteção contra burst:** adicionar `COUNT(DISTINCT ne.published_at::date)` em `window_stats` e exigir ≥ 2 dias, e/ou contar `window_agencies` excluindo republicadoras.

**Testes a estender.**
- graphql-api:
  - `tests/datasources/test_trending_entities_datasource.py`: o SQL contém o filtro de MAX.
  - `tests/resolvers/test_trending_entities.py`: campos novos.
- data-platform:
  - `tests/unit/jobs/test_trend_detection_persist.py`: DELETE na mesma transação e caso de lista vazia.
  - `tests/unit/jobs/test_trend_detection_scorer.py`: casos com bc=0 e de burst.
  - `tests/unit/dags/test_compute_entity_trending.py`.
  - `load_snapshot` não tem nenhum teste.

**Consumidores afetados.**
- Portal:
  - `src/components/entities/TrendingEntitiesSection.tsx:5-6,39,47` mostra o badge `↑{volumeRatio.toFixed(1)}×`, hoje "↑8571.4×".
  - `src/app/(public)/noticias/page.tsx:34,123-124` usa `getTrendingEntities(6)`.
  - Também: `src/services/content/graphql.ts:424-426` e `src/lib/graphql/queries/entities.ts:149-174`.
- gobus-mcp: `tools/detect_anomalies.py:19,68` e `resources/health_pipelines.py:22,86`.

## B. trendingThemes

Fica em `graphql-api/src/graphql_api/schema/resolvers/analytics.py:177-276` e é calculado na hora, via Typesense.
- Faz 2 consultas de facet em `theme_1_level_1_label` (só nível L1, com `max_facet_values` 100).
- Depois faz até `limit` buscas extras para `topArticles`, ordenadas por `trending_score:desc`, que está nulo; na prática a ordem cai em `published_at`.
- O `themeCode` vem sempre `None`.

Parâmetros e defaults: `windowDays=7`, `baselineDays=28`, `minArticles=3`, `growthThreshold=1.5`, `agencyKey` (filtro `agency:{key}`, sem aspas) e `limit=10`.

**Fórmula** (`:228-230`):
- `baseline_daily = b/B`, `growth = (w/W)/(b/B)`.
- **O baseline se sobrepõe à janela.** As duas janelas são `published_at >= now − N` (`:195-212`), então `b` inclui `w`.
  - Por isso `growth ≤ B/W`: no máximo 4,0 para 7/28 e 7,0 para 3/21.
  - O piso de 0,001 é código morto.
  - O teste `tests/resolvers/test_analytics.py:384` codifica esse comportamento: com w=b=21, growth=4,0.
- **O cliente consegue recuperar a razão verdadeira:** `b = baselineDailyAvg·B`, `b_prev = b − w`, `ratio = (w/W)/(b_prev/(B−W))`. Há um pequeno erro de arredondamento, porque o servidor arredonda para 3 casas.
- A janela é móvel até "agora" e inclui o dia parcial. Os volumes reais são muito diferentes ao longo da semana: sábado ~50, domingo ~23, dias úteis 175–230. Uma janela de 3 dias calculada na segunda-feira contém o fim de semana, o que distorce o resultado de 5 a 8 vezes.
- O `growthThreshold` é aplicado no servidor; para ver quedas é preciso passar 0.

## C. "Silêncio coordenado" (entidade → agência-dona)

**Campos de agência.**
- `entity_registry.agency_key` (migração 015) só é preenchido para as linhas `agencies_seed`, em que `entity_id = 'dgb_' + key` (seed 017).
- `canonicalization.py:1062` aceita `agency_key=None` e nenhum chamador o passa. Por isso entidades POLICY/EVENT/LAW/PER/ORG externas têm `agencyKey` nulo.
- Ao vivo: `agencies` lista 156 agências (não 159), e `entity(id:"dgb_saude").agencyKey = "saude"`.
- O gazetteer de POLICY (027) só tem `domain` e `lifecycle_phase`, sem agência.

**Arestas.**
- `subordinate_to` e `is_agency` existem em `entity_edges` (`jobs/graph/edges.py:136-185`).
- Porém `relatedEntities` e `entityNetwork` filtram `kind='co_mention'` (`postgres.py:178-247`), então **não são expostas**.
- Não existe a query `entityProfile` no SDL.

**Assinaturas** (de `docs/reference/schema.graphql`):
- `entityCoverage(entityId: String!, dateFrom: String = null, dateTo: String = null, granularity: Granularity! = MONTH): [EntityCoveragePoint!]!`, com os campos `{period agencyKey agencyName articleCount totalMentions avgSentimentScore}`.
  - Só traz dias com artigo (sem preenchimento de lacunas).
  - `period` vem em UTC, no formato `"2026-08-27 00:00:00+00"`.
  - `dateTo` é tratado como meia-noite, então **exclui o próprio dia**.
- `agencyAnalytics(agencies: [String!]!, dateFrom: String!, dateTo: String!, granularity: Granularity! = MONTH, metrics: [MetricType!])`.
  - Só a variante DAY preenche lacunas (generate_series) e é inclusiva.
  - Em MONTH/WEEK, o `BETWEEN` com meia-noite exclui o `dateTo`.
- `EntityNode { entityId canonicalName type aliases wikidataId wikidataUrl description agencyKey }`.

**Caminho mais barato e robusto:**
1. Se `entity(id).agencyKey` não for nulo, a dona é a própria agência.
2. Senão, uma única chamada `entityCoverage(id, dateFrom=−90d ou pré-defeso, DAY)`. A dona é a agência com mais artigos, excluindo republicadoras.
   - Custo medido: 0,48 s para dgb_saude (246 linhas) e 0,16 s para entidades pequenas.
   - Exemplos: Censo → inep/mec; Mais Médicos Especialistas → saude.
   - A mesma resposta já traz a série de menções da dona.
3. Desempate por `relatedEntities` com id ∈ {`dgb_<key>`}.
4. Para a produção diária total da dona: `agencyAnalytics([dona], DAY)`, que tem zeros explícitos.

## D. Volume diário total e defeso

**`articlesTimeline` está quebrado.**
- `analytics.py:134` usa `facet_by: "published_date"`, campo que não existe no schema do Typesense (`data-platform/src/data_platform/typesense/collection.py`, que só tem `published_at`, `_year`, `_month` e `_week`).
- Erro ao vivo: `[Errno 404] Could not find a facet field named 'published_date'`. Como o campo não é anulável, a resposta inteira volta com `data: null`.
- O teste `test_analytics.py:192-199` simula esse facet, e por isso passa.

**`analyticsKpis(range:{days})`** só dá total móvel (7d: 930 artigos, 132,86/dia), sem dia de calendário.

**O que funciona hoje:** `agencyAnalytics(agencies:[as 156 keys], DAY)` somado no cliente.
- Para 127 dias: 19.812 linhas, 1,36 MB, cerca de 4 s.
- Os dias são em UTC.

**Números do defeso:**
- Média de 01/06 a 03/07: 239,2 artigos/dia. Média de 04/07 a 04/10: 135,6/dia, ou seja **−43%** (o brief fala em ~35%; a diferença vem das janelas escolhidas).
- 28 agências publicaram em junho e estão com zero desde 10/07: abc, abin, acessoainformacao, agu, casacivil, cbtu, cemaden, coaf, compras, conarq, corregedorias, esd, funai, governodigital, hfa, ibict, icmbio, inpe, insa, int, memoriasreveladas, museudoindio, ouvidorias, palmares, propriedade-intelectual, secom, sri, transferegov.
- 04/10 (domingo, primeiro turno) teve 110 artigos de 6 agências.

**Correção upstream sugerida:** reimplementar `articlesTimeline` em Postgres (`generate_series` + `count(*)` de `news` por `(published_at AT TIME ZONE 'America/Sao_Paulo')::date`).

## E. get_message_coherence

**Filtros de `ArticleFilter`:**
- `agencies`, `themes` (códigos, OR entre L1, L2 e L3), `tags`, `startDate`, `endDate`.
- `themeLabel`: só L1, igualdade exata; funciona com espaços.
- `dedup` (agrupa por `content_hash`).
- `entities` (texto de superfície), `sentiment` (rótulo), `entityCanonical` (ids canônicos).
- Implementação em `typesense.py:191-235`.

**Limites e paginação:**
- `articles` não tem clamp: o `per_page` vai direto, e o Typesense rejeita acima de 250 ("Only upto 250 hits", erro 422). A paginação é por `page`.
- `search` tem `limit=20` fixo (`search.py:56`).

**Datas:**
- `endDate` sem hora vira meia-noite e exclui o dia. Use o dia seguinte ou `T23:59:59`.
- `startDate`/`endDate` sem fuso são interpretados no fuso do servidor.

**`features { entities }`:**
- Vem por DataLoader com uma única consulta `WHERE unique_id = ANY($1)` (`dataloaders.py:69-82`, `postgres.py:149-153`).
- 200 artigos: 0,52 s e 250 KB com features, contra 0,16 s e 33 KB sem.
- Média de 10,6 entidades por artigo; 69,5% das menções têm `canonicalId`.

**`Agency.isRepublisher`:**
- É um frozenset fixo em `schema/types/theme.py:26`: agencia_brasil, tvbrasil, ebc, radioagencia_nacional. A última não existe na lista de agências.
- Só existe no tipo `Agency`. É preciso cruzar com `Article.agency`.

**`publicationHour`** é `published_at.hour` em **UTC** (`article.py:42-46`); por exemplo, 23:49Z vira 23, quando no horário de Brasília são 20h.

**Filtros por tema não servem para datas depois de 26/09** (ver seção 0); para esse período é preciso usar `entityCanonical`.

## F. Custo de `firstMentionDate` / `firstSeenByAgency`

- `news_entities` já tem `published_at` desnormalizado (migração 021) e o índice `idx_news_entities_entity_pub (entity_id, published_at)` (migração 024).
- `MIN(published_at) WHERE entity_id=$1` vira uma busca de intervalo no índice, da ordem de milissegundos. Dá para fazer em lote com `= ANY($1) GROUP BY`.
- `firstSeenByAgency` precisa de JOIN com `news` pela chave primária, e o custo cresce com o número de artigos da entidade (6.835 para dgb_saude: dezenas de ms). Não precisa de índice novo.
  - Opcional: desnormalizar `agency_key` em `REBUILD_NEWS_ENTITIES_SQL` (`edges.py:37-58`).
- Ressalvas:
  - Só conta menções canonicalizadas.
  - A tabela é reconstruída a cada 6h.
  - `entity_registry.created_at` não é a primeira menção.
- Já dá para obter hoje, sem mudar o schema: `entityCoverage(id, granularity: MONTH)` sem datas devolve o primeiro mês por agência em 0,16 s.

## G. Sentimento, trendingScore e mudanças desde julho

**Sentimento.**
- É calculado pelo worker de enriquecimento do data-science com Bedrock Claude Haiku (`feature_registry.yaml:84-89`), na mesma chamada que classifica o tema. Está parado desde cerca de 26/09.
- No Typesense o `sentiment_label` funciona; no Postgres, via graphql-api, está quebrado pela chave (seção 0).

**`trendingScore` por artigo.**
- Vem de `data-platform/src/data_platform/jobs/bigquery/trending.py:12-47`, no DAG `compute_trending` (`0 */6`).
- Fórmula: contagem do tema L1 nas 24h ÷ (contagem em 7 dias ÷ 7), só para artigos das últimas 24h, com `PARTITION BY theme_l1_code`. Temas NULL caem todos no mesmo balde.
- Ao vivo está sempre nulo.

**Commits desde 01/07 no `origin/main`:**
- graphql-api: nenhum depois dos 3 de 01/07 (policyDetails, publicationHour/isRepublisher, policies).
- data-platform: d6d6c88 (CI, 03/07), 31a7e9d (pre-commit, 18/08), 9646b1a e 30e4fe9 (seed de ontologia POLICY, 05/10), bdc884f e d0bb8a5 (chores, 05/10).
- data-science: 38f009c (ontologia POLICY na canonicalização, 06/07) e 2cfbff9 (chore).
- **Nada sobre trending ou sentimento.**

## Implicações para o plano

- **Frente 0 (pré-requisito, fora do gobus-mcp):** abrir um incidente para o enriquecimento por LLM parado desde cerca de 26/09 (tema, sentimento e resumo) e para o `compute_trending`, que não grava. Sem isso, as frentes 3 e 4 (radar de temas) não têm dados. O provável culpado é o worker do data-science; checar logs e cota de LLM (`llm_daily_usage`).
- **Frente 2, PR do graphql-api:**
  - Filtrar pela última execução com `computed_at = MAX(computed_at)`.
  - Corrigir as chaves de sentimento: `features->'sentiment'->>'score'` e `->>'label'` em `postgres.py:326-412`.
  - Reimplementar `articlesTimeline` em Postgres com fuso de Brasília e corrigir o teste que simula o facet.
  - Opcionalmente, um baseline de `trendingThemes` sem sobreposição: janela `[now−B, now−W)`.
- **Frente 2, PR do data-platform:**
  - DELETE de linhas velhas na mesma transação em `persist.py`.
  - Laplace (bc+1) e `log1p` no score.
  - Exigir ≥ 2 dias distintos na janela.
  - Migração 029 com `baseline_count`/`baseline_agencies`.
  - Reavaliar o oráculo em `research/trend-detection`, que é autorreferente.
- **Frentes 2 e 3, defeso:** a partir de 25/10, as 15 a 28 agências que voltam vão gerar `bc=0` em massa. Aplicar o Laplace antes de 25/10, ou restringir o baseline às agências ativas em ambas as janelas, ou usar a janela pré-defeso (06/06 a 03/07) como baseline até cerca de 22/11.
- **Frente 3, no gobus-mcp, sem esperar o upstream:**
  - Calcular a razão verdadeira de `trendingThemes` a partir de `windowCount` e `baselineDailyAvg`.
  - Normalizar por dia da semana: sábado e domingo valem cerca de 25% e 12% de um dia útil.
  - Fazer o share-of-voice com `agencyAnalytics` cobrindo as 156 agências em DAY (uma chamada, cerca de 4 s; vale cachear no resource).
  - Respeitar `horizon_days`.
- **Silêncio coordenado:**
  - Dona = `entity.agencyKey` ou, se nulo, a agência com mais artigos em `entityCoverage(DAY, 90d)` excluindo republicadoras.
  - Silêncio = dona com 0 menções na janela, outras agências subindo, e queda na produção total da dona normalizada pela própria média no defeso (via `agencyAnalytics` DAY).
  - Passar sempre `dateTo` = dia seguinte.
- **Frente 4:** o `ui://article-scorecard` vai mostrar sentimento, Flesch e trending nulos em artigos posteriores a junho. Tratar como "indisponível", não como 0.
- **Frente 5:**
  - Usar `articles(limit ≤ 250, filter:{entityCanonical | agencies, startDate, endDate+1d})` com `features{entities{canonicalId type salience}}`, não `search` (20 por página).
  - Montar o mapa de republicadoras a partir de `agencies{code isRepublisher}`.
  - Converter `publicationHour` para o horário de Brasília (UTC−3).
  - Evitar `themeCode`/`themeLabel` para datas depois de 26/09.
- **Frente 1, limpeza:** o campo do SDL é `baselineDailyAvg`, como na correção prevista para o CLAUDE.md. Remover `radioagencia_nacional` do frozenset ou o vínculo com o portal.

Nota: um `2>` meu em um comando `time` criou sem querer o arquivo `/tmp/null_time_unused`, que só contém saída de tempo. Não o apaguei porque a tarefa é somente leitura; pode ser removido.
