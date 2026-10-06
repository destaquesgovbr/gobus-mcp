> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — verificação adversarial, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

**Verificação adversarial do rascunho F0+F2-upstream**

Conferi o rascunho contra `origin/main` de infra, data-platform, data-science, graphql-api, portal e embeddings, contra a introspecção e as queries ao vivo, contra o `gh` em modo leitura e contra o textstat da venv. Para confirmar o FORBIDDEN usei só uma query (`newsById`). Nenhuma mutation foi enviada.

**O que está correto e pode ficar como está:**
- **N1.1 a N1.6:**
  - `POST /` dá 404 e `/graphql` dá 200. O tipo `ID` não existe.
  - `themL*` não existe. O campo é `newsBatchForBigquery`, com datas `String!`, e `BigQueryRecordType` não tem os 4 campos.
  - `SERVICE_ACCOUNT_AUDIENCE` não aparece em `graphql-api.tf`.
  - `json.dumps` está em `handler.py:61` e `postgres.py:918`.
- **N2:** o desvio para `update_failed` (`handler.py:228-237`) e os 6 assinantes de `enriched` (`pubsub.tf`). O bronze assina `scraped`.
- **N3:** `service_account.py:12-32` não tem allowlist.
- **N4:** confirmei ao vivo. A busca dá `found 4600` e o tema é "Economia e Finanças".
- **N5:** `LANG_CONFIGS` não tem `pt`.
- **N7:** o runner rejeita versões duplicadas e o `_ROLLBACK` em maiúsculas.
- O Composer não define `GRAPHQL_API_URL`.
- Os 3 workers têm `DATABASE_URL` e caminho PG funcional.
- Os nomes dos serviços, `ignore_changes` só da imagem, os gatilhos de deploy, os inputs do `db-migrate.yaml`, o environment `production` sem política de branch, os nomes das tabelas do ledger e a mensagem de log `Cliente Bedrock inicializado`.
- As contas de Laplace (16 / 244 / 2,05) e a janela D2 até `< 2026-11-30` (é exatamente quando o baseline rolante fica todo pós-defeso).

## (A) Correções obrigatórias

1. **B1 cobre só até 01/07.** O comando de B1 tem só `--date-from 2026-05-20`, e o default de `--date-to` no script é `"2026-07-01"`. Como B1 roda em 08/10, antes do PR-5, julho a outubro fica de fora.
   - **Correção:** passar `--date-to <amanhã>` explicitamente.
   - **Evidência:** `/Users/nitai/dev/destaquesgovbr/data-platform/scripts/backfill_features_window.py:28-29`.

2. **A segunda passada `--with-annotations` não seleciona nada.** O filtro do script é `NOT nf.features ? 'readability_flesch'`. Depois de B1 em 08/10, uma passada com `--with-annotations` (PR-5, 15/10) não encontra nenhuma linha, e `content_annotations` fica faltando desde 26/05.
   - **Correção (uma das duas):**
     - mudar o filtro para `NOT (features ? 'readability_flesch' AND features ? 'content_annotations')`;
     - ou adiar B1 até o PR-5 e rodar uma vez só.
   - **Evidência:** mesmo arquivo, `:48`.

3. **A cota do backfill é aplicada duas vezes.** `BEDROCK_DAILY_TOKEN_QUOTA = 0,8×cota AWS`, somado à fração padrão de 0,8, dá um teto efetivo de 0,64×. `budget_exhausted` já calcula `fraction × daily_quota`.
   - **Correção:** usar a cota real da AWS, com margem como a do Sonnet (6,0M contra 6,4M), e deixar `BACKFILL_QUOTA_FRACTION=0.8`.
   - **Evidência:** `/Users/nitai/dev/destaquesgovbr/data-science/src/news_enrichment/quota_governor.py:113-140`.

4. **`target_version=029` pode aplicar também 027 e 028.** O `migrate --target 029` aplica tudo o que estiver pendente até 029. A 027 (seed POLICY) foi renumerada hoje (9646b1a, 05/10), e a mensagem do commit diz que "em prod o histórico só registra 026…". A 027 e a 028 podem estar pendentes em produção.
   - **Correção:**
     - depois do `status`, se 027 ou 028 estiverem pendentes, aplicá-las num dispatch separado (`target_version=028`), combinado com quem cuida do trabalho do gazetteer (o branch local é `feature/policy-gazetteer`);
     - só então aplicar a 029.
   - **Evidência:** `git show 9646b1a`; `scripts/migrate.py`.

5. **O conselho de health check está invertido.** O rascunho diz que, depois do PR-3/PR-4, o health check deve olhar `isNew` e não a idade. Mas com o DELETE fica um único `computedAt`, e a idade dele passa a ser o sinal certo de dado velho. Se o DAG parar, ou se cair na guarda `if not entity_stats: return 0`, o snapshot envelhece.
   - **Correção:** usar a idade de `max(computedAt)` (mais de 7h = alerta) **e** a fração de `isNew` no top-N.

6. **Correções pontuais de referência:**

   | Onde | Está no rascunho | Correção | Evidência |
   |---|---|---|---|
   | Tabela de PRs, PR-3 | "N6 de N1" | N1.6 (N6 é o ciclo de vida do modelo) | — |
   | `typesense_sync/handler.py` | `:39-44` | `:40-45` | — |
   | `compute_trending.py` | "skipping" em `:56-58` | `:57-60` | — |
   | PR #189 | "revisão REQUER MUDANÇAS" | É um **comentário** ("Review Final…"). Não há review formal no GitHub: `reviewDecision` vazio, `reviews:[]`, `mergeable: MERGEABLE` | `gh pr view 189` |
   | PR-3, testes de `_row_to_*` | `tests/datasources/test_postgres.py` | Já existem `tests/datasources/test_postgres_bigquery.py` e `test_postgres_features.py` | árvore de testes da graphql-api |
   | PR-3, allowlist | `tests/auth/…` | `tests/auth/test_service_account.py` (já existe) | idem |
   | PR-3, timeline | reescrever só `test_articles_timeline` | `test_invalid_range_returns_error` (`test_analytics.py:233`) também chama o resolver e precisa ser adaptado | `tests/resolvers/test_analytics.py` |

7. **Faltam as regras de commit por repo, e o default do harness as violaria.**
   - O `infra/CLAUDE.md` proíbe atribuição ou co-autoria do Claude.
   - O `graphql-api/CLAUDE.md:175` pede "português, sem `Co-Authored-By`, prefixos `feature:`/`fix:`…".
   - O data-platform aceita (9646b1a tem `Co-authored-by`).
   - **Correção:** pôr no plano uma tabela de convenção por repo.

8. **Processo: a sonda com mutation viola o modo read-only.** O FORBIDDEN pode ser confirmado com uma query: `query($u:String!){newsById(uniqueId:$u){uniqueId}}` dá `FORBIDDEN`. Registrar no plano que validações futuras usam só queries.

## (B) Lacunas

1. **O filtro de ≥2 dias distintos não pega os casos que o motivaram.** No Censo, 57 dos 60 artigos são do mesmo dia e os outros 3 de outros dias, então passa no filtro. O `test_filtra_burst_de_um_dia` só cobre o burst puro.
   - Acrescentar um teste com a divisão 57/3 que documente o comportamento esperado.
   - Avaliar uma guarda complementar: fração do dia de pico ≤ 0,7, ou dedup por título (35 títulos distintos em 50).

2. **Com `log1p(vr)`, o `agency_growth` passa a dominar o ranking.** Esse termo (`wa/max(ba,1)`) não é comprimido. Com `ba=0` e `wc=60`, o score fica ≈ 3,3 + 0,25·wa: com 27 agências ou mais, passa de 10 e o teste `test_entidade_nova_nao_explode` depende da fixture. Os pesos 0,40/0,25/0,20/0,15 foram calibrados para `vr` cru.
   - Comprimir ou limitar o `agency_growth`.
   - Rodar `research/trend-detection/evaluate.py` offline antes de decidir a D1.

3. **A D2 entra em produção pela primeira vez sozinha, em 26/10.** Falta um ensaio: rodar `load_snapshot` com `date_end=2026-10-26` em leitura (SQL read-only) entre 19 e 23/10 e conferir o top-N.
   - O significado de `is_new` muda durante o override: passa a ser "não visto em junho". Documentar isso.

4. **AWS (A8 e gate do PR-1):**
   - O plano não diz de onde vêm as credenciais. A única conhecida é o secret `airflow_aws_bedrock_conn`, e lê-lo precisa da sua autorização.
   - O usuário IAM provavelmente só tem `bedrock:InvokeModel`, então `get-foundation-model`, `list-inference-profiles` e `service-quotas` podem dar AccessDenied.
   - Acrescentar ao gate a política IAM para o perfil `us.` **e** para os ARNs do modelo nas regiões de destino do perfil cross-region.
   - Prova mais direta: um `invoke_model` mínimo nos dois IDs, que já está implícito no smoke.

5. **Secrets do smoke do PR-1.** O smoke lê a taxonomia do PG (`load_taxonomy_from_postgres`) e usa as credenciais AWS. Precisa de autorização para os dois secrets, e o plano só menciona a do SQL.

6. **Coordenação com o #189:**
   - O `tests/unit/test_pg_migrations.py::test_versions_have_no_gaps` faz o #189 só poder virar 030 **depois** que a 029 estiver em `main`.
   - O #189 e o PR-5 mexem no mesmo `jobs/bigquery/sync_to_bigquery.py`, então vai haver conflito.

7. **B5 e embeddings (plausível, não confirmado).** O texto do embedding é título + resumo (`embeddings_client/text_prep.py`). Os 4.600 artigos MOCK provavelmente têm embedding gerado a partir do resumo `[MOCK]…`. Só que `_fetch_news_without_embeddings` pega apenas `content_embedding IS NULL`, então o B5 precisa zerar esses embeddings antes de regenerar.
   - O B3 também precisa de `EMBEDDINGS_API_URL`/chave (`EmbeddingGenerator(database_url, api_url, api_key)`), que é mais um secret.

8. **Thumbnails.** O thumbnail-worker assina `enriched`, e o plano proíbe reenviar eventos. Conferir se o DAG `generate_video_thumbnails` cobre os vídeos de 26/09 até o fix.

9. **Contrato GraphQL ao vivo no CI.** Se a variante ao vivo (`requires_network`) ficar em `tests/unit/`, ela roda no CI: o `tests.yaml` não desseleciona markers. Isso torna o CI dependente de produção. Proteger com variável de ambiente ou mover para fora de `tests/unit`.

10. **Testes que hoje fixam o bug.** `tests/workers/test_*_graphql.py` e `tests/dags/test_bigquery_sync_graphql.py` usam fixtures com `themL*`. O PR-5 precisa reescrevê-los (passo red).

11. **Drift no `terraform-plan`.** O último apply do infra foi em 03/07. O plano de PR pode trazer diffs que não são deste PR (por exemplo `client`/`client_version` deixados pelos `gcloud run services update`). O critério deve ser "nenhum destroy ou replace, e diffs alheios explicados", não "só 4 updates".

12. **PR-2: a correção é só um warning.** O default `DEFAULT_ENRICHMENT_MODEL_ID` continua sendo o Haiku 3 em `llm_client.py:29`, `handler.py:78` e `classifier.py`. Trocar o default para o perfil confirmado, ou falhar no startup quando faltar a env.

13. **Volumes superestimados (menor).**
    - B2: de 27/09 a 05/10 são 1.121 artigos, então até 07/10 dá cerca de 1,6 a 1,9 mil, não 3 mil.
    - B1: junho já tem Flesch, então são cerca de 17 mil, não 25 mil.
    - Também incluir na triagem F0 o `SELECT count(*) FROM news_features WHERE jsonb_typeof(features) <> 'object'`, para confirmar que hoje não há linhas corrompidas pelo N1.6.

## (C) Simplificações sugeridas

1. **O gate de F2 até 25/10 deve ser só 029 + PR-4.** Com o DELETE no `persist`, só ficam as linhas da última execução, e o filtro `MAX` do PR-3 vira redundância. O PR-3 (campos de baseline, sentimento, timeline) sai do caminho crítico.

2. **Tirar do PR-3 o que está dormente.** A allowlist (N3) e a validação de `features` (N1.6) só valem quando `SERVICE_ACCOUNT_AUDIENCE` e `GRAPHQL_API_URL` voltarem. Mover para o PR-6 deixa o PR-3 menor.

3. **Adiar o PR-5 (caminho GraphQL) para depois de 25/10, junto com o PR-6.**
   - Esse código não tem efeito em produção enquanto o INF-1 valer.
   - A melhoria do script de backfill e o texto do `feature_registry.yaml` podem ir no PR-4: são `scripts/` e YAML, que não disparam deploy de worker.
   - Atenção: tocar no `pyproject.toml`, por exemplo para adicionar `graphql-core`, redeploya todos os workers.

4. **B1 sem código novo de anotações.** Fazer o script chamar `handle_feature_computation(uid, PostgresManager(), gql_client=None)` em laço. Isso reaproveita o handler: features, `content_annotations` e o pulo por hash.

5. **Tirar o índice `computed_at` da 029.** Depois do DELETE, a tabela fica com uma execução só, de centenas de linhas. Basta `ADD COLUMN` dos dois campos e o rollback.

6. **Tirar do PR-1 a mudança em `bedrock_daily_token_quota`.** O B2 roda localmente com a env. O PR-1 fica com 1 variável, 1 env e 3 remoções.

7. **Retirar `SERVICE_ACCOUNT_AUDIENCE` e o PR-6 do escopo da fase.** Basta registrar como issue, porque reabilitar o caminho GraphQL é decisão de produto (a migração "Fase I2"), não correção.
