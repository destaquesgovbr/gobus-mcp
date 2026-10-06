> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — rascunho de desenho, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# F0 + F2: plano upstream (data-science, data-platform, graphql-api, infra)

Tudo aqui foi verificado em `origin/main` de cada repo (`git show`/`git grep`), por introspecção do GraphQL público e via `gh` (somente leitura). Não rodei gcloud nem terraform.

**Transparência:** uma das sondas enviou a mutation `upsertFeatures(uniqueId:"__nao_existe__", features:{})` sem token. A API recusou com `FORBIDDEN` e nada foi gravado.

## 0. Achados novos que mudam o desenho

**N1. O caminho GraphQL dos workers (feature, typesense-sync, bronze) está quebrado em 4 camadas empilhadas, mais 2 bugs latentes que corrompem dados.** As camadas vêm desde que `GRAPHQL_API_URL` entrou no infra (e991573, 26/05).
1. `GRAPHQL_API_URL = google_cloud_run_v2_service.graphql_api.uri`, sem `/graphql` (`infra/terraform/feature-worker.tf:103-107`, `typesense-sync-worker.tf:115-118`, `bronze-writer.tf:110-113`). Testei ao vivo: `POST /` dá **404**, `POST /graphql` dá 200. É a primeira falha.
2. `$uniqueId: ID!` não existe no schema (`data-platform/src/data_platform/clients/graphql_client.py:121,134,161,177,191`). A API responde `Unknown type 'ID'`.
3. Os campos `themL1Code…themL3Label` não existem (o nome certo é `themeL*`), em `graphql_client.py:126-127,139-140`, `typesense_sync/handler.py:39-44` e `bronze_writer/handler.py:36-41`. Em `NEWS_BATCH_FOR_BIGQUERY_QUERY` (`:148-158`) há mais divergências:
   - o campo se chama `newsBatchForBigquery`;
   - as datas são `String!`, não `DateTime!`;
   - `charCount`, `paragraphCount`, `publicationHour` e `publicationDow` não existem em `BigQueryRecordType`, mas dá para tirá-los de `features`.
   - Validei o template corrigido com graphql-core contra a introspecção ao vivo: todos passam, exceto o de BigQuery, que precisa do ajuste acima.
4. `IsInternal` (`graphql-api/src/graphql_api/auth/guards.py:15-20`) exige `ctx.service_account`, que só é preenchido se existir `SERVICE_ACCOUNT_AUDIENCE` (`context.py:174-184`). Essa env **não existe** em `infra/terraform/graphql-api.tf:101-185`, e o env não está em `ignore_changes`. Resultado: `newsById`, `newsForTypesense` e `upsertFeatures` dão `FORBIDDEN` (confirmado ao vivo).
5. Latente: o handler do feature-worker por GraphQL passa `publishedAt` como str para `compute_publication_hour` (`features.py:265-267`), o que levanta `AttributeError`.
6. Latente e destrutivo: `feature_worker/handler.py:61` envia `json.dumps(features)` (uma string) para o escalar `JSON`. A API faz `json.dumps` de novo (`postgres.py:918`) e `features || $2::jsonb` transforma o objeto num **array** jsonb, corrompendo `news_features`.

**N2. Desde 26/09 não sai nenhum evento `dgb.news.enriched`.** Quando a classificação falha, `update_news_enrichment` pula a linha (`enrichment_job.py:123-127`), o handler devolve `update_failed` e não publica (`handler.py:228-237`).
- Com isso pararam, para artigos novos: feature-worker, typesense-sync (tempo real), embeddings-api, thumbnail, **push-notifications** e **federation**. Todos assinam `dgb.news.enriched` (`infra/terraform/pubsub.tf`).
- O Typesense só recebe artigos pelo `main-workflow.yaml` (cron diário às 04:00 UTC). Isso explica os 14 contra 155 de 05/10 (F0f).

**N3. Segurança.** `verify_service_account` (`graphql-api/src/graphql_api/auth/service_account.py:12-32`) aceita **qualquer** token Google com o audience certo, sem allowlist de e-mail. Nunca definir `SERVICE_ACCOUNT_AUDIENCE` antes de existir allowlist.

**N4. Os 4.600 artigos MOCK (issue #3) também têm tema falso.** Amostrei 60 de 60 em três páginas: `theme1Level1Label = mostSpecificThemeLabel = "Economia e Finanças"`, efeito de `_generate_mock_classifications` (`enrichment_job.py:154+`). `UPDATE summary=NULL` sozinho deixa o tema falso.

**N5. Flesch em português.** O textstat 0.7.13 instalado não tem constantes para `pt` (`LANG_CONFIGS` só tem en, de, es, fr, it, nl, pl, ru, hu). `set_lang('pt')` só troca o silabador e mantém as constantes inglesas, por isso o valor cai para cerca de −30. **Não é** a fórmula adaptada pt-BR (Martins/1996).

**N6. Ciclo de vida do modelo.** Pela referência da skill claude-api, o Claude Haiku 3 (`claude-3-haiku-20240307`) foi aposentado na API Anthropic em 19/04/2026; o Bedrock tem ciclo próprio. Não houve mudança de código em data-science (último `src/` em 06/07) nem em infra (último commit em 03/07) perto de 26/09. A queda é externa ao código.

**N7. Numeração de migração.** O PR data-platform#189 usa `027_add_summary_moderation.sql` com rollback `027_..._ROLLBACK.sql`, em maiúsculas. O runner (`scripts/migrate.py:32-33,123-160`) exige o sufixo `_rollback.sql` e rejeita versões duplicadas. O #189 quebra o runner de duas formas (027 já existe em main, e o `_ROLLBACK` é lido como uma segunda 027). A 029 está livre.

## 1. PRs e ordem

| # | Repo | Branch | Frentes | Depende de | Deploy |
|---|---|---|---|---|---|
| PR-1 INF-1 | infra | `fix/fase2.5-enrichment-model-workers-pg` | F0a, F0b, F0f (hotfix) | confirmar o id do Haiku 4.5 | merge → `terraform-apply.yml` |
| PR-2 DS-1 | data-science | `feature/fase2.5-enrichment-observabilidade-reenrich` | F0a (observabilidade e script de re-enriquecimento) | — | push em `src/news_enrichment/**` → enrichment-worker |
| PR-3 GA-1 | graphql-api | `feat/fase2.5-trending-sentimento-timeline` | F2, F0c, F0d, N3, N6 de N1 | 029 aplicada | push em `src/graphql_api/**` |
| PR-4 DP-B | data-platform | `feature/fase2.5-trending-entities` | F2 e migração 029 | — | 029 via dispatch; merge → `composer-deploy-dags.yaml` |
| PR-5 DP-A | data-platform | `feature/fase2.5-graphql-workers` | F0b (código latente), F0g (documentação) | — | merge → redeploy dos 3 workers (sem efeito enquanto INF-1 vale) |
| PR-6 INF-2 (opcional, depois de 25/10) | infra | `feat/reabilita-graphql-workers` | religar o caminho GraphQL | GA-1 com allowlist em produção, e DP-A | apply |

O portal **não precisa de mudança** (ver §5). Se preferir um PR por repo, PR-4 e PR-5 podem virar um só. Recomendo separar para isolar o prazo de F2.

## 2. F0: triagem por incidente

**Regras para todos os incidentes:**
- Retenção padrão dos logs é de 30 dias, então o início de 26/09 está visível; o de 26/05 (F0b) não está.
- SQL somente dentro de `BEGIN READ ONLY; … ROLLBACK;` via cloud-sql-proxy, e só com autorização sua para ler o secret.
- Comandos AWS são todos de leitura.

### F0a: enriquecimento LLM (tema, resumo e sentimento) zerado desde 26/09

**Triagem:**
```bash
# A1: início e código do erro (o handler loga "Tentativa i/3 falhou para notícia X: <ErrorCode> - <msg>")
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="destaquesgovbr-enrichment-worker" AND textPayload:"falhou para notícia" AND timestamp>="2026-09-25T00:00:00Z" AND timestamp<"2026-09-27T12:00:00Z"' --project=inspire-7-finep --order=asc --limit=20 --format='value(timestamp,resource.labels.revision_name,textPayload)'
# A2: mesmo filtro com --freshness=1d (estado atual)
# A3: desfecho por dia (enriched / update_failed / skipped)
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="destaquesgovbr-enrichment-worker" AND textPayload:"Result for" AND timestamp>="2026-09-20T00:00:00Z"' --project=inspire-7-finep --limit=50000 --format='value(timestamp,textPayload)' | awk '{print substr($1,1,10),$NF}' | sort | uniq -c
# A4: modelos em uso a cada cold start
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="destaquesgovbr-enrichment-worker" AND textPayload:"Cliente Bedrock inicializado"' --project=inspire-7-finep --freshness=30d --limit=20 --format='value(timestamp,resource.labels.revision_name,textPayload)'
# A5: houve troca de revisão perto de 26/09? (A1 com --format='value(resource.labels.revision_name)' | sort | uniq -c, de 20/09 a 28/09)
# A6/A7 (SQL): o ledger e a cobertura dizem quando a chamada combinada parou de consumir tokens
#   SELECT day, model_id, input_tokens, output_tokens FROM llm_daily_usage WHERE day >= '2026-09-15' ORDER BY 1,2;
#   SELECT (n.published_at AT TIME ZONE 'America/Sao_Paulo')::date d, count(*), count(n.most_specific_theme_id) tema,
#          count(n.summary) resumo, count(*) FILTER (WHERE nf.features ? 'sentiment') sent,
#          count(*) FILTER (WHERE nf.features ? 'entities') ent
#     FROM news n LEFT JOIN news_features nf USING (unique_id) WHERE n.published_at >= '2026-09-20' GROUP BY 1 ORDER BY 1;
# A8 (AWS, leitura, conta <AWS-ACCOUNT-ID>)
aws bedrock get-foundation-model --model-identifier anthropic.claude-3-haiku-20240307-v1:0 --region us-east-1 --query 'modelDetails.modelLifecycle'
aws bedrock list-inference-profiles --region us-east-1 --query "inferenceProfileSummaries[?contains(inferenceProfileId,'haiku-4-5')].inferenceProfileId"
aws service-quotas list-service-quotas --service-code bedrock --region us-east-1 --query "Quotas[?contains(QuotaName,'Haiku 4.5')].[QuotaName,Value]" --output table
```

**Hipóteses, em ordem:**
1. **H1: Claude 3 Haiku em fim de vida ou sem acesso no Bedrock.**
   - A1 deve mostrar `ResourceNotFoundException`, `ValidationException` ("end of its life") ou `AccessDeniedException`.
   - No ledger (A6), as linhas do Haiku 3 devem acabar em 25–26/09, enquanto as do `us.anthropic.claude-sonnet-4-6` (NER) continuam.
   - A8 mostra o status `LEGACY` ou EOL.
2. **H2: throttling ou cota diária do Haiku 3.** Nesse caso A3 teria sucessos parciais depois da virada de dia UTC. Zero todos os dias descarta H2.
3. **H3: regressão de deploy.** Exigiria troca de revisão em A5. Pouco provável, porque não houve commit.
4. **H4: mudança na tabela `themes`** (os códigos não mapeiam). Já está descartada pelos dados (o sentimento também sumiu), e o log "Sem tema para X (codes: …)" teria códigos não nulos.

**Correção:**
- H1: PR-1 com `ENRICHMENT_MODEL_ID` = inference profile do Haiku 4.5.
  - Candidato: `us.anthropic.claude-haiku-4-5-20251001-v1:0`. **Confirmar em A8 antes do merge** (o comentário em `variables.tf:198-200` exige o prefixo `us.`).
  - Antes do merge, smoke local com cerca de 20 artigos de 15–25/09, chamando `classifier.classify_single`.
  - Critérios do smoke: 100% de JSON parseável, códigos L1 válidos, e concordância de L1 com os rótulos do Haiku 3 de pelo menos ~80%. A troca de modelo muda a distribuição de temas e afeta F3.
  - Não usar Sonnet 4.6: com ~10–20k tokens de entrada por artigo (a taxonomia vai inteira no prompt, cerca de 27 KB) e ~200 artigos/dia, consumiria cerca de 3M dos 6M tokens/dia do pool compartilhado com canon e NER (`variables.tf:245-259`).
- H2: o mesmo PR-1. Se for cota, pedir aumento à AWS, fora dos repos.
- PR-2 acrescenta observabilidade.

**Backfill:** re-enriquecer de 25/09 até a data do fix, cerca de 3 mil artigos. Detalhes em §4.

### F0b: Flesch e wordCount nulos (de fato desde cerca de 26/05; "30/06" é só a borda do backfill 9c90bb0)

**Triagem:**
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name=("destaquesgovbr-feature-worker" OR "destaquesgovbr-typesense-sync-worker" OR "destaquesgovbr-bronze-writer") AND (textPayload:"Unhandled error" OR textPayload:"Upsert failed" OR textPayload:"404")' --project=inspire-7-finep --freshness=30d --limit=30 --format='value(timestamp,resource.labels.service_name,textPayload)'
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="destaquesgovbr-graphql-api" AND logName="projects/inspire-7-finep/logs/run.googleapis.com%2Frequests" AND httpRequest.requestMethod="POST" AND httpRequest.status=404' --project=inspire-7-finep --freshness=30d --limit=20 --format='value(timestamp,httpRequest.requestUrl,httpRequest.userAgent)'
# Invocações por dia dos assinantes de enriched (espera-se queda em 26/09), para cada serviço:
# feature-worker, typesense-sync-worker, embeddings-api, thumbnail-worker, push-notifications, federation-web
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="destaquesgovbr-feature-worker" AND logName="projects/inspire-7-finep/logs/run.googleapis.com%2Frequests" AND timestamp>="2026-09-15T00:00:00Z"' --project=inspire-7-finep --limit=100000 --format='value(timestamp)' | cut -c1-10 | sort | uniq -c
# SQL: início exato
#   SELECT (n.published_at AT TIME ZONE 'America/Sao_Paulo')::date d, count(*),
#     count(*) FILTER (WHERE nf.features ? 'word_count') wc, count(*) FILTER (WHERE nf.features ? 'readability_flesch') fre,
#     count(*) FILTER (WHERE nf.features ? 'content_annotations') ann
#   FROM news n LEFT JOIN news_features nf USING (unique_id) WHERE n.published_at >= '2026-05-15' GROUP BY 1 ORDER BY 1;
```

**Hipóteses:**
1. Pilha N1 (praticamente certa). A mensagem esperada é `Client error '404 Not Found' for url 'https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app'`.
2. Desde 26/09, também não há gatilho (N2).
3. Crash ou escala do serviço. Os logs descartam.

**Correção:**
- Imediata (PR-1): remover `GRAPHQL_API_URL` dos 3 workers. Eles voltam ao caminho Postgres direto, que funcionou de março a maio e que, para o feature-worker, grava com merge `||` (`postgres_manager.py:734-737`).
- Os bugs latentes vão no PR-5 e no PR-3.

**Backfill:** `scripts/backfill_features_window.py` de 2026-05-20 até amanhã. Não usa LLM. São cerca de 25 mil artigos, a maior parte selecionada pelo filtro `NOT features ? 'readability_flesch'`.
- O PR-5 acrescenta `--dry-run` e `--with-annotations`, porque a lacuna de `content_annotations` do portal tem a mesma origem.
- Ponto em aberto: a lacuna da camada bronze no GCS (bronze-writer) desde cerca de 26/05. Conferir com `gsutil ls gs://<GCS_BUCKET do bronze-writer.tf>/bronze/news/2026/09/`. Fica fora do escopo e deve ser registrada como issue.

### F0c: a graphql-api lê a chave errada do sentimento

- **Triagem:** já confirmado ao vivo (`agencyAnalytics` nulo contra 3.800 rótulos no Typesense). Em SQL, conferir se há chaves planas legadas:
  `SELECT count(*) FILTER (WHERE features ? 'sentiment') aninhado, count(*) FILTER (WHERE features ? 'sentiment_label') plano FROM news_features;`
- **Hipótese única:** chave errada em `postgres.py:332-334,363-365,400` (SQL) e `:578-579,700-701` (mapeadores).
- **Correção:** PR-3.
  - Usar `COALESCE(nf.features->'sentiment'->>'label', nf.features->>'sentiment_label')`, e o equivalente para `score`.
  - `pct_*` passa a ser NULL quando não há rótulo: `AVG(CASE WHEN lbl='positive' THEN 1.0 WHEN lbl IS NOT NULL THEN 0.0 END)`. Isso segue a regra de que nulo não é zero.
- **Backfill:** nenhum (a correção é só na leitura).

### F0d: `articlesTimeline` quebrado

- **Triagem:** o erro ao vivo é `Could not find a facet field named 'published_date'` (`analytics.py:134`).
- **Correção:** PR-3 reimplementa em Postgres, com `generate_series`, dias em `America/Sao_Paulo` e zeros nos dias sem artigo. Isso também elimina o atraso do Typesense.
- **Backfill:** nenhum.

### F0e: `trendingScore` por artigo nulo (prioridade baixa: não bloqueia F2 nem F3)

**Triagem:**
```bash
gcloud logging read 'resource.type="cloud_composer_environment" AND resource.labels.environment_name="destaquesgovbr-composer" AND labels.workflow="compute_trending"' --project=inspire-7-finep --freshness=3d --limit=200 --format='value(timestamp,severity,labels."task-id",textPayload)'
gcloud logging read 'resource.type="cloud_composer_environment" AND resource.labels.environment_name="destaquesgovbr-composer" AND labels.workflow="sync_pg_to_bigquery"' --project=inspire-7-finep --freshness=7d --limit=200 --format='value(timestamp,severity,textPayload)'
# Opcional (bq, leitura): SELECT DATE(published_at) d, COUNT(*) FROM `inspire-7-finep.dgb_gold.fato_noticias` WHERE published_at >= TIMESTAMP('2026-09-01') GROUP BY d ORDER BY d DESC
# SQL: SELECT count(*) FILTER (WHERE nf.features ? 'trending_score') FROM news n JOIN news_features nf USING (unique_id) WHERE n.published_at >= now() - interval '60 days';
```

**Hipóteses:**
1. `fato_noticias` parado, e o DAG registra "No trending scores returned … skipping" (`compute_trending.py:56-58`).
2. Falha de import ou permissão: `jobs/bigquery/trending.py` importa pandas no topo, e `to_dataframe` precisa de `db-dtypes`. A correção de dependência seria em `infra/terraform/composer.tf` (`pypi_packages`), via PR de infra.
3. DAG pausado ou com erro de import (ver na UI do Airflow).
4. Sobrescrita: descartada, porque `upsert_features` faz merge com `||`.

O Composer não define `GRAPHQL_API_URL`, então os bugs de N1 **não** afetam os DAGs.

**Correção:** depende do que os logs mostrarem. Se der mais de um dia de trabalho, registrar como problema conhecido.

**Backfill:** nenhum histórico. O score é do tipo "últimas 24h, por tema L1", então só faz sentido depois do F0a.

### F0f: atraso de indexação no Typesense

- **Triagem:**
  - Comparar `articles(filter:{startDate:"<hoje>"}){found}` com a soma de `agencyAnalytics(<156 agências>, hoje, hoje, DAY)` ao longo do dia.
  - Ver as invocações do typesense-sync (consulta de F0b).
  - `gh run list -R destaquesgovbr/data-platform --workflow=main-workflow.yaml --limit 10`.
- **Hipóteses:**
  1. O tempo real está morto pelas duas causas: N1, desde maio, e N2, desde 26/09. Só sobra o sync diário das 04:00 UTC.
  2. Sobrecarga da VM do Typesense (improvável).
- **Correção:** PR-1, mais F0a. Nenhuma mudança de código.
- **Backfill:** um `typesense-maintenance-sync` (`incremental-sync`, que faz upsert de toda a janela) no fim (§4).

### F0g: fórmula de Flesch em inglês ou em português

**Decisão: manter agora a escala atual, em inglês**, por continuidade com os dados de março a junho, com o benchmark de cerca de 33,5 e com a meta 50. O clamp fica no gobus (F1).
- PR-5 corrige a descrição falsa em `feature_registry.yaml:56-61` ("adaptado pt-BR" passa a "fórmula inglesa do textstat 0.7.13, sem set_lang, com valores negativos possíveis").
- PR-5 também acrescenta um teste que fixa a escala.
- Abrir issue para o futuro `readability_flesch_ptbr` como **chave nova**: 248,835 − 1,015·ASL − 84,6·ASW, com sílabas do pyphen pt_BR, sem sobrescrever a chave atual e **sem** `set_lang`, que é estado global.

## 3. PRs

### PR-1 INF-1 (infra): hotfix de modelo e workers no caminho Postgres

**Objetivo:** restaurar o enriquecimento combinado, as features, o Typesense em tempo real e a camada bronze, sem mudar código.

**Arquivos:**
- `terraform/variables.tf`:
  - nova `variable "enrichment_model_id"`, com default igual ao id confirmado em A8;
  - opcional: acrescentar a chave do Haiku 4.5 em `bedrock_daily_token_quota` (`:245-259`), lida só por jobs de backfill.
- `terraform/enrichment-worker.tf:125-130`: novo `env { name = "ENRICHMENT_MODEL_ID" value = var.enrichment_model_id }`.
- `terraform/feature-worker.tf:103-107`, `typesense-sync-worker.tf:115-118`, `bronze-writer.tf:110-113`: remover o bloco `GRAPHQL_API_URL` e deixar um comentário "reabilitar no INF-2 após allowlist SA (graphql-api) e SERVICE_ACCOUNT_AUDIENCE".

**Testes:** o `terraform-plan.yml` do PR deve mostrar só updates in-place nos templates de 4 serviços (novas revisões), sem nenhum destroy.

**Verificação, 2 a 4 horas depois do apply:**
- Repetir A3: aparecem `enriched` e `textPayload:"Cliente Bedrock inicializado: enrichment=us.anthropic.claude-haiku-4-5…"`.
- Repetir o SQL A7: há tema, resumo e sentimento no dia.
- Há requisições no feature-worker e `word_count` em artigos novos.
- `articles(filter:{startDate:hoje}){found}` chega perto da contagem do Postgres em minutos.

**Gate:** id do modelo confirmado, acesso habilitado na conta e smoke local aprovado.

**Riscos:**
- Mudança na distribuição de temas (o smoke mede).
- Custo ao vivo: cerca de 3M tokens/dia, uns US$3/dia em Haiku 4.5. Conferir a tabela de preços do Bedrock.
- **Ao voltar a publicar `enriched`, os push e o federation retomam só para artigos novos, o que é desejado.**

### PR-2 DS-1 (data-science): observabilidade e re-enriquecimento sem NER

**Objetivo:** tornar visível a falha da chamada combinada e ter um backfill seguro, que não sobrescreva entidades canonicalizadas, não chame o Sonnet e não publique eventos.

**Arquivos:**
- `src/news_enrichment/llm_client.py:202-246,418-446`: `_create_fallback_result(row, error=…)` grava `_error="<ErrorCode>: <msg>"`.
- `src/news_enrichment/classifier.py:224-238`: incluir `'_error'` em `classification_fields`.
- `src/news_enrichment/worker/handler.py`:
  - `:191-239`: detectar falha combinada (`_error` presente ou todos os campos de tema nulos). Logar `logger.error("enrichment_combined_failed uid=%s model=%s error=%s")`, manter o NER e o upsert de entidades, e devolver `{"status":"classification_failed"}` (continua com ACK).
  - `:75-79`: `logger.warning` quando cair no modelo legado por falta de env.
- Novo `scripts/reenrich_combined_window.py`:
  - opções `--select {null-theme,mock}`, `--date-from/--date-to`, `--limit`, `--workers`, `--dry-run`;
  - fluxo: `classify_single` → `update_news_enrichment` → `_upsert_ai_features(uid, {"sentiment": …})` (**sem** `entities`) → `quota_governor.record_usage` e `budget_exhausted` por modelo;
  - **nunca** chama `extract_entities` e **nunca** chama `publish_enriched_event`;
  - mesmo padrão de `scripts/backfill_ner_corpus.py`.

**Testes:**
- `tests/test_enrichment_worker.py`:
  - `test_falha_combinada_loga_erro_e_retorna_classification_failed`;
  - `test_falha_combinada_mantem_upsert_de_entidades`;
  - `test_falha_combinada_nao_publica`.
- `tests/test_enrichment.py`: `test_fallback_inclui_codigo_do_erro`.
- Novo `tests/test_reenrich_combined_window.py` (usa `tests/fakedb.py`):
  - SQL de `null-theme` e de `mock`;
  - não chama NER;
  - o upsert contém só `sentiment`;
  - não publica;
  - para quando `budget_exhausted`;
  - `--dry-run` não escreve nada.

**Verificação:** `cd /Users/nitai/dev/destaquesgovbr/data-science && .venv/bin/python -m pytest tests -q -p no:cacheprovider`. Esse repo não tem CI de testes, então tudo roda local.

**Gate:** PR-1 aplicado, porque o script precisa do modelo novo.

**Risco:** o deploy do worker acontece no merge. A mudança de status não afeta o ACK.

### PR-3 GA-1 (graphql-api): trending, sentimento, timeline e hardening

**Objetivo:** cumprir F2 do lado de leitura, mais F0c, F0d e N3, e impedir N1.6.

**Arquivos:**
- `src/graphql_api/datasources/postgres.py:479-486`:
  ```sql
  SELECT entity_id, canonical_name, type, trending_score, volume_ratio, window_count, window_agencies,
         baseline_count, baseline_agencies, computed_at::text
  FROM entity_trending_scores
  WHERE computed_at = (SELECT MAX(computed_at) FROM entity_trending_scores)
  ORDER BY trending_score DESC LIMIT $1
  ```
  A igualdade é segura: um único `engine.begin()` faz `NOW()` idêntico em todas as linhas da execução.
- `schema/types/entities.py:46-54`: acrescentar `baseline_count: Optional[int]`, `baseline_agencies: Optional[int]` e `is_new: Optional[bool]`.
- `schema/resolvers/entities.py:168-186`: mapear os novos campos. `is_new = baseline_count == 0`; fica None quando a linha é legada.
- `postgres.py:332-334,363-365,400`: chave de sentimento com `COALESCE` e `pct_*` nulo quando não há dado. Em `:578-579,700-701`, helper `_sentiment(features)`.
- `schema/resolvers/analytics.py:120-145`: o resolver passa a ser async e chama o novo `ds.articles_timeline(days)` (com clamp `days ≤ 366`), usando `_ARTICLES_TIMELINE_SQL`:
  - CTE `params(today=(NOW() AT TIME ZONE 'America/Sao_Paulo')::date)`;
  - filtro por faixa sargável em `published_at`;
  - `GROUP BY (published_at AT TIME ZONE 'America/Sao_Paulo')::date`;
  - `generate_series` e `COALESCE(cnt,0)`.
- `auth/service_account.py:12-32`: allowlist. Aceitar só e-mails `*@inspire-7-finep.iam.gserviceaccount.com` ou os listados em `SERVICE_ACCOUNT_ALLOWLIST`; caso contrário, None.
- `schema/resolvers/internal_mutations.py:15-31` e `postgres.py:917-943`: rejeitar `features` que não seja `dict` (`ValueError("features deve ser objeto JSON")`).
- `docs/reference/schema.graphql`: regenerar com `make docs-schema`. O arquivo está desatualizado desde 01/07, e o gobus (F1) usa como contrato.
- **Não mexer em `trendingThemes`.** O F3 recupera a razão verdadeira a partir de `baselineDailyAvg` assumindo o baseline sobreposto de hoje.

**Testes:**
- `tests/datasources/test_trending_entities_datasource.py`: `test_sql_filtra_ultima_execucao` (o SQL passado a `conn.fetch` contém `MAX(computed_at)`) e `test_mapeia_baseline`.
- `tests/resolvers/test_trending_entities.py`: `test_expoe_baseline_count_e_is_new` e `test_baseline_nulo_em_linha_legada`.
- `tests/datasources/test_postgres.py`:
  - os SQLs de analytics e coverage contêm `features->'sentiment'->>'label'`;
  - `_row_to_typesense_doc` e `_row_to_bigquery_record` leem o sentimento aninhado e caem para as chaves planas.
- `tests/resolvers/test_analytics.py:192-231`: reescrever `test_articles_timeline` com mock de `postgres_ds.articles_timeline`, mais `test_timeline_preenche_zeros`, `test_timeline_clamp_366` e `test_timeline_sql_usa_fuso_sp`. O teste atual simula o facet inexistente.
- `tests/resolvers/test_internal_mutations.py`: `test_upsert_features_rejeita_string`.
- `tests/auth/…`: `test_sa_fora_da_allowlist_retorna_none`.

**Verificação:**
- Local: `cd /Users/nitai/dev/destaquesgovbr/graphql-api && .venv/bin/python -m pytest -q && .venv/bin/ruff check src tests`.
- Depois do deploy:
  - `{ trendingEntities(limit:50){ computedAt volumeRatio baselineCount isNew } }`: há um único `computedAt` distinto.
  - `agencyAnalytics(["saude"],"2026-09-01","2026-09-26",MONTH){ avgSentimentScore pctPositive }`: não nulo.
  - `articlesTimeline(range:{days:14})`: 14 pontos.

**Gate:** migração 029 aplicada (§5). O CI `test.yaml` passa.

**Riscos:**
- `pctPositive` muda de semântica (de "fração de todos os artigos" para "fração dos que têm rótulo"). Avisar F1 para o `health_pipelines`.
- Rollback: reverter o PR.

### PR-4 DP-B (data-platform): F2 trending de entidades e migração 029

**Objetivo:** snapshot por execução, Laplace, proteção contra burst, baseline persistido e, conforme decisão, baseline pré-defeso na retomada.

**Arquivos:**
- `scripts/migrations/029_entity_trending_baseline.sql`:
  ```sql
  ALTER TABLE entity_trending_scores
      ADD COLUMN IF NOT EXISTS baseline_count    INTEGER,
      ADD COLUMN IF NOT EXISTS baseline_agencies INTEGER;
  CREATE INDEX IF NOT EXISTS idx_entity_trending_computed_at ON entity_trending_scores (computed_at DESC); -- sem CONCURRENTLY
  ```
  Rollback em `029_entity_trending_baseline_rollback.sql`: `DROP INDEX IF EXISTS …;` e `ALTER TABLE … DROP COLUMN IF EXISTS baseline_count, DROP COLUMN IF EXISTS baseline_agencies;`.
- `src/data_platform/jobs/trend_detection/signals.py`:
  - `:57-67`: em `window_stats`, acrescentar `COUNT(DISTINCT (ne.published_at AT TIME ZONE 'America/Sao_Paulo')::date) AS window_active_days`.
  - `:21-28`: novos parâmetros `baseline_start`/`baseline_end` opcionais (override).
  - `:106-118`: extrair a função pura `build_entity_stats(rows, window_days, baseline_days)`, com:
    - `baseline_daily = bc/B`, **sem piso 0,001**;
    - `volume_ratio = laplace_volume_ratio(wc, bc, W, B) = ((wc+1)/W)/((bc+1)/B)`;
    - `is_new` e `window_active_days`.
  - `:208-218`: o oráculo passa a usar `s["volume_ratio"] > 1.5`.
  - Nova função pura `resolve_baseline_window(date_end, W=7, B=28)` (decisão D2): devolve `[2026-06-06, 2026-07-04)` (28 dias pré-defeso) se `2026-10-26 ≤ date_end < 2026-11-30`; caso contrário, a janela rolante.
- `jobs/trend_detection/scorer.py:25-49`:
  - usar `s["volume_ratio"]`, sem recalcular;
  - `if s.get("window_active_days", 0) < 2: continue`;
  - score com `math.log1p(vr)` nos termos de volume (decisão D1).
- `jobs/trend_detection/persist.py:10-61`:
  - o upsert grava `baseline_count` e `baseline_agencies`;
  - `volume_ratio = s["volume_ratio"]`. É obrigatório: com o baseline cru, `:43` daria `ZeroDivisionError`;
  - `executemany` com a lista de parâmetros;
  - na mesma transação e depois do upsert: `DELETE FROM entity_trending_scores WHERE computed_at < NOW()`;
  - guarda: `if not entity_stats: return 0` (falta de dado não apaga o snapshot). Com `scores` vazio e stats presentes, apaga tudo (o "nada em alta" é verdadeiro).
- `dags/compute_entity_trending.py:38`: `bs, be = resolve_baseline_window(date.today())`, que passa para `load_snapshot`.

**Testes** (todos em `tests/unit/`, porque o CI roda só `tests/unit` com cobertura ≥ 70):
- Novo `tests/unit/jobs/test_trend_detection_signals.py`:
  - bc=0, wc=3 dá vr ≈ 16,0;
  - wc=60 dá ≈ 244,0;
  - wc=20, bc=40 dá ≈ 2,05;
  - não existe 0,001;
  - `window_active_days` é propagado;
  - `resolve_baseline_window` em 2026-10-20 dá a janela rolante; em 2026-10-26 e 2026-11-29 dá o override; em 2026-11-30 volta à rolante.
- `tests/unit/jobs/test_trend_detection_scorer.py`, com a fixture acrescida de `volume_ratio` e `window_active_days`:
  - `test_filtra_burst_de_um_dia`;
  - `test_entidade_nova_nao_explode` (wc=60, bc=0 dá score < 10);
  - `test_usa_volume_ratio_do_snapshot`.
- `tests/unit/jobs/test_trend_detection_persist.py`, ajustando `test_retorna_zero_para_lista_vazia`:
  - `test_delete_stale_na_mesma_transacao` (UPSERT e DELETE `computed_at < NOW()` no mesmo `conn`, nessa ordem);
  - `test_scores_vazios_com_stats_limpa_snapshot`;
  - `test_sem_stats_nao_toca_tabela`;
  - `test_grava_baseline`;
  - `test_baseline_zero_sem_zerodivision`.
- `tests/unit/dags/test_compute_entity_trending.py`: o DAG chama `resolve_baseline_window`.
- `tests/integration/test_migrate_integration.py`: o `test_rollback_last_and_reapply` (`:248`) já pega a 029, desde que ela não use CONCURRENTLY. Acrescentar `test_029_colunas_nulas_e_indice`.

**Verificação local:**
```bash
cd /Users/nitai/dev/destaquesgovbr/data-platform && .venv/bin/python -m pytest tests/unit -q -p no:cacheprovider && pre-commit run --files <alterados>
docker run -d --rm -p 55432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=t pgvector/pgvector:pg16
MIGRATION_TEST_DATABASE_URL=postgresql://test:test@localhost:55432/t .venv/bin/python -m pytest tests/integration/test_migrate_integration.py --no-cov
```

**Verificação em produção** (Composer `labels.workflow="compute_entity_trending"` e SQL read-only):
`SELECT count(*), count(DISTINCT computed_at), max(volume_ratio), count(*) FILTER (WHERE baseline_count=0) FROM entity_trending_scores;`
- Espera-se 1 `computed_at` distinto e `max(vr)` da ordem de `(wc_max+1)·4`, ou seja, centenas no pior caso e não milhares.

**Gate e ordem:** ver §5.

**Riscos:**
- Entidades novas continuam no topo, comprimidas por `log1p`.
- O DELETE pode esvaziar o snapshot (o portal esconde a seção sem quebrar).
- Corrida com o TRUNCATE do `project_entity_graph`: é uma única transação, o leitor bloqueia e não vê dado parcial.

### PR-5 DP-A (data-platform): caminho GraphQL dos workers (latente) e documentação de Flesch

**Objetivo:** consertar N1.2, N1.3, N1.5 e N1.6 (inertes enquanto o INF-1 vale) e travar com teste de contrato.

**Arquivos:**
- `clients/graphql_client.py`:
  - `:121,134,161,177,191`: `ID!` vira `String!`;
  - `:126-127,139-140`: `themL*` vira `themeL*`;
  - `:148-158`: `newsBatchForBigquery`, `String!` nas datas, e `features` no lugar dos 4 campos inexistentes;
  - `:16,37-53`: se o path da URL for vazio, acrescentar `/graphql`; audience do OIDC = `GRAPHQL_API_AUDIENCE` ou a origem da URL.
- `workers/feature_worker/handler.py:48`: parsear `publishedAt` com `datetime.fromisoformat(s.replace("Z","+00:00"))`.
- `workers/feature_worker/handler.py:59-62`: passar o `dict`, sem `json.dumps`.
- `workers/typesense_sync/handler.py:39-44`, `workers/bronze_writer/handler.py:36-41` e `jobs/bigquery/sync_to_bigquery.py:~225-255`: `themeL*`, `newsBatchForBigquery`, e os 4 campos lidos de `features`.
- Mudar os handlers também dispara os deploys por path dos 3 workers.
- `feature_registry.yaml:56-61`: nova descrição do Flesch.
- `scripts/backfill_features_window.py`: `--dry-run`, `--with-annotations` (busca `nf.features->'entities'` e usa `compute_content_annotations`), e `--date-to` com padrão em amanhã.
- `pyproject.toml`: dev-dep `graphql-core = "^3.2"`.
- `tests/fixtures/graphql_api_schema.graphql`: snapshot gerado por `graphql-api/scripts/export_schema.py` no commit do PR-3.

**Testes:**
- Novo `tests/unit/clients/test_graphql_contract.py`: valida **todas** as constantes em maiúsculas de `graphql_client` contra o snapshot. Variante ao vivo marcada `requires_network`.
- `tests/unit/workers/feature_worker/test_handler.py`:
  - `test_graphql_published_at_string_gera_publication_hour`;
  - `test_upsert_graphql_envia_dict`.
- `tests/unit/workers/typesense_sync/test_worker.py`: `test_mapeia_themeL`.
- `tests/unit/workers/feature_worker/test_features.py`: `test_flesch_formula_inglesa_fixada` (frase pt fixa com valor fixo, para detectar `set_lang` acidental).
- Rodar local também `tests/workers` e `tests/dags`, que ficam fora do CI.

**Verificação:**
```bash
cd /Users/nitai/dev/destaquesgovbr/data-platform && .venv/bin/python -m pytest tests/unit tests/workers tests/dags -q -p no:cacheprovider
```

**Gate:** o PR-3 merged (para o snapshot do SDL). Sem pressa: não está no caminho crítico.

**Risco:** nenhum em produção enquanto `GRAPHQL_API_URL` estiver ausente.

### PR-6 INF-2 (opcional, depois do defeso)

**Arquivos:**
- `graphql-api.tf`: env `SERVICE_ACCOUNT_AUDIENCE = local.graphql_api_audience`, uma string constante, para evitar autorreferência ao `.uri`. Só **depois** do allowlist do PR-3 estar em produção.
- Nos 3 workers: `GRAPHQL_API_URL = "${google_cloud_run_v2_service.graphql_api.uri}/graphql"` e `GRAPHQL_API_AUDIENCE = local.graphql_api_audience`.

**Verificação:** logs sem 404 nem FORBIDDEN, e `news_features.features` continua objeto: `SELECT count(*) FROM news_features WHERE jsonb_typeof(features) <> 'object'` deve dar 0.

## 4. Backfills: ordem, custo e cota

Todos escrevem em produção. Cada um precisa do seu OK explícito, roda primeiro com `--dry-run` e com `--limit 10`, e depois completo. A execução é local via cloud-sql-proxy (o mesmo padrão do 9c90bb0) ou pelo workflow indicado.

| # | Quando | O quê | Volume e custo | Cota |
|---|---|---|---|---|
| B1 | depois do PR-1 | `backfill_features_window.py --date-from 2026-05-20` (com `--with-annotations` depois do PR-5) | ~25 mil artigos, só CPU, minutos | — |
| B2 | depois do PR-2 em produção | `reenrich_combined_window.py --select null-theme --date-from 2026-09-25` | ~3 mil artigos × ~10–20k tokens ≈ 30–60M tokens, ~US$30–60 em Haiku 4.5. **Medir antes tokens por artigo no ledger do Haiku 3** (o tokenizer difere) | `BEDROCK_DAILY_TOKEN_QUOTA='{"<id haiku 4.5>": 0,8×cota AWS}'` (cota lida via service-quotas). O worker ao vivo usa o **mesmo** pool do Haiku 4.5, e o governador o protege. O pool de 6M/dia do Sonnet **não é tocado** (sem NER) |
| B3 | depois de B2 | embeddings da janela: conferir `count(*) FILTER (WHERE content_embedding IS NULL)` por dia desde 25/09; gerar com `embeddings_client.generator` (janela, `content_embedding IS NULL`; o texto usa título e resumo, por isso depois de B2) | ~3 mil, sem LLM | — |
| B4 | depois de B1 a B3 | `typesense-maintenance-sync` (`incremental-sync`, de 2026-05-20 até hoje, batch 1000) via `gh workflow run` (você dispara) | ~25 mil documentos | — |
| B5 | decisão D3 | `reenrich --select mock` (4.600) e depois `incremental-sync` de 2025-09-24 a 2026-02-28 | ~45–90M tokens, ~US$50–90 | mesmo governador |
| — | não fazer | reenviar `dgb.news.enriched` para artigos antigos | geraria push e federation de notícias velhas | — |
| — | não fazer | histórico de `trendingScore` por artigo e re-sync de BigQuery | o valor é sempre "últimas 24h" | — |

Otimização opcional, depois da fase: prompt caching do bloco de taxonomia no prompt combinado, que corta cerca de 80% do custo de entrada ao vivo e no backfill.

## 5. F2: numeração, migração, ordem de deploy e consumidores

**Numeração.** A F2 fica com a **029**. Comentar no #189 (autor ODenteAzul, revisão "REQUER MUDANÇAS", parado desde 17/07) pedindo:
- renumerar para **030** (027 e 028 já existem em main);
- renomear o rollback para `030_add_summary_moderation_rollback.sql`, em minúsculas, porque `_ROLLBACK` é lido como uma segunda migração e aborta `discover_migrations`.

O `ci-migrations.yaml` do #189 pega o conflito.

**Aplicar a 029.** O environment `production` do data-platform não tem `deployment_branch_policy` (verificado com `gh api`), então dá para disparar a partir do branch do PR antes do merge:
```bash
gh workflow run db-migrate.yaml -R destaquesgovbr/data-platform --ref feature/fase2.5-trending-entities -f command=status
gh workflow run db-migrate.yaml -R destaquesgovbr/data-platform --ref feature/fase2.5-trending-entities -f command=migrate -f dry_run=true -f target_version=029
gh workflow run db-migrate.yaml -R destaquesgovbr/data-platform --ref feature/fase2.5-trending-entities -f command=migrate -f dry_run=false -f confirm=true -f target_version=029
```
- O próprio workflow cria um backup on-demand antes de aplicar.
- A 029 é aditiva e nula, e o `persist` antigo lista colunas explícitas, então é inofensiva para o código atual.
- Depois de aplicada, congelar o arquivo.

**Ordem de deploy:**
1. 029.
2. Merge do PR-4, na janela logo após um run. O DAG roda a `0 */6` no fuso de São Paulo, ou seja, 03, 09, 15 e 21 UTC; fazer o merge por volta de 21:05 UTC.
3. Merge do PR-3.

"graphql-api primeiro é seguro?" Para o filtro `MAX` sozinho, sim: não depende de schema, tira as linhas velhas na hora, mas os ratios continuam inflados até o PR-4. O PR-3 como desenhado lê `baseline_*`, então **exige a 029 aplicada**. Com a 029 aplicada primeiro, a ordem entre PR-3 e PR-4 fica livre.

**Rollback:** reverter o PR-3, depois reverter o PR-4. Rodar `db-migrate rollback 029` é opcional, porque as colunas nulas são inofensivas.

**Portal:** não precisa de mudança.
- `TrendingEntitiesSection.tsx:5-6` mostra `↑{volumeRatio}×`, que cai de cerca de 8571× para uma faixa de 2 a ~250×.
- Os campos novos são aditivos; `queries/entities.ts:149-174` e o e2e `public-content.spec.ts:360-366` não mudam.
- Opcional, depois da fase: badge "novo" quando `isNew` for verdadeiro.

**Avisar os donos de F1 e F3 no gobus:**
- Depois do PR-3, `computedAt` fica uniforme. O health check deve olhar a fração de `isNew` no top-N, não a idade.
- Os limiares 2/3/5× de `detect_anomalies` passam a filtrar de verdade.
- `pctPositive` pode vir nulo.

## 6. Cronograma até 25/10/2026

| Data | Ação |
|---|---|
| ter 06/10 | Triagem F0 completa (A1 a A8, F0b, F0e, F0f) e smoke local do Haiku 4.5. Abrir PR-1 |
| qua 07/10 | Merge do PR-1 e apply. Verificar nas 2 a 4 horas seguintes. Subagentes começam PR-3 e PR-4 (TDD) |
| qui 08/10 | B1 (features). Abrir PR-2 |
| sex 09/10 | Merge do PR-2 e deploy. Iniciar B2 com o governador. PR-4 pronto para review e 029 com `dry_run` |
| seg 12/10 | **Feriado (N. Sra. Aparecida): sem deploy** |
| ter 13/10 | 029 aplicada pelo branch. Merge do PR-4 por volta de 21:05 UTC |
| qua 14/10 | Conferir os runs de 03 e 09 UTC (SQL e logs). Merge do PR-3. B3 |
| qui 15/10 | B4 (Typesense). Merge do PR-5 |
| **sex 16/10** | **Gate F2 em produção** (9 dias de folga). B5, se D3 for aprovada |
| 19 a 23/10 | Observação: pelo menos 20 runs. Métricas: 1 `computed_at` distinto, `max(vr)`, fração `isNew` no top-50, zero ocorrências de `enrichment_combined_failed` |
| sáb 24/10 | Congelamento upstream até 27/10 |
| dom 25/10 | Fim do defeso. A partir de seg 26/10 o override de baseline liga sozinho (D2), com monitoramento diário até 30/11 |
| depois de 30/11 | PR-6 (opcional) e issue do `readability_flesch_ptbr` |

## 7. Decisões pendentes

- **D1.** `log1p(vr)` no score do PR-4. Recomendo incluir: não muda nenhum contrato, só a ordem do ranking.
- **D2.** Baseline pré-defeso de 06/06 a 03/07, ativo de 26/10 a 29/11, via `resolve_baseline_window`. Recomendo incluir: é o que realmente neutraliza o `bc=0` em massa da retomada.
- **D3.** Issue #3: trocar "UPDATE summary=NULL" por re-enriquecimento (B5), porque o tema também é falso (N4). Se mantiver o UPDATE, zerar também `theme_l1_id`, `theme_l2_id`, `theme_l3_id` e `most_specific_theme_id`.
- **D4.** Separar em PR-4 e PR-5, ou juntar num PR só no data-platform.
- **D5.** Quem roda os backfills e onde: localmente (padrão 9c90bb0) ou num workflow `workflow_dispatch` novo.

### Critical Files for Implementation
- /Users/nitai/dev/destaquesgovbr/data-platform/src/data_platform/jobs/trend_detection/persist.py (e `signals.py`, `scorer.py` no mesmo diretório, mais `scripts/migrations/029_*`)
- /Users/nitai/dev/destaquesgovbr/graphql-api/src/graphql_api/datasources/postgres.py
- /Users/nitai/dev/destaquesgovbr/data-science/src/news_enrichment/worker/handler.py (e `llm_client.py`)
- /Users/nitai/dev/destaquesgovbr/infra/terraform/enrichment-worker.tf (e `feature-worker.tf`, `typesense-sync-worker.tf`, `bronze-writer.tf`, `variables.tf`)
- /Users/nitai/dev/destaquesgovbr/data-platform/src/data_platform/clients/graphql_client.py
