# PLANO_FASE2_5 — gobus-mcp: fechar a Fase 2 com dados confiáveis e abrir a Fase 3

> Destino: `gobus-mcp/_plan/PLANO_FASE2_5.md`. Anexos de desenho em `gobus-mcp/_plan/fase2_5/` (ver §12).
> Escrito em 2026-10-05 (segunda-feira).
> Base: investigação read-only (workflow wf_98f5ad51-e18, 5 agentes) e desenho com verificação adversarial e crítica de integração (wf_4dd686b8-683, 7 agentes).
> Decisões do usuário: Frente 0 incluída; validação de apps em Claude Desktop, claude.ai e basic-host; nome "Fase 2.5".

## 1. Context

As Fases 1 e 2 do `_experiments/uc-2026-06-30-v3/BLUEPRINT.md` foram mergeadas em 01/07 (PRs #6 e #7). Depois de ~3 meses parado, medimos a produção. **O código existe, mas quase toda tool responde vazio, errado ou constante.** A causa principal está fora do gobus: pipelines de dados parados.

O prazo duro é **25/10/2026**, fim do defeso eleitoral (com 2º turno). A retomada de ~39 agências vai gerar baseline zero em massa nos detectores, e as correções de trending precisam estar em produção antes disso.

### Diagnóstico medido (05/10)

| # | Problema | Causa (verificada no código) | Efeito |
|---|---|---|---|
| a | Tema, resumo e sentimento zerados desde **26/09** | Chamada combinada do enriquecimento falha. Provável: modelo default `claude-3-haiku-20240307` (EOL?) em `data-science/.../worker/handler.py:76-79`, sem `ENRICHMENT_MODEL_ID` no Terraform. Com a falha, o handler **não publica `dgb.news.enriched`** | Pararam para artigos novos: feature-worker, typesense-sync em tempo real, embeddings, thumbnails, **push-notifications e federation**. `detect_trends`, `forecast` e anomalias de tema vazios |
| b | Flesch e wordCount nulos (de fato desde ~26/05; jun foi backfill) | Caminho GraphQL dos workers quebrado em camadas: `GRAPHQL_API_URL` sem `/graphql` (404), tipo `ID!` inexistente, campos `themL*`, `IsInternal` → FORBIDDEN. Dois bugs latentes corrompem dados (`json.dumps` → jsonb array; `publishedAt` str) | `score_article` sempre 5.6; legibilidade 0.0 em tudo |
| c | Sentimento sempre nulo/0 na graphql-api | Lê `features->>'sentiment_score'`; o worker grava `features.sentiment.{label,score}` (`postgres.py:326-412`) | Sem eixo de tom |
| d | `articlesTimeline` quebrado | facet `published_date` inexistente (`analytics.py:134`) | Sem série diária da plataforma |
| e | `trendingScore` por artigo 100% nulo | DAG BigQuery `compute_trending` (causa a triar) | `sort: TRENDING` inútil |
| f | Typesense atrasado (05/10: 14 contra 155) | Tempo real morto por (a) e (b); só resta o sync diário das 04 UTC | Janelas de "hoje" subestimadas |
| g | Flesch com fórmula **inglesa** | textstat 0.7.13 não tem `pt`; descrição "pt-BR" no registry está errada | Valores negativos, faixas sem sentido |
| h | `trendingEntities` com linhas de 25/06→05/10; as 50 do topo têm baseline 0 (`vr` 714–8571×) | Resolver sem filtro de execução (`postgres.py:479-486`); `persist.py` faz UPSERT sem DELETE; piso 0.001 (`signals.py:113`) | "Cobertura concentrada" só aponta artefatos |
| i | `get_readability_recommendations(agency)` **sempre falha** | `search(limit:)` não existe; `query:""` é rejeitada | Tool quebrada |
| j | `health/pipelines` mente | Flesch null→0 conta como OK; escala de `pctPositive` errada | Falsa sensação de saúde |
| k | Issue #3: o `DELETE` apagaria **4.600 notícias reais** | Só o summary é falso; o tema também é falso ("Economia e Finanças") | Risco de perda de dados |
| l | Build não reproduzível, sem CI de testes | Dockerfile `pip install .` com `fastmcp ^3.0`; lock com 2.1.2 | Regressão silenciosa |
| m | O Claude Code recebe `{"result": "<md>"}` | Wrap automático do fastmcp 3.4.2 nas tools `-> str` | Ruído para o modelo |

Contexto do defeso: volume de 205/dia para 136/dia (−34%); 15 agências com ≥10 artigos em junho zeraram (39 no total); republicadoras subiram de 27% para 35%; fim de semana pesa 4,6× menos.

### Resultado pretendido
1. Pipelines de dados restaurados, com o histórico de lacunas preenchido por backfill.
2. `trendingEntities` correto **em produção antes de 25/10**.
3. Tools que dizem a verdade: "indisponível" quando não há dado, nunca 0.0 ou nota constante.
4. Detectores cientes do defeso. A retomada pós-25/10 é o teste real.
5. As 4 MCP Apps (readability, scorecard e os 2 radares) conformes à SEP-1865 e validadas nos 3 hosts.
6. `gobus_get_message_coherence` abrindo a Fase 3.

## 2. Decisões

**Tomadas pelo usuário:** F0 dentro do plano; triagem só de leitura (`gcloud logging read --project=inspire-7-finep`); infra só via PR no `infra/`; validação de apps em Desktop, claude.ai e basic-host; nome Fase 2.5.

**Adotadas como default (recomendação da integração; o usuário pode vetar):**

| Id | Decisão |
|---|---|
| D0 | Hotfix do enriquecimento com **Haiku 4.5** via env `ENRICHMENT_MODEL_ID`. É o único compatível com o corpo Anthropic atual; o id `us.` é confirmado na triagem. O data-science#38 (Nova) entra depois, rebaseado |
| D2 | Baseline pré-defeso (06/06–03/07) no job upstream de **26/10 a 29/11**. Recuperação no gobus no mesmo intervalo (`fim + 7 + 28`) |
| D4 | Guarda de rajada: ≥2 dias distintos (upstream) mais `max_day_share ≥ 0,8` → classe `burst` (gobus) |
| D5 | Enums de payload em inglês ASCII; rótulos PT só em texto |
| D7 | Anomalias e forecast de tema usam `topThemes` + `analyticsKpis` (share-of-voice, sem sobreposição), não `trendingThemes`. Equivale à "razão verdadeira via baselineDailyAvg", sem o arredondamento e sem o N+1 de `topArticles`. `detect_trends` e `agency_summary` mantêm `trendingThemes` com o limiar convertido |
| — | Flesch: **manter a escala inglesa agora**, com clamp em [0,100] no gobus. Issue para uma futura chave `readability_flesch_ptbr` (Martins/1996) |

**A decidir durante a execução (gate com OK explícito):**
- **D1**: `log1p(vr)` e limite do `agency_growth` no scorer. Decidir após rodar `research/trend-detection/evaluate.py` offline.
- **D3**: MOCK. Re-enriquecer os 4.600 (~US$50–90) **ou** `UPDATE` anulando summary e tema. Nos dois casos, `content_embedding=NULL` e reindex.
- **D6**: re-enriquecer os 28 dias anteriores ao corte (~4k artigos) para alinhar os baselines de tema ao classificador novo.

## 3. Mapa de PRs e sequência

| PR | Repo / branch (worktree a partir de `origin/main`) | Frentes | Depende de | Alvo |
|---|---|---|---|---|
| **INF-1** | infra / `fix/fase2.5-enrichment-model-workers-pg` | F0a: var e env `ENRICHMENT_MODEL_ID`. F0b/f: remove `GRAPHQL_API_URL` dos 3 workers (voltam ao caminho PG, que funcionava) | triagem + smoke Haiku 4.5 | qua 07/10 |
| **DS-1** | data-science / `feature/fase2.5-enrichment-observabilidade` | Falha combinada visível (`enrichment_combined_failed`, `_error`), status `classification_failed`; script `reenrich_combined_window.py` (sem NER, sem publicar evento, com governador de cota). **Não muda o default do modelo** | INF-1 | sex 09/10 |
| **DP-B** | data-platform / `feature/fase2.5-trending-entities` | F2: migração **029** (só `ADD COLUMN baseline_count, baseline_agencies` + rollback), Laplace, DELETE na mesma transação, ≥2 dias, D2; melhoria do script de backfill de features (`scripts/`, sem deploy) | — | ter 13/10 |
| **GA-1** | graphql-api / `feature/fase2.5-trending-sentimento-timeline` | F2 (filtro `computed_at = MAX`, campos `baselineCount/baselineAgencies/isNew`); F0c (chave de sentimento, `pct_*` nulo sem dado); F0d (`articlesTimeline` em Postgres, BRT); regenerar SDL + teste de drift | 029 aplicada | qua 14/10 |
| **G1** | gobus / `feature/fase2.5-higiene` | F1 completo e fundações compartilhadas (calendário, payloads, readability, catálogo) | — | sex 09/10 (reserva ter 13/10) |
| **G2** | gobus / `feature/fase2.5-analytics` (empilhado sobre G1) | F3 | G1 | ter 20/10 (limite qui 22/10) |
| **G3** | gobus / `feature/fase2.5-apps-coerencia` | F4 + F5 | G2 (radares), G1 (resto) | ~qui 05/11 |
| **DP-A** | data-platform / `feature/fase2.5-graphql-workers` | Bugs latentes do caminho GraphQL (`ID!`→`String!`, `themL*`→`themeL*`, `json.dumps`, `publishedAt`, `newsBatchForBigquery`) + teste de contrato; descrição do Flesch no `feature_registry.yaml` | GA-1 (SDL) | ~03/11 (pós-defeso) |
| INF-2 | — | Religar o caminho GraphQL dos workers (allowlist de SA na graphql-api + `SERVICE_ACCOUNT_AUDIENCE`) | — | **issue**, fora da fase |

```
triagem F0 → smoke → INF-1 → DS-1 → B2 → B3 → B4
INF-1 → B1
029 → DP-B → GA-1 → (G2 refresh do snapshot SDL) → DP-A
G1 → G2 → G3(radares) ;  G1 → G3(readability, scorecard, F5)
```

**Caminhos críticos para 25/10:** upstream 029 → DP-B (o DELETE sozinho já elimina as linhas velhas); gobus G1 → G2 (a supressão de baseline zero é o plano B se F2 atrasar).

### Cronograma

| Data | Faixa principal | Paralelo (subagentes em worktrees) |
|---|---|---|
| ter 06/10 | Triagem F0 (§4). `db-migrate status`. Smoke Haiku 4.5. Mensagens aos donos de #38, #189, #184, #203 e embeddings#11 (com OK) | DP-B, GA-1 e G1 em TDD |
| qua 07/10 | Merge + apply do INF-1; verificar em 2–4 h | DS-1; G1 continua |
| qui 08/10 | B1 (`--dry-run` → `--limit 10` → completo) | PRs DS-1, DP-B e G1 abertos; G2 começa |
| sex 09/10 | Merge do DS-1 → B2 com governador (até sáb). Merge do G1 se verde | GA-1 com PR aberto |
| seg 12/10 | **Feriado: sem merge nem deploy** | G2 e funções puras do F5 |
| ter 13/10 | Aplicar 029. B3 → **B4**. Merge do DP-B ~21:05 UTC (logo após a execução das 21 UTC) | G2 rebase sobre main |
| qua 14/10 | Conferir execuções 03/09 UTC. Merge do GA-1 | G2 valida temas ao vivo (pós-B4); G3-a (infra `ui/`, mini-host, readability, scorecard) |
| **sex 16/10** | **Gate F2 em produção** (≥8 execuções boas) | PR do G2 aberto |
| ter 20/10 | Merge do G2 → checagem em produção | G3 continua |
| 21–23/10 | Observação (≥20 execuções); ensaio do D2 com SQL read-only; janela de hotfix | Radares do G3 sobre o contrato do G2 |
| **24–27/10** | **Congelamento** (só hotfix). 25/10 fim do defeso; 26/10 o D2 e a fase `recovery` ligam sozinhos | — |
| 27/10–29/11 | Checklist diário F2/F3 (sem deploy em 02/11 e 20/11) | PR do G3 ~03/11; validação nos 3 hosts; merge ~05/11; DP-A ~03/11; B5 se D3 aprovada |
| 30/11 | D2 e `recovery` desligam: conferir | Issues `readability_flesch_ptbr`, INF-2, cópias MOCK no BigQuery/HF |

## 4. F0 — Incidentes de dados (comandos completos no anexo `F0_F2-upstream.md`)

| Incidente | Triagem (read-only) | Hipótese principal | Correção |
|---|---|---|---|
| a | `gcloud logging read` no `destaquesgovbr-enrichment-worker`: erros "falhou para notícia" de 25–27/09; desfecho por dia; "Cliente Bedrock inicializado"; revisões. SQL `llm_daily_usage` e cobertura por dia. AWS `get-foundation-model` / `list-inference-profiles` / `service-quotas` (podem dar AccessDenied; o smoke é a prova direta) | H1: Haiku 3 EOL ou sem acesso. Descartar H2 (cota), H3 (deploy) e H4 (taxonomia) | INF-1 + DS-1. Smoke de 20 artigos de 15–25/09: 100% JSON válido, L1 válido, concordância ≥80% com Haiku 3 (guardar matriz por L1 → aviso `CLASSIFIER_CHANGED`) |
| b | Logs dos 3 workers (404, Unhandled error); POST 404 na graphql-api; invocações/dia; SQL de cobertura desde 15/05; `count(*) WHERE jsonb_typeof(features) <> 'object'` | Pilha N1 (URL sem `/graphql` → 404) | INF-1 (caminho PG); bugs latentes no DP-A |
| c | Já confirmado; SQL de chaves aninhada contra plana | Chave errada | GA-1 (`COALESCE` aninhada/plana; `pct_*` NULL sem rótulo) |
| d | Já confirmado | Facet inexistente | GA-1 (Postgres + `generate_series`, dias BRT, clamp 366) |
| e | Logs do Composer `compute_trending` e `sync_pg_to_bigquery`; `fato_noticias` por dia | `fato_noticias` parado / dependência (`db-dtypes`) / DAG pausado | Conforme logs. Se >1 dia de trabalho, vira issue. Prioridade baixa |
| f | `articles(startDate:hoje){found}` contra soma de `agencyAnalytics(DAY)` ao longo do dia | Consequência de a+b | INF-1 + F0a |
| g | — | Fórmula inglesa | Manter; descrição corrigida no DP-A; teste que fixa a escala; issue ptbr |

**Backfills** (todos escrevem em produção; sempre `--dry-run` → `--limit 10` → completo, cada etapa com OK do usuário):
- **B1** features: `data-platform/scripts/backfill_features_window.py --date-from 2026-05-20 --date-to <amanhã>`, com filtro corrigido para cobrir `content_annotations` (ou laço sobre `handle_feature_computation`). ~17 mil artigos, só CPU.
- **B2** re-enriquecimento: `reenrich_combined_window.py --select null-theme --date-from 2026-09-25`. ~1,6–1,9 mil artigos, Haiku 4.5. Cota = cota real da AWS com margem; fração 0,8 aplicada uma única vez. Não toca o pool do Sonnet.
- **B3** embeddings da janela com o script `embeddings/scripts/backfill_embeddings.py`. **Está untracked: preservar e versionar.** Rodar com o modelo atual, antes de qualquer bge-m3.
- **B4** `typesense-maintenance-sync` (`incremental-sync`, 2026-05-20→hoje) via `gh workflow run`, logo após B1–B3 (os temas recuperados só chegam ao gobus depois do B4).
- **B5** (D3) MOCK: anular `content_embedding`, re-enriquecer ou fazer `UPDATE`, depois `incremental-sync` 2025-09-24→2026-02-28.
- **Nunca** reenviar `dgb.news.enriched` para artigos antigos (geraria push e federation de notícias velhas). Conferir o DAG de thumbnails para 26/09→fix.

## 5. F2 — `trendingEntities` correto (DP-B + GA-1; prazo 25/10)

**DP-B (data-platform):** todo código novo vai em `jobs/trend_detection/`, porque o Composer só copia esse pacote como plugin.
- `signals.py`: `window_active_days` (dias distintos em BRT); função pura `build_entity_stats` com `laplace_volume_ratio = ((wc+1)/W)/((bc+1)/B)` (sem piso 0,001) e `is_new`; `resolve_baseline_window(date_end)` → `[2026-06-06, 2026-07-04)` se `26/10 ≤ date_end < 30/11`, senão rolante; oráculo com o mesmo vr.
- `scorer.py`: usa o `volume_ratio` do snapshot; filtra `window_active_days < 2`; D1 só depois do `evaluate.py`.
- `persist.py`: grava `baseline_*`; `executemany`; **DELETE `computed_at < NOW()` na mesma transação após o upsert**; guarda `if not entity_stats: return 0`. Commit `chore:` separado com o ruff format do arquivo.
- `dags/compute_entity_trending.py`: usa `resolve_baseline_window`; linha de log com a versão.
- **Migração 029**: `ADD COLUMN IF NOT EXISTS` dos dois campos + `029_..._rollback.sql`, sem índice, passando no sqlfluff. Aplicação: `db-migrate.yaml` com `command=status` (se 027/028 estiverem pendentes, aplicar antes, separado) → `dry_run=true target_version=029` → `dry_run=false confirm=true`.
- **Testes** (`tests/unit/`): Laplace 16 / 244 / 2,05; fronteiras do `resolve_baseline_window` (20/10, 26/10, 29/11, 30/11); burst de 1 dia; **caso Censo 57/3** documentado; DELETE na mesma transação; stats vazio não toca a tabela; baseline zero sem `ZeroDivisionError`; DAG chama o resolver; integração rollback+reapply da 029.

**GA-1 (graphql-api):** SQL com `WHERE computed_at = (SELECT MAX(computed_at) …)`; `TrendingEntityResult` + `baselineCount`, `baselineAgencies` e `isNew` (aditivos; `volumeRatio` continua não nulo para o portal). Testes nos arquivos existentes (`tests/datasources/test_trending_entities_datasource.py`, `tests/resolvers/test_trending_entities.py`, `test_postgres_bigquery.py`, `test_postgres_features.py`, `test_analytics.py`, incluindo `test_invalid_range_returns_error`). `make docs-schema` + teste de drift do SDL. A allowlist de SA e a validação de `features` saem da fase (issue INF-2).

**Portal:** sem mudança (o badge cai de ~8571× para centenas ou menos; seção vazia é escondida). Badge "novo" via `isNew` vira issue.

**Numeração com terceiros:** #189 → **030** e #184 → **031**, só depois de a 029 estar em main (`test_versions_have_no_gaps`), com rollback em minúsculas. O infra#203 (bge-m3) fica **segurado** até o 031 e o embeddings#11; nunca no mesmo apply do INF-1.

## 6. F1 — G1: higiene e correção do gobus

**Dependências, build e CI**
- `fastmcp>=3.4.2,<3.5`; atualizar `pytest ^9.1` e `pytest-asyncio ^1.4` no pyproject **antes** de `poetry lock`.
- Adicionar `tzdata`; dev-deps `ruff` e `graphql-core`.
- Dockerfile instala a partir do lock.
- Novo `.github/workflows/test.yaml` (pull_request + workflow_call + workflow_dispatch): pytest, `ruff check`, `ruff format --check`, `mkdocs build --strict` (validar local antes).
- `deploy.yaml` com `needs: ci`. Commit separado de `ruff format`.

**Fundações compartilhadas** (contratos únicos em §9)
- `cache.py`: TTL single-flight, dict + lock.
- `calendario.py`: o nome evita sombrear o `calendar` da stdlib.
- `data_status.py` e `payloads/common.py`.
- `readability.py`: clamp [0,100] na escala inglesa; tabela única de faixas 0/25/50/75; `weighted_metric` que ignora null; `last_period_with_data`; "janela efetiva".
- `agency_catalog.py`: `agencies{code isRepublisher}` + nomes via `agencyAnalytics(todas, D−1, D−1, DAY)` (~1,1 s, 156 nomes) + `topAgencies`; aliases curados (`ms→saude`, `trabalho|mte→trabalho-e-emprego`, `tcu|camara|senado|ibge` → "fora do catálogo") antes do `difflib`; `republishers()` ∪ `radioagencia_nacional`.

**server.py**
- Todas as tools com `output_schema=None` e `annotations={"readOnlyHint": True}`.
- Contêiner `Deps(client, catalog, activity)` com `get_deps()` (os testes trocam `server._deps`).

**Correções por tool/resource**
- `get_readability_recommendations`: `articles(limit, filter:{agencies}, sort:DATE)`; pior/melhor artigo escolhido no cliente; parâmetro `date_to`; janela efetiva com nota "dados até 06/2026"; sem o "~33.5" fixo; separação `build_readability_payload` / `render_readability_markdown`.
- `score_article`: status `scored | partial | refused` (sem Flesch ou wordCount → "nota indisponível", nunca 5.6); benchmark ancorado em `publishedAt−90d`, mediana da agência e da Agência Brasil, `sampleSize`, null se n<10; separação `build_score_payload` / `render`.
- `get_article`, `get_agency_analytics`, `get_agency_summary`: null≠0; faixa única de Flesch; nomes do catálogo.
- `detect_trends` e `get_agency_summary`: pedir `baselineDailyAvg`; converter o limiar do usuário r0 → g0 = B·r0/(r0·W + B − W); nunca `growthThreshold:0`.
- `get_policy_lifecycle`: agregar `entityCoverage` por mês (hoje cada mês×agência vira período); pico real; artigos da janela de pico; período formatado.
- `health_pipelines`: só `data_status` (themes, readability, sentiment, entity_ranking), escala de fração e linhas legadas por `vr/wc ≥ 100`. Atraso e atividade ficam para o G2.
- `readability_report`: guiado pelo catálogo, null-aware, mime `application/json`.
- `agencies` com nomes; queries nomeadas em `agencies.py`, `themes.py` e `platform_stats.py`; prompts só com `gobus_*` (teste).

**Testes**
- `FakeGraphQLClient.route(op_name)`.
- Teste de contrato: todas as constantes `*_QUERY` nomeadas e válidas contra o SDL obtido por introspecção (snapshot commitado em `tests/fixtures/`; variante ao vivo com marker `live`).
- `addopts = "-m 'not live and not ui'"`.
- Reescrever os testes que fixam bugs (`test_health_pipelines` escala; mocks `search` → `articles`; `test_resources.py`).
- Smoke Docker em `/mcp`, `/sse` e `/messages/`.

**Higiene do repo** (ações locais destrutivas e remotas só com OK)
- Commitar `_plan/` (rename `PLANO.md`→`PLANO_V1.md`), `_experiments/`, `docs/experimentos/` + nav. **Redigir IPs e ids de conta antes do commit; o repo é público.**
- Descartar a mudança errada de `docs/deploy.md` e reescrever: "HTTP stateless `/mcp` + compat `/sse`".
- CLAUDE.md a partir de `origin/main`: `baselineDailyAvg`, contagens, instalação de dev, seção MCP.
- `.mcp.json` do repo: `{"mcpServers":{"gobus-local": stdio .venv/bin/python3.12 -m gobus_mcp}}`.
- Tag em `7021868`, reset do `main` local, limpeza de branches remotos mergeados.
- Docs: 13 páginas em `docs/tools`, 7 em `docs/resources`, contagens.
- Reescrever a **issue #3** (sem IP; D3; embeddings; cópias no BigQuery e no HF).

## 7. F3 — G2: anomalias e forecast conforme a spec e cientes do defeso

**Módulos novos**
- `analytics/` (ratios, weekday, themes, entities, forecast, render), `domains.py`, `agency_activity.py`, `payloads/anomalies.py` e `forecast.py`.
- Funções puras com `now`/`today` injetáveis.
- Janelas de entidade fechadas em D−1 23:59 BRT; janelas de tema móveis em UTC, e o cabeçalho diz qual é qual.

**`agency_activity`:** snapshot `agencyAnalytics(156 agências, DAY)`, cache de 6 h com single-flight; período = D−90 (mais o pré-defeso só nas fases blackout/recovery). Dá `silenced`, `resumed`, `last_active` e `platform_daily`, deduplicado por `(period, agencyKey)`.

**`detect_anomalies(sensitivity, domain_filter)`**
- **Temas**
  - share-of-voice de `topThemes` + `analyticsKpis` nas janelas 3d e 7d, com Laplace;
  - gate de `classified_coverage`: abaixo do limiar, o bloco fica `unavailable` com aviso `THEMES_UNCLASSIFIED`, detectado dinamicamente, nunca por data fixa;
  - `sustained_spike` / `sustained_drop` exigem as duas janelas além do limiar.
- **Entidades**
  - candidatos de `trendingEntities(50){…computedAt}`;
  - descartar linhas legadas e de piso zero (aviso `BASELINE_ZERO_SUPPRESSED` / `TRENDING_ENTITIES_STALE`);
  - recalcular cada candidato via `entity` + `entityCoverage(DAY)` + `policyDetails` (`Semaphore(8)`, cache de 30 min).
- **Precedência das classes:**
  1. `burst` (`max_day_share ≥ 0,8`);
  2. `new_entity` (bc=0);
  3. `calendar_explained` (dona silenciada no defeso, ou ≥50% da janela vinda de agências retomadas);
  4. `coordinated_silence`: outras agências com razão ≥ limiar; dona com 0 menções ou ≤25% do normal; dona ativa no geral (≥0,5); dona com baseline ≥3;
  5. `concentrated_coverage`;
  6. `normal`.
- **Dona:** `entity.agencyKey`, senão a agência dominante em [D−90, D−8] excluindo republicadoras (share ≥0,3, ≥3 artigos).
- **`domain_filter`:** os 7 de `policies.domain` + `OTHER`. POLICY sem domínio usa o mapa da dona; valor inválido devolve as opções.
- **`severity` 0–1** + `band` (normal/watch/alert) calculados aqui; o app não reimplementa limiares.

**`forecast_trends(horizon_days, limit)`**
- Janelas 3d/7d/21d por share-of-voice e taxa log por dia.
- Composto com pesos renormalizados nas janelas presentes; momentum pela diferença de taxas (`undetermined` sem dados).
- Perfil de dia útil e feriados (12/10, 02/11, 15/11, 20/11, 25/12).
- **`horizon_days` efetivo** (1–28): projeção amortecida (φ=0,9) com intervalo de Poisson. Confiança cai um nível em `recovery`.
- Sem toggle de fim de semana: a correção fica sempre ligada.

**Calendário:** fases `normal | blackout | recovery`; avisos `ELECTORAL_BLACKOUT`, `POST_BLACKOUT_RECOVERY` e `CLASSIFIER_CHANGED` (data de corte vinda de F0a; ativo enquanto algum baseline cruzar o corte).

**Health completo:** `indexing_lag` medido no dia D e `agency_activity`.

**Saída:** as tools continuam `-> str` no G2. Os builders devolvem `AnomalyReport` / `ForecastReport`, que o G3 liga como payload. Orçamento: anomalias p50 ≤2 s com cache quente, ≤6 s a frio; forecast ≤2 s.

## 8. F4 + F5 — G3: MCP Apps e coerência de mensagem

**Infra `src/gobus_mcp/ui/`**
- `assets/_base.html`, `_tokens.css` (`var(--color-*)` com fallback, dark mode), `_bridge.js`, `_dom.js` (só `textContent`/`createElement`), `_svg.js` (barras, gauge, radar, sparkline, semáforo) e um `<app>.{js,css}` por app.
- `render_app(name)` com `lru_cache`: concatena num único `<script type="module">` e falha se houver `</script`, URL externa em `src/href/url(/import` (o namespace SVG fica liberado), `innerHTML`/`eval` ou mais de 60 KB.
- **Nenhum dado no HTML e nenhum I/O no `resources/read`.** Sem SDK ext-apps, sem Chart.js/D3.

**Bridge** (JSON-RPC raw, protocolo `2026-01-26`)
- Listeners registrados antes do `ui/initialize`.
- Handshake: `ui/initialize` → `applyHostContext` (variáveis, tema, `displayMode`) → `ui/notifications/initialized`.
- `size-changed` via `ResizeObserver`.
- Handlers: `tool-input`, `tool-result`, `tool-cancelled`, `host-context-changed`, `resource-teardown`.
- API exposta: `callTool`, `sendMessage`, `openLink` (só https), `updateModelContext`, `requestDisplayMode`, condicionadas às `hostCapabilities`.
- Sem `localStorage`.

**Binding (4 tools de app)**
- `@mcp.tool(app=AppConfig(resource_uri=URI), meta={"ui/resourceUri": URI}, annotations={"readOnlyHint": True}) -> ToolResult`.
- Retorno: `ToolResult(content=markdown, structured_content=payload.model_dump(mode="json", by_alias=True))`; o `summary` (= markdown, ≤6 KB) é o primeiro campo, porque é o que o Claude Code mostra.
- Resources: `@mcp.resource(URI, app=AppConfig(prefers_border=True))` → `render_app(...)`.
- O `resources/readability_dashboard.py` antigo é removido (incluindo o `Chart` falso e o teste que o exige).
- CLAUDE.md ganha a exceção "tools de app = summary + payload".

| App (URI) | Tool | Card inline | Fullscreen e interações |
|---|---|---|---|
| `ui://readability-dashboard` | `gobus_get_readability_recommendations` | top-8 barras com faixa-alvo, chip de cobertura | ranking; detalhe da agência via `tools/call`; botão "último período com dados" (`date_to`) |
| `ui://article-scorecard` | `gobus_score_article(unique_id, compare_with)` | nota + 3 semáforos (ícone e texto) contra mediana/AB | lado a lado de 2 artigos; `ui/message` "reescreva"; estados `refused`/`partial` |
| `ui://anomaly-radar` | `gobus_detect_anomalies` | 8 gauges por domínio (pico/silêncio), chips de defeso e de temas | lista com toggle local; sensibilidade e domínio via `tools/call`; "investigar" via `ui/message` |
| `ui://forecast-radar` | `gobus_forecast_trends` | radar log2 com anel 1× e top-3 com momentum | razões por janela; horizonte 7/14/21/28 via `tools/call` |

Comum a todos: estados `ok | partial | empty | unavailable` com "—"; versão incompatível detectada; tabela equivalente em `<details>`; mínimo de 320 px; claro e escuro. Orçamento: HTML ≤60 KB (meta 25), payload ≤20 KB (meta 10).

**Tools de preview dev** (`gobus_dev_preview_*` com fixtures marcadas "DEV — dados fictícios") só são registradas com `GOBUS_DEV_PREVIEW=1`. Servem para validar render enquanto F0 não repõe os dados.

**Testes de F4**
- `tests/test_ui/`: `render_app`, guards, tamanho.
- `tests/test_server/test_apps_wire.py` via `fastmcp.Client` em memória: `meta.ui.resourceUri` igual ao legado; MIME `text/html;profile=mcp-app`; 0 GraphQL no `resources/read`; payload valida e ≤20 KB.
- `tests/browser/` (Playwright `async_api`, marker `ui`): mini-host com iframe sandbox + CSP da spec; ordem do handshake; `size-changed` 100–2000 px; 0 erros de console e de CSP; fixture XSS sem `dialog`; claro/escuro × 320/760.
- TDD: mini-host e fixtures logo após o commit de infra.
- CI: jobs `ui` e `apps-conformance` (`npx @mcpjam/cli apps conformance --url http://localhost:8000/mcp`, servidor com `PORT=8000`). Alvos no Makefile existente (uma linha com `$$!`, `until curl` e `trap`).

**Validação manual (checklist e screenshots no PR)**
1. **basic-host**: clone de `modelcontextprotocol/ext-apps`, `SERVERS='["http://localhost:8000/mcp"]' npm start`. Conferir comando e versão no clone.
2. **Claude Desktop (stdio)**: `claude_desktop_config.json` → `.venv/bin/python3.12 -m gobus_mcp` com `GOBUS_GRAPHQL_URL`; devtools com Cmd+Opt+I.
3. **claude.ai**: antes do merge, custom connector via túnel `cloudflared` para o `/mcp` local; depois do deploy, no Cloud Run `/mcp` (público, `allUsers`), com rollback por revert.

O Claude Code não renderiza apps; ali só se verifica que o `summary` chega.

**F5: `gobus_get_message_coherence(entity_id | theme, agencies, date_from, date_to) -> str`**
- **Entradas:** exatamente um entre `entity_id` e `theme`. Entidade resolvida por `entitySearch(limit:3)`, escolhendo o maior volume e listando as alternativas. Padrão: D−14..D−1 BRT; máximo de 92 dias.
- **Dados**
  - `articles(limit:250, page, filter:{entityCanonical | themeLabel, agencies, startDate/endDate com -03:00}){…features{entities{canonicalId type salience}}}`; páginas 2–4 em gather (teto de 1000, aviso `SAMPLE_TRUNCATED`);
  - tom por aliases de contagem `articles(limit:1, filter:{…, agencies:[a], sentiment:[l]}){found}`;
  - prior via `entityCoverage(DAY)`.
- **Índice 1–5** = média renormalizada das dimensões disponíveis:

  | Dimensão | Peso | Cálculo |
  |---|---|---|
  | E, entidades | 0,35 | cosseno salience×idf, excluindo a própria entidade e as `dgb_{code}` do catálogo |
  | T, timing BRT | 0,25 | 1º artigo em até 48 h + Jaccard de dias |
  | F, enquadramento | 0,25 | léxico anúncio/resultado/desafio/serviço/agenda; 1−JSD; ignora summary `[MOCK]` |
  | S, tom | 0,15 | 1−JSD; só com cobertura ≥50% |

  Cortes provisórios; calibração (sanity check, não gabarito) em `_experiments/coherence-calibration-2026-10/` com UC-03, Q575545 e `dgb_pe-de-meia`.
- **Saída:** republicadoras sempre em seção separada; aviso de tema dinâmico.
- **Fora desta fase:** `CoherenceReport` (payload) já existe, mas o app `ui://coherence-matrix` fica para depois.
- **Testes:** funções puras (cosseno, idf, JSD, léxico, virada de dia BRT, `insufficient`) e tool (roteamento por operação, paginação `found=600`, erros).

## 9. Contratos compartilhados (versão única)

- **Pydantic:** campos snake_case + `ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True, extra="forbid")`. Null sai como `null`.
- **`ReportBase`:** `schema_version=1, kind, tool, summary, status, generated_at, reference_date, params, calendar: CalendarContext, data_status[], notices[]`.
  - Campo opcional novo mantém a versão; remover ou renomear sobe a versão; a URI `ui://` nunca muda.
- **Status:** dado = `ok | degraded | unavailable`; relatório = `ok | partial | empty | unavailable`.
- **`NoticeCode`:** `THEMES_UNCLASSIFIED`, `SENTIMENT_UNAVAILABLE`, `READABILITY_UNAVAILABLE`, `TRENDING_ENTITIES_STALE`, `BASELINE_ZERO_SUPPRESSED`, `CLASSIFIER_CHANGED`, `ELECTORAL_BLACKOUT`, `POST_BLACKOUT_RECOVERY`, `INDEXING_LAG`, `SAMPLE_TRUNCATED`.
  - Detecção sempre dinâmica; data fixa só como dica de `since`, nunca no JS.
- **Calendário (os dois repos fixam as mesmas datas nos testes):** defeso 2026-07-04..2026-10-25; recuperação até 2026-11-29; D2 desliga em 30/11.
- **`AnomalyReport`:** blocos `themes` (`ThemeSignal`), `entities` (`EntitySignal` com `owner`, `silence_score`, `daily[≤28]`, `owner_daily[≤28]`) e `domains[8]` em ordem fixa. `ForecastReport`: `windows{3d,7d,21d}`, `platform`, `themes[]` com `projection`. A série diária de tema fica `null` na v1. Detalhe no anexo `integration.md` §1.4–1.5.
- **Contratos upstream → gobus:** `volumeRatio` não nulo; `baselineCount/isNew` aditivos (o G2 não depende deles); `pctPositive` pode vir null depois do GA-1.

## 10. Regras de execução

- **Orquestração (ultracode):** cada PR é implementado por subagentes em **worktree** (`<repo>/.claude/worktrees/fase2.5-<tema>`) com TDD (`test: … (red)` → `feature:/fix: … (green)`). Antes de abrir o PR, revisão adversarial (`/code-review` ou workflow de review). A thread principal só orquestra.
  - Nunca trocar o branch do checkout principal dos outros repos.
  - Testes com `PYTHONPATH=<worktree>/src` (os installs editáveis apontam para o checkout principal).
  - Validar o G2/G3 por uma entrada stdio separada (`gobus-g2`).
- **Ações que exigem OK explícito do usuário:** merges, `gh workflow run`, comentários e edição de PR/issue, `git push --delete`, descarte de mudanças locais, leitura de secrets (PG, AWS, embeddings), cada etapa de backfill, SQL (sempre `BEGIN READ ONLY … ROLLBACK`).
- **Proibido:** terraform local, gcloud mutante, DELETE de notícias, reenviar eventos antigos, **sondas com mutation** (houve um incidente nesta investigação, ver §13).
- **pre-commit** no data-platform e no scraper: rodar `.venv/bin/pre-commit run --files <alterados>`.
- **Convenção de commit por repo:**

  | Repo | Atribuição ao Claude | Mensagens |
  |---|---|---|
  | gobus-mcp | **sem Co-Authored-By** (CLAUDE.md) | português, prefixos `fix:`, `feature:`, `refactor:`, `chore:`, `test:`, `docs:` |
  | graphql-api | sem (CLAUDE.md:175) | idem |
  | infra | sem (infra/CLAUDE.md) | — |
  | data-platform, data-science | aceita `Co-authored-by` | — |

- **Hosts:** o `~/.claude.json` do usuário ainda aponta o "gobus" para `/sse`. Ajuste manual do usuário; nenhum agente edita esse arquivo.

## 11. Verificação e critérios de aceite

- **F0**
  - **a:** smoke aprovado; 24 h após INF-1, `enriched` ≥95%; 7 dias sem `enrichment_combined_failed`; após B2+B4, tema/resumo/sentimento ≥95% em todo dia desde 25/09; `analyticsKpis(7d).activeThemes ≥ 15`.
  - **b:** Flesch ≥95%/dia de 20/05 até hoje; artigo novo com `word_count` em ≤15 min; `jsonb_typeof <> 'object'` = 0.
  - **c:** `pctPositive` em [0,1], com diferença ≤5 p.p. contra o Typesense.
  - **d:** `articlesTimeline(14d)` com 14 pontos e soma igual ao Postgres por dia BRT (±2%).
  - **e:** causa documentada (corrigida ou issue).
  - **f:** Typesense ≥98% do Postgres em ≤30 min.
- **F2 (gate 16/10)**
  - `count(DISTINCT computed_at) = 1`; idade de `max(computedAt)` ≤13 h; 0 linhas no padrão do piso antigo; `max(vr) < 300` (esperado); `baseline_count` 100% não nulo;
  - fração de `isNew` no top-50 registrada por dia; log de versão presente; portal `/noticias` recente.
- **F1**
  - `readability_recommendations("saude")` sem erro; `("trabalho")` sugere `trabalho-e-emprego`; `("ms")` sugere `saude`;
  - contrato 100% verde; `tools/list` com 13 tools sem `outputSchema` e com `readOnlyHint`; nenhum "0.0" vindo de null;
  - `score_article` sem "5.6" (recusa ou nota com `sampleSize ≥10`, testado ao vivo antes e depois do B1);
  - `poetry check --lock` OK; imagem a partir do lock; `test.yaml` verde; smoke Docker nas 3 rotas.
- **F3**
  - testes de fase em 03/07, 04/07, 25/10, 26/10, 29/11 e 30/11, com feriados;
  - fixture de 05/10 sem "8571"; temas `unavailable` com `since` 26/09;
  - 0 sinais com bc=0 em silêncio ou concentrada; `burst` com `max_day_share ≥ 0,8`;
  - `horizon_days` 7 e 21 dão saídas diferentes; latências dentro do orçamento;
  - cenário `now=2026-10-30` → `calendar_explained`; `POST_BLACKOUT_RECOVERY` ao vivo em 27/10 e 03/11.
- **F4**
  - MCPJam 7/7 (local, CI, produção); testes de wire; Playwright em todas as fixtures × temas × larguras;
  - orçamentos respeitados; render confirmado em basic-host, Desktop e claude.ai (screenshots); o Claude Code recebe o `summary`.
- **F5**
  - `Q575545` em ago–set em ≤3 s, saída ≤5 KB, índice 1–5 com tabela de dimensões;
  - republicadoras separadas; `[MOCK]` ignorado; virada de dia BRT testada; tom só com cobertura ≥50%.

## 12. Anexos e passo 0 após aprovação

**Passo 0:** gravar este plano em `gobus-mcp/_plan/PLANO_FASE2_5.md` e os anexos em `gobus-mcp/_plan/fase2_5/`, **redigindo IPs e ids de conta**. Eles entram no commit de higiene do G1.

| Anexo | Conteúdo |
|---|---|
| `investigacao/{gobus-internals,upstream-data,live-probe,mcp-apps-spec,critic}.md` | Base factual de 05/10 |
| `desenho/F0_F2-upstream.md` (+ `verificacao`) | Comandos de triagem, arquivos e testes por PR upstream |
| `desenho/F1_F3-gobus-core.md` (+ `verificacao`) | Assinaturas dos módulos e algoritmos |
| `desenho/F4_F5-apps-coherence.md` (+ `verificacao`) | Contratos dos apps, bridge, testes, F5 |
| `desenho/integration.md` | Contratos únicos, cronograma, terceiros, correções consolidadas (prevalece sobre os rascunhos) |

## 13. Riscos e incidentes

- **Incidente do processo (05/10):** um agente de desenho enviou a mutation `upsertFeatures(uniqueId:"__nao_existe__")` à API de produção. Ela foi recusada com `FORBIDDEN` e nada foi gravado. Daqui em diante, só queries.
- **data-science#38 colide com o DS-1:** mesmos 4 arquivos e mesmo default; depende das colunas do #189. O DS-1 entra primeiro, o #38 faz rebase e só entra com a 030 aplicada e o corpo da requisição Nova corrigido.
- **Troca de classificador cria degraus** nas séries de tema até ~30/10 (7/28) e meados de janeiro (21/84). Mitigado com `CLASSIFIER_CHANGED` e, opcionalmente, D6.
- **infra#203 aplicado com os eventos religados** gravaria vetores de 1024d em coluna de 768d. Segurar.
- **Fastmcp 3.5+ ou o lock novo podem quebrar** a API privada do `/sse` (`server.py:50,57`). Mitigado com pin `<3.5` e smoke das 3 rotas.
- **Endpoint gobus público sem auth:** custo e abuso a acompanhar (fora do escopo).
- **Dados indisponíveis até o B4** (~13/10): apps e tools mostram `unavailable`; o render é validado com as tools de preview.
- **Itens a conferir no clone:** comando do basic-host e flags do MCPJam (`--reporter`, versão do Node).

## 14. Registro de execução

### 2026-10-05 (noite): dia 1, triagem e smoke

- **F0a: H1 confirmada.** O Claude 3 Haiku tem EOL no Bedrock em 10/09/2026, segundo a página legacy da AWS. A primeira falha apareceu em 2026-09-25T17:32Z: `ResourceNotFoundException: This model version has reached the end of its life`. O último `enriched` foi em 26/09 00:30Z. Há revisão única (00018-df4) e não existe `ENRICHMENT_MODEL_ID`.
- **D0 confirmado:** `us.anthropic.claude-haiku-4-5-20251001-v1:0`. Smoke com 20 artigos: JSON 100%, L1 válido 100%, concordância de L1 80% (no limite; L2 65%, L3 50%), sentimento mais neutro, 18,9k tokens de entrada e 301 de saída por artigo, ~US$0,022 por artigo (~US$4/dia ao vivo, ~US$37 no B2). O corpo atual do `_call_bedrock` é compatível: **o INF-1 só precisa da env**. As respostas vêm em cercas ```json, que o `_parse_response` já tolera.
- **NOVO: o NER (Sonnet 4.6) roda ~12× mais desde 26/09.** O scraper reemite `scraped` ~22×/artigo. A idempotência do enriquecimento dependia do tema gravado; sem tema, toda reemissão roda a chamada combinada (falha) e depois o NER (sucesso). O ledger mostra o Sonnet saindo de ~5,4M/1,1M tokens/dia para 8–10M/2,5–3M; `Stored raw LLM response` foi de ~250 para 2–3 mil por dia. O INF-1 corrige isso, porque o tema volta a ser gravado. **Ajuste no DS-1:** em falha combinada, NÃO rodar o NER se o artigo já tiver entidades (o desenho anterior mantinha o NER e preservaria a amplificação).
- **F0b: N1 confirmada.** 44,6 mil POST 404 na raiz da graphql-api desde 20/09 (bronze 3,3k/dia, feature e typesense ~200–400/dia). Os workers fazem ACK silencioso. `features` está 100% como objeto jsonb (sem corrupção N1.6) e o sentimento só aparece na chave aninhada.
- **F0e: causa nova.** O `compute_trending` sempre devolve `no_data`, porque o `sync_pg_to_bigquery.sync_facts` falha há ≥30 dias com `Parquet column 'has_image' has type INT32 which does not match BOOL`. A coluna inteira é NULL, já que não há features desde ~26/05. O `dgb_gold` inteiro está parado. **Ação:** depois do B1, re-rodar `sync_pg_to_bigquery` na janela (OK do usuário); hardening de dtype no `write_to_parquet_gcs` entra no DP-A.
- **F0f confirmada:** em 05/10, o Typesense tinha 4 artigos contra 171 no Postgres. O `main-workflow` roda entre 09:42 e 11:14Z, não às 04:00Z.
- **NOVO (urgente): o clipping usa Claude Sonnet 4 (`us.anthropic.claude-sonnet-4-20250514-v1:0`), que tem EOL em 14/10/2026** e está em public extended access (preço maior) desde 14/07. Entra no INF-1 a env `BEDROCK_MODEL_ID = var.clipping_model_id` (Sonnet 4.6), pendente de smoke.
- **Migrações em produção:** 027 e 028 aplicadas em 05/10, então a 029 está livre.
- **Riscos de longo prazo:** o EOL do Haiku 4.5 não acontece antes de ~abr/2027 e o do Opus 4.1 é em 08/01/2027 (não usado). O DS-1 deve alertar sobre `ResourceNotFoundException` e `update_failed`; o EOL do Haiku 3 levou 15 dias para ser notado.
- **INF-1 pronto localmente** (`infra` / `fix/fase2.5-enrichment-model-workers-pg`, commit `fddba40`, `terraform fmt` ok):
  - `var.enrichment_model_id` + env `ENRICHMENT_MODEL_ID` no enrichment-worker;
  - remoção de `GRAPHQL_API_URL` nos 3 workers, que voltam ao caminho PG (confirmado no código: sem a env, o `_gql_client` fica `None`).
- **CL-1 (novo, clipping)** (`clipping` / `fix/fase2.5-digest-json-cercas`, 4 commits TDD, 188 testes verdes):
  - `parse_digest_json` tolera cercas markdown;
  - default `bedrock_model_id` passa a `us.anthropic.claude-sonnet-4-6`.
  - Smoke: no Sonnet 4.6 o agente (Converse + tools) funciona sem mudança; o consolidador só precisava da tolerância a cercas.
  - O merge em `main` faz deploy automático e precisa acontecer **antes de 14/10**. Com o default trocado no código, o INF-1b (env no Terraform) é dispensável.
- Ambiente local: o `pip` da máquina aponta para um índice privado. Nos venvs do DGB usar `PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple`. O Poetry segue quebrado (`python` não encontrado), então usar `pip install -e .` direto.
- **Amplificação do NER: causa refinada.** ~98% vem do scraper republicando `scraped` a cada re-scrape que casa por URL (scraper#36, ef94497, 27/04, `postgres_manager.py:283`), a cada ~10 min, das 10h às 23h50 UTC. Em 01/10 foram 3.075 processamentos para 243 artigos; só 1,4% eram reentregas por NACK. O `worker/app.py` sempre responde 200. Requests de 30–70 s derrubaram instâncias (503 por liveness, 429 sem instância).
  - Custo extra estimado: **~US$33–46/dia de Sonnet 4.6, ~US$265–370 de 28/09 a 05/10**.
  - O INF-1 estanca o custo: com o tema gravado, a idempotência volta a devolver `skipped`.
  - **Novo item (issue no scraper, fora da fase):** publicar `scraped` em update só quando o `content_hash` mudar. O bronze-writer também recebe ~13× mais eventos por isso.
  - **DS-1:** NER no máximo uma vez por uid (checar `features ? 'entities'` antes do `extract_entities`); métrica de log de `update_failed` e de NER por uid.
  - **DLQ** `dgb.news.scraped--enrichment-dlq`: pode ter recebido mensagens dos 503. Não reprocessar sem filtro.
- **INF-1 MERGEADO e APLICADO** (infra#215, 2026-10-06 00:19 UTC): `Apply complete! 0 added, 15 changed, 2 destroyed`.
  - Por decisão do usuário, removido o acesso de <e-mail> do `terraform.auto.tfvars` (VM e IAM já tinham sido apagados fora do Terraform). Destruídos o disco `<disco da devvm>` (100 GB, desanexado desde 16/07) e a policy de auto-shutdown.
  - Drift explicado no PR: `client`/`client_version`, `CACHE_BUST` do portal, scaling do gobus/MLflow, descrição da SA.
- **CL-1 aberto:** clipping#25, CI verde, aguardando OK de merge (prazo: EOL do Sonnet 4 em 14/10).
- **Comentários postados** em data-science#38, data-platform#189/#184, infra#203 e embeddings#11.
- **GA-1:** sentimento só existe na chave aninhada (39.547 contra 0), então o fallback plano no `COALESCE` é opcional.
- **CL-1 MERGEADO** (clipping#25, 2026-10-06 00:37Z; deploy run 37395019889 com sucesso; revisão `destaquesgovbr-clipping-00108-8xg` pronta, sem erros). O clipping está fora do Sonnet 4 antes do EOL de 14/10. Conferir no próximo disparo (a cada 30 min) que o digest sai estruturado.

### 2026-10-06 (madrugada): PRs, 029 e B1
- **PRs abertos, todos com CI verde:**
  - data-platform#202 (DP-B, 19 commits);
  - graphql-api#28 (GA-1, 13 commits; a revisão pegou que o asyncpg entrega o JSONB como str, então o fix de sentimento nos mapeadores não funcionaria; já corrigido);
  - gobus-mcp#8 (G1, 69 commits, 407 testes, smoke Docker em `/mcp`, `/sse` e `/messages/`; a revisão pegou o `dateTo` exclusivo do `agencyAnalytics` MONTH/WEEK, já corrigido com helpers no `calendario`).
- **Migração 029 APLICADA** em produção (01:06Z, `db-migrate` a partir do branch do DP-B; `dry_run` antes; backup automático). As colunas `baseline_count` e `baseline_agencies` existem.
- **B1 em execução:** 20.482 artigos na janela [20/05, 07/10) (14.864 sem Flesch, 20.293 sem `content_annotations`). Teste com `--limit 10` ok: 3 s, chaves preservadas, jsonb continua objeto. Ritmo de ~0,3 s/artigo, ~1h40 no total.
- **DS-1 e G2** em implementação local (workflow com revisão e correção).
- **MERGEADOS E EM PRODUÇÃO (06/10, ~01:13–01:35Z):**
  - **data-platform#202 (DP-B):** os plugins do Composer foram deployados; a próxima execução às 03Z já roda o trending v2.
  - **graphql-api#28 (GA-1):** `trendingEntities` com um único `computedAt`; `articlesTimeline` ok.
  - **gobus-mcp#8 (G1):** 13 tools sem `outputSchema` e `readOnlyHint`; o health mostra temas `unavailable` desde 26/09 (6% em 7 dias) e legibilidade `ok`.
- **Regressão do GA-1 em produção, corrigida pelo hotfix graphql-api#29** (merge e deploy às ~01:35Z).
  - Causa: o `Float` do graphql-core 3.3 (instalado na imagem, que não tem lock) rejeita o `Decimal` do asyncpg em `pctPositive` e `avgWordCount`. O venv local tinha a 3.2.8, que aceita.
  - Correção: `_as_float()` no resolver. TDD reproduzido num venv com as deps mais recentes.
  - Verificado ao vivo: sem erros; set/2026 com sentimento, Flesch e `word_count`.
  - **Follow-up:** lockfile ou faixa fixa de versão na graphql-api, para que o CI teste o mesmo que vai para produção.
- **G2 está empilhado no G1, que foi mergeado por squash.** Antes do PR: `git rebase --onto origin/main feature/fase2.5-higiene feature/fase2.5-analytics`.
- **B1 CONCLUÍDO** (06/10, ~02:32Z): 20.472 artigos processados, 0 falhas, 133 sem Flesch (menos de 10 palavras), 83 min.
  - Aceite: 139 dias desde 20/05 com `word_count` e `content_annotations` em 100%; Flesch com mínimo de 94,5% (1 dia abaixo de 95%, por textos curtos).
- **BigQuery `fato_noticias`:** tem dados só até 27/05, mais 28/05 (4 linhas), 29/06 (192) e 30/06 (2). O `sync_facts` é diário, sem catchup, processa só o dia anterior e faz load `WRITE_APPEND` (sem dedup).
  - **Sync diário:** deve voltar sozinho às 07:00Z (o dia anterior agora tem `has_image`), e com ele o `compute_trending`.
  - **Histórico (28/05→04/10):** reprocessar DEPOIS do B2, para entrar com tema e sentimento. Antes, `DELETE` no BigQuery das linhas parciais de 28/05, 29/06 e 30/06 (pedir OK); depois, `dags trigger -e <data>` por dia, com `max_active_runs=1`.
  - Hardening de dtype no `write_to_parquet_gcs` (coluna toda nula vira INT32) continua no DP-A.
- **DS-1 e G2 implementados e revisados** (workflow wf_ff8d5fb7-b90). Revisões aprovaram; os should_fix foram corrigidos.
  - **data-science#43 (DS-1):** 12 commits, 347 testes. A guarda do NER (uma vez por uid) vale nos dois caminhos e usa `news_llm_raw` além de `features ? 'entities'`. Logs estáveis: `enrichment_combined_failed`, `enrichment_model_unavailable` (CRITICAL), `enrichment_update_failed` e `enrichment_ner status=…`.
  - **gobus-mcp#9 (G2):** 62 commits, 718 testes, rebase sobre `main` depois do squash do G1; snapshot do SDL atualizado. Correções da revisão:
    - "retomada" conta só quem volta depois do fim do defeso;
    - baseline pequeno fica limitado a "atenção";
    - `burst` e `new_entity` nunca passam de "atenção";
    - `entityCoverage` soma em vez de deduplicar.
  - Questões abertas:
    - dona por cobertura dentro do defeso (estender o período da dona ao pré-defeso nas fases blackout/recovery?);
    - teto de sinais no payload: com 30 candidatos deu 19,7 KB e o summary saiu truncado (o G3 deve reduzir);
    - `agencyKey` errado no registry (PGF → Fundação Joaquim Nabuco).
- **B2 em execução** (06/10 02:35Z, a partir do branch do DS-1):
  - `--limit 10` ok (37 s; tema, resumo e sentimento gravados, entidades preservadas). Lotes de 500, 2 workers, ~2,3 s/artigo, mais recentes primeiro.
  - Governador com cota de 12M e fração 0,8 (9,6M/dia, incluindo o worker ao vivo). A cota diária real do Haiku 4.5 é desconhecida (servicequotas AccessDenied); o loop para no primeiro throttling.
  - Previsão: ~400 artigos/dia, término em ~3–4 dias UTC.
- **Ledger confirma o fim da amplificação:** o Sonnet caiu de 8,7M (05/10) para 0,3M em 06/10 até 02:40Z.
- **Gate F2 ATINGIDO** (06/10 03:01Z, primeira execução do trending v2 em produção):
  - 1 execução, 32 linhas;
  - `max(volume_ratio)` foi de **8571 para 24**;
  - `baseline_count` 100% não nulo;
  - linha de log `trend_detection v2 (laplace, snapshot): date_end=2026-10-06 baseline=[2026-09-01, 2026-09-29)`.
  - O topo ainda tem 15 de 32 entidades com bc=0 (caso da D1). O G2 as classifica como `new_entity` (≤ atenção).
- **B2, dia 1:** 435 artigos re-enriquecidos (do mais recente para trás: 01/10 parcial a 04/10), depois o governador parou em 9,6M. Retoma no próximo dia UTC.
- **Mergeados e deployados (~09:55Z):** data-science#43 (DS-1, enrichment-worker revisão 00020-289) e gobus-mcp#9 (G2).
  - G2 ao vivo: avisos de defeso e de troca de classificador presentes, nenhum "8571", baseline pequeno limitado a "atenção".
- **B4 parcial** (10:02Z, `incremental-sync` 20/05→06/10): 22.834 indexados, 0 erros. `activeThemes` (7d) passou de 0 para 22. Repetir o B4 completo no fim do B2.
- **NOVO, achado durante o B3: ~35% dos artigos têm tema e não têm resumo desde junho/2026** (jun 1.742, jul 1.552, ago 1.620, set 1.369, out 59 até agora).
  - Continua no caminho ao vivo com o Haiku 4.5: `especial-chica-xavier_814659` saiu `enriched` às 00:30Z com summary NULL.
  - O caminho do script do B2 grava resumo em 100%.
  - Esses artigos também não têm `content_embedding`, logo ficam fora da busca semântica.
  - **B3 segurado** até sair a causa raiz (agente `rca-resumo` investigando): gerar embedding sem resumo agora impediria regerar depois.
- **Causa raiz dos resumos apagados** (agente `rca-resumo`, 06/10 ~10:05Z): o **re-scrape do scraper** apaga.
  - `scraper/.../storage/postgres_manager.py`, `_update_existing_articles` (Phase 1, casamento por agency+url) faz `summary = v.summary` (sempre NULL) e `content_embedding = NULL` incondicional.
  - Passou a valer em **02/06** com o `d406fee` (01/06), que consertou os casts do UPDATE.
  - Escala: **6.935 artigos** (tema + sem resumo + sem embedding), em 7 agências; agencia_brasil e tvbrasil ~95%.
  - É o mesmo caminho que republica `scraped` (~13×/dia por artigo).
  - Os 445 artigos do B2 de hoje estão seguros (fora da janela de re-scrape de ~16 h).
  - **Nova ordem:** SC-1 (scraper) → DS-2 (backfill só de resumo com prompt enxuto, ~2k tokens/artigo em vez de 19k, ~US$20) → B3 (embeddings, que dependem do resumo) → B4 completo.
  - SC-1 e DS-2 em implementação local (workflow `wf_6f104f1c-ee7`).
- O alerta de "scraper parado" foi falso: as DAGs de scrape rodam de dia (~10–24h UTC). Nenhum erro de import depois do deploy do DP-B.
- **SC-1 e DS-2 mergeados e deployados** (06/10 ~11:58Z):
  - **scraper#64:** re-scrape preserva `summary`, temas, `image_url` e embedding; republica só se o conteúdo mudou ou o artigo ainda não tem tema; CI com Postgres real. Miguel marcado como revisor pós-merge.
  - **data-science#44:** `--select null-summary` com prompt enxuto.
  - Verificado: a revisão `scraper-api-00045` grava normalmente (6 inserções e 17 atualizações, sem erro de SQL); a contagem "tema sem resumo" de hoje parou de subir.
  - Os 500 em `/scrape/agencies` já existiam (11,6% na revisão anterior) e vêm de falhas da API gov.br.
- **DS-2:**
  - `dry-run`: 6.342 artigos (jun→05/10), 0 antes de junho, `com_embedding=0` (o passo 4 do runbook não é necessário), `sem_sentimento=0`.
  - `--limit 10`: 10 ok em 24 s, resumos com boa qualidade.
- **Decisão do usuário:** governador sobe para cota 20M × 0,8 = **16M/dia** (havia 9,78M/dia sem throttling); prioridade é DS-2, depois B2.
- **Executor desacoplado** (`scratchpad/backfill_runner.sh`, iniciado às 12:42Z):
  - Sequência: DS-2 principal → passada final de D+1 (06/10, liberada a partir de 07/10 BRT) → B2.
  - Espera o próximo dia UTC quando o orçamento acaba; para no primeiro throttling ou em passada sem `ok`.
  - Estado em `backfill_runner.state`, log em `backfill_runner.log`.
- **Depois do executor:** trava (`dry-run` com 0) → B3 (embeddings, `--end-date 2026-10-07`) → B4 completo → histórico do BigQuery (com OK para o DELETE das linhas parciais).
- **Issues abertas** (06/10):
  - infra#216: métricas de log e alert policies para falhas silenciosas (enriquecimento, workers, DAGs);
  - data-platform#203: `readability_flesch_ptbr` (Martins/1996);
  - graphql-api#30: lockfile/pin de dependências (incidente Decimal/graphql-core 3.3).
- **G3 e DP-A em implementação local** (workflow `wf_39a7612c-7f1`):
  - G3 em 3 etapas: infra `ui/` + readability/scorecard, depois radares + preview dev + conformance, depois coerência F5;
  - DP-A: caminho GraphQL latente, contrato, dtype do parquet do BigQuery, COALESCE no `allow_update` do `PostgresManager`, descrição do Flesch.
- **G3 pronto — gobus-mcp#10 (aberto, sem merge):**
  - 39 commits; 968 testes, mais 197 de navegador (mini-host Playwright).
  - 4 MCP Apps (readability, scorecard, anomaly-radar, forecast-radar), previews dev só com `GOBUS_DEV_PREVIEW=1`, MCPJam conformance no CI, validado no basic-host (ext-apps 2.0.3).
  - `gobus_get_message_coherence` (14ª tool) com `INDEXING_LAG`, porque o Typesense não tem `entityCanonical` antes de ~20/05.
  - Calibração por tema não reproduz o UC-03 (E≈0,03–0,07); pesos e cortes seguem provisórios.
  - **Falta a validação visual do usuário** no Claude Desktop e no claude.ai antes do merge (roteiro em `docs/apps/desenvolvimento.md`).
- **DP-A pronto — data-platform#204 (aberto; merge só depois de 27/10):**
  - 12 commits, 1.026 testes.
  - A revisão pegou o `newsById` devolvendo `features` como string JSON (o merge `||` corromperia o jsonb); corrigido.
  - Escopo de deploy: 4 workers, mais `composer-deploy-dags`, mais `postgres-docker-build`.
- **Issues novas:**
  - graphql-api#31: `newsBatchForBigquery` (datas str no asyncpg; bloqueia o INF-2);
  - data-platform#205: teste de integração do BigQuery roda DDL em produção com ADC;
  - data-platform#206: reindex do `entity_canonical` no Typesense para o acervo anterior a ~20/05.
- **Restrição temporária do usuário (06/10):** nada que dependa de autenticação no gcloud por enquanto.
  - Em espera: SQL de verificação, leitura de logs, B3 (secrets de embeddings), histórico do BigQuery.
  - O executor dos backfills segue rodando com as credenciais carregadas no início.
- **DS-2 CONCLUÍDO** (06/10 14:12Z): **6.332 resumos recuperados**, 0 falhas, ~950 tokens/artigo (~6M tokens). De junho a agosto não sobrou nenhum artigo com tema e sem resumo.
  - Restam ~160 artigos de jun–ago e ~102 de 05/10 **sem tema** (falhas antigas e 05/10 antes do INF-1). O B2 foi ampliado para [2026-06-01, 2026-10-07) e o executor foi reiniciado às 18:24Z; retoma às 03Z de 07/10 (passada D+1 → B2).
  - Haiku em 06/10: 16,5M tokens sem throttling.
- **B3 iniciado** (06/10 ~15:27Z):
  - A embeddings-api agora exige **IAM do Cloud Run** (403 sem identity token).
  - Script versionado e corrigido em embeddings#13: `--require-summary` e identity token via gcloud com cache.
  - Janela [2026-03-01, 2026-10-06) com `--require-summary`: 6.807 artigos. Teste com `--limit 10` ok (768 dimensões).
- **B3 CONCLUÍDO** (06/10 15:38Z): **6.797 embeddings**, 0 erros, 11 min (~10 artigos/s, 3 workers). Em [01/03, 06/10) não sobra artigo com resumo e sem embedding. Os 1.245 sem embedding são os que ainda esperam resumo pelo B2.
- **B4 parcial nº 2** (06/10 18:47Z, `incremental-sync` [2026-03-01, 2026-10-06]): 38.833 indexados, 0 erros. Busca semântica ok.
- **Pendente:** B2 (executor, a partir de 07/10 03Z) → B3 e B4 da sobra (`--require-summary`, janela do B2) → histórico do BigQuery (pedir OK do DELETE das linhas parciais de 28/05, 29/06 e 30/06).
- **G3 EM PRODUÇÃO** (gobus-mcp#10, 06/10 ~19:35Z, depois da validação visual do usuário):
  - 14 tools, 4 com MCP App;
  - 4 resources `ui://` com `text/html;profile=mcp-app`, sem previews dev;
  - payload do forecast com 9,8 KB (summary primeiro);
  - **MCPJam conformance 7/7 contra produção**.
  - embeddings#13 mergeado (só scripts e tests, sem deploy).
- **BigQuery:**
  - Achado: o `sync_facts` carregava 2 dias por execução (`end` inclusivo + `logical_date` = horário da execução no Airflow 3), o que dava duplicatas de 2–6% em mar–mai.
  - Correção `previous_day_window()` (TDD) adicionada ao DP-A (data-platform#204, merge após 27/10). Issue de dedup do histórico aberta.
  - Teste do mecanismo: DELETE de 28/05 (4 linhas), depois DAG com `logical_date` 29/05 → 28/05 = 248 e 29/05 = 274, **iguais ao Postgres**, sem duplicatas.
- **Executor pós-B2** (`scratchpad/post_runner.sh`, iniciado às 19:46Z):
  1. espera o B2 → B3 da sobra (`--require-summary`, [01/03, 07/10)) → B4 (`incremental-sync` [01/03, 07/10]);
  2. DELETE no BigQuery das linhas parciais de 29/06 e 30/06;
  3. 64 execuções do DAG (logical dates de 31/05 a 04/10, de 2 em 2 dias, sem sobreposição);
  4. conferência BigQuery × Postgres por dia.
  - Estado em `post_runner.state`, log em `post_runner.log`.
