> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — crítica de integração, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Crítica de integração da Fase 2.5: contratos, sequência, terceiros, aceite e correções

Base: os 5 relatórios do scratchpad (o `r_critic.md` prevalece), os 3 rascunhos com as respectivas verificações e checagens read-only feitas agora: `git show origin/main`, `gh pr view/diff/list`, `gh run list`, introspecção do GraphQL público e inspeção das venvs. Não alterei nenhum arquivo.

## 0. Achados desta rodada que mudam o plano

**I1. O data-science#38 (ODenteAzul, `reviewDecision: APPROVED`) colide com a correção de F0a.** O PR troca o modelo de enriquecimento para Nova 2 Lite e adiciona guardrails.
- Mexe nos mesmos 4 arquivos do DS-1: `llm_client.py`, `classifier.py`, `enrichment_job.py` e `worker/handler.py`.
- Altera a mesma linha `DEFAULT_ENRICHMENT_MODEL_ID` (passa a `us.amazon.nova-2-lite-v1:0`).
- O `UPDATE` de `update_news_enrichment` passa a gravar `summary_blocked*`. Essas colunas só existem com a migração do #189. O último comentário de revisão diz "pronto para merge após a Migration 027 (PR #189)".
- **Risco 1:** se o #38 for mergeado antes da migração de moderação, o UPDATE falha e o enriquecimento zera de novo.
- **Risco 2 (provável, a confirmar):** o #38 não muda o corpo da requisição. `_call_bedrock` continua chamando `invoke_model` com `anthropic_version`. O id Nova com corpo Anthropic tende a falhar.
- **Consequência para o INF-1:** a env `ENRICHMENT_MODEL_ID` do INF-1 só funciona com modelo Anthropic (Haiku 4.5) e passa por cima do default do #38 sem aviso.

**I2. O trio bge-m3 (infra#203, data-platform#184, embeddings#11) pode quebrar os embeddings quando os eventos voltarem.**
- O infra#203 está **APPROVED** e põe `MODEL_NAME=BAAI/bge-m3` e `MODEL_DIMENSION=1024` no embeddings-api.
- O data-platform#184 usa `004_add_bge_m3_columns.sql` e `004_rollback.sql`. São versões duplicadas, que o runner rejeita desde o 9646b1a. Ele também mexe em `typesense/collection.py` e `indexer.py`.
- Se o #203 for aplicado sozinho enquanto o INF-1 religa o `dgb.news.enriched`, o embeddings-api passa a gravar vetores de 1024d numa coluna de 768d.

**I3. A janela de normalização pós-defeso diverge entre os repos.**
- O D2 upstream vale para `26/10 ≤ date_end < 30/11`.
- O gobus usa `normalization_days=28`, ou seja, até 22/11.
- A janela é `[D−7, D−1]` (o `load_snapshot` usa `[date_end−7, date_end)`) e o baseline é `[D−35, D−8]`. O baseline só fica todo pós-defeso em D = 30/11.
- **Versão única:** recuperação de 26/10 a 29/11 nos dois repos, derivada como `fim + W + B` (= 35 dias).

**I4. O Composer só recebe o código de `trend_detection` como plugin copiado.**
- O `composer-deploy-dags.yaml` copia só `jobs/{bigquery,graph,integrity,similarity,thumbnail,trend_detection}`, `typesense/{client,collection}.py` e `cloud_run.py`.
- Por isso todo código novo do DP-B (`resolve_baseline_window`, `laplace_volume_ratio`, a guarda de burst) precisa ficar em `jobs/trend_detection/` e não pode importar outros módulos de `data_platform`.

**I5. Todos os checkouts locais estão em outros branches, alguns com trabalho em andamento.**

| Repo | Branch atual | Estado local |
|---|---|---|
| graphql-api | `feature/portal-policies-query` | — |
| data-platform | `feature/policy-gazetteer` | arquivos untracked |
| data-science | `feat/policy-ontology-enrichment` | — |
| infra | `fix/terraform-sa-dns-admin` | — |
| embeddings | — | `scripts/` untracked |
| scraper | — | `checker.py` modificado |
| portal | `feature/portal-politicas-page` | — |

- Os installs editáveis apontam para o `src` do checkout principal: `gobus_mcp.pth`, `data_platform.pth`, `data_science.pth`.
- Só a graphql-api tem `pythonpath=["src"]` no pytest.
- Teste rodado num worktree com a venv principal importa o código do outro branch, a menos que se use `PYTHONPATH=<worktree>/src` ou uma venv por worktree.

**I6. A troca de classificador (Haiku 3 → Haiku 4.5, e talvez Nova depois) cria degraus artificiais na série de temas.**
- O degrau fica na virada de 25–26/09, porque o backfill B2 e o tráfego ao vivo usam o modelo novo e o baseline usa o Haiku 3.
- O share-of-voice do F3 vai acusar picos e quedas falsos em temas cuja fatia mudou com o classificador:
  - janelas 7/28 até cerca de 30/10;
  - janelas 21/84 até meados de janeiro.
- O caminho por tema do F5 sofre o mesmo efeito.

**I7. Os temas e o sentimento recuperados pelo B2 só aparecem para o gobus depois do B4.**
- `topThemes`, `trendingThemes` e o filtro `sentiment` leem o Typesense. O B4 (incremental-sync) precisa rodar logo depois de B2 e B3, e não em 15/10.

**I8. A 027 e a 028 provavelmente já estão aplicadas.**
- Houve 5 execuções de `db-migrate` em `main` hoje, entre 16:05 e 17:08 UTC, depois do 30e4fe9. Mesmo assim, rodar `command=status` antes da 029.

**I9. O script de backfill de embeddings não é versionado.**
- `embeddings/scripts/backfill_embeddings.py` está **untracked** (16/03). Ele trata `content_embedding IS NULL` e aceita intervalo de datas. O B3 e a correção dos MOCK dependem dele, então não pode ser perdido.

**I10. A graphql-api não tem teste de drift de schema.** O `docs/reference/schema.graphql` está desatualizado desde 01/07 e só existe `tests/test_schema.py`.

**I11. O pre-commit do data-platform não está instalado no clone e vai gerar ruído.**
- O `.git/hooks` não tem `pre-commit`.
- O `persist.py` não está no ruff-format do hook (`ruff format --line-length 100 --check` falha). O hook vai reformatar o arquivo inteiro.
- O hook também roda `sqlfluff` nas migrações, `detect-secrets` com baseline e `validate-feature-registry`.

## 1. Contratos compartilhados: divergências e versão única

### 1.1 Tabela de divergências

| Tema | F1+F3 | F4+F5 | F0+F2 | **Versão única** |
|---|---|---|---|---|
| Local dos modelos | `analytics/models.py` | `payloads/*.py` | — | `src/gobus_mcp/payloads/`: `common`, `readability`, `scorecard` (G1); `anomalies`, `forecast` (G2); `coherence` (G3) |
| Pacote de análise | `analytics/` | `analysis/` | — | `analytics/` (com `coherence.py` e `framing.py`) |
| Calendário | `calendar.py`, normalização de 28d | `timeutil.py` + `blackout.py`, até ~22/11 | D2 até < 30/11 | `calendario.py` no **G1** (evita sombrear a stdlib e destrava o F5), recuperação até 29/11 (I3) |
| Vocabulário de status | `ok/degradado/indisponivel` | `ok/partial/empty/unavailable` | — | bloco/dado: `ok\|degraded\|unavailable`; relatório: `ok\|partial\|empty\|unavailable` |
| Idioma dos enums | valores em PT | misto | — | ASCII em inglês, coerente com `sensitivity=high\|medium\|low`, `policies.domain` e o CLAUDE.md ("inglês em identificadores"); rótulos em PT só em `labels_pt` |
| Avisos de dado | `DataStatus` + `KNOWN_INCIDENTS` | `DataNotice` com códigos | — | `DataStatus` (`data_status.py`) mais `Notice` (payload), com mapeamento fixo (§1.3) |
| Datas de incidente | fixas | proibidas no código | — | detecção sempre dinâmica; a data fixa só serve de *hint* de `since` em Python quando o detector diz não-ok; nunca no JS |
| Domínios | 7 | 8, com `OTHER` | — | os 7 de `policies.domain` mais `OTHER` (POLICY sem domínio cai no mapa da dona; o resto vai para `OTHER`) |
| Formato de anomalias | blocos `themes`/`entities` | listas planas `spikes`/`silences` mais gauges | — | blocos do F3 com os campos que o F4 precisa (§1.4) |
| Forecast | chaves `"3"/"7"/"21"`, sem parâmetro de fim de semana | `3d/7d/21d`, `weekendCorrection`, `daily` por tema | — | chaves `3d/7d/21d`; **sem** `weekend_correction` (share-of-voice e perfil sempre ligados; o toggle sai da UI); `daily` histórico de tema = `null` na v1 |
| Severidade | `severity` de 0 a 1 | `score` + `band` | — | `severity` de 0 a 1 mais `band: normal\|watch\|alert` (<0,33 / <0,66 / ≥0,66), calculados no F3 |
| Escala de Flesch | `"textstat-en"` | `"flesch_en_textstat"` | escala inglesa (F0g) | uma constante `FLESCH_SCALE_ID="flesch_en_textstat"`; faixas exportadas no payload; o JS não codifica limiares |
| Nota do `score_article` | renormaliza o que houver | nota só com 3 dimensões | — | `scored` (3 dimensões); `partial` (Flesch + ≥1 outra, renormalizada, com flag); `refused` (sem Flesch ou sem wordCount) |
| Benchmark do scorecard | `agencyAnalytics` ponderado, `pub−90d` | amostra de 250, mediana, janela nominal | — | amostra `ag`/`ab` ancorada no `publishedAt`; `window` = min/max **real** da amostra; `sampleSize`; `null` se n<10. O G1 implementa |
| Parâmetros de readability | — | `date_to` | — | `date_to` entra no **G1**, junto com a "janela efetiva" |
| Cobertura de readability | `Coverage{covered_articles…}` | `articlesWithFlesch` (sem fonte) | — | `{periodsTotal, periodsWithData, articlesTotal, articlesInPeriodsWithData, lastPeriodWithData}` |
| Pydantic | gerador de alias com campos já em camelCase | alias camelCase | — | campos em snake_case com `ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True, extra="forbid")` (pydantic 2.13.4 na venv) |
| Retorno das tools de app | — | `TextContent(text=…)` (inválido) | — | `ToolResult(content=markdown, structured_content=payload.model_dump(mode="json"))` |
| Registro das tools | 13 com `output_schema=None` | as 4 de app com `-> ToolResult` | — | toda tool sem `outputSchema`; as não-app ficam `-> str`; `annotations={"readOnlyHint":True}` em todas já no G1 |
| `.mcp.json` | stdio | `/mcp` no commit 12 | — | só no G1: stdio com nome `gobus-local`; o F4 não mexe |
| Workflow de CI | `test.yaml` | `ci.yaml` | — | `test.yaml`; o G3 acrescenta os jobs `ui` e `apps-conformance` |
| Markers do pytest | `live`, `ui` | só `ui` | — | `addopts="-m 'not live and not ui'"` |
| Mock do cliente | `route()` | `set_responses` em ordem | — | `FakeGraphQLClient.route(op_name, …)` em todo teste novo |
| Dependências no `server` | `_client`, `_catalog`, `_activity` | monkeypatch só de `_client` | — | contêiner `Deps(client, catalog, activity)` com `get_deps()`; os testes trocam `server._deps` |
| Snapshot do SDL | introspecção ao vivo | — | fixture do `export_schema` | consumidores (gobus e data-platform) usam introspecção ao vivo; o GA-1 regenera `docs/reference` e cria o teste de drift (I10) |
| Health do ranking | `vr/wc ≥ 100`, idade > 7d | — | idade de `max(computedAt)` + `isNew` | antes do F2: linhas legadas por `vr/wc ≥ 100`; depois: um único `computedAt` com idade ≤ 13h; fração de `isNew` só quando o campo existir no snapshot |
| Corte de tom (F5) | — | "via health" | — | cobertura dinâmica pelo filtro `sentiment` do Typesense na própria janela |

### 1.2 Regras do payload

- **Versionamento:**
  - campo opcional acrescentado mantém `schemaVersion=1`;
  - remover ou renomear campo sobe a versão;
  - o JS mostra "versão incompatível" quando a versão é desconhecida;
  - a URI `ui://` não muda.
- **`summary`:** é o primeiro campo legível e é idêntico ao `content` (truncado em 6 KB).
- **Orçamento:** payload ≤ 20 KB (meta ≤ 10 KB); null sai como `null` (`exclude_none=False`).

### 1.3 Base comum (`payloads/common.py` e `data_status.py`, no G1)

```python
Status = Literal["ok","degraded","unavailable"]; ReportStatus = Literal["ok","partial","empty","unavailable"]
DataKey = Literal["themes","summaries","sentiment_labels","sentiment_analytics","entities_ner","readability",
                  "word_count","article_trending","entity_ranking","indexing_lag","agency_activity"]
class DataStatus(Payload): key: DataKey; status: Status; since: date|None; message: str; metric: dict[str, float|int|None] = {}
NoticeCode = Literal["THEMES_UNCLASSIFIED","SENTIMENT_UNAVAILABLE","READABILITY_UNAVAILABLE","TRENDING_ENTITIES_STALE",
                     "BASELINE_ZERO_SUPPRESSED","CLASSIFIER_CHANGED","ELECTORAL_BLACKOUT","POST_BLACKOUT_RECOVERY",
                     "INDEXING_LAG","SAMPLE_TRUNCATED"]
class Notice(Payload): code: NoticeCode; severity: Literal["info","warn","error"]; message: str; since: date|None; affects: list[str] = []
class CalendarContext(Payload): phase: Literal["normal","blackout","recovery"]; label: str|None; blackout_start: date|None
    blackout_end: date|None; recovery_until: date|None; days_to_end: int|None; silenced_agencies: int|None; resumed_agencies: int|None
class Window(Payload): kind: Literal["closed","rolling"]; start: datetime; end: datetime  # end exclusivo
    days: int; bucket_tz: Literal["America/Sao_Paulo","UTC"]; baseline_overlaps_blackout: bool = False
class ReportBase(Payload): schema_version: Literal[1]=1; kind: str; tool: str; summary: str; status: ReportStatus
    generated_at: datetime; reference_date: date; params: dict; calendar: CalendarContext
    data_status: list[DataStatus]; notices: list[Notice]
```

Mapeamento de `DataStatus` não-ok para `Notice`:

| `DataKey` | `NoticeCode` |
|---|---|
| `themes` | `THEMES_UNCLASSIFIED` |
| `sentiment_*` | `SENTIMENT_UNAVAILABLE` |
| `readability` e `word_count` | `READABILITY_UNAVAILABLE` |
| `entity_ranking` | `TRENDING_ENTITIES_STALE` |
| `indexing_lag` | `INDEXING_LAG` |

`CLASSIFIER_CHANGED` (I6) é parâmetro do `calendario`: a data de corte vem do F0a, e o aviso fica ligado enquanto o baseline de alguma janela cruzar essa data.

### 1.4 `AnomalyReport` (G2 produz, G3 consome)

- `kind="gobus.anomalies"`, `tool="gobus_detect_anomalies"`.
- `params{sensitivity, domain_filter}`, `thresholds{ratio, window_agencies, silence_ratio, min_count}`.
- **`themes: ThemesBlock`**
  - `{status, note, windows{short,long}: Window(rolling, UTC), classified_coverage{short,long}, signals[ThemeSignal]}`.
  - `ThemeSignal{label, domain, kind: sustained_spike|sustained_drop, ratio_short, ratio_long, count_short, count_long, share_long, severity, band, confidence: high|medium|low, flags, daily=None}`.
- **`entities: EntitiesBlock`**
  - `{status, note, window: Window(closed, BRT nominal, bucket UTC), baseline: Window, candidates, upstream{last_run_at, rows_total, rows_last_run, rows_legacy_floor}, signals[EntitySignal]}`.
  - `EntitySignal{entity_id, name, type, domain, kind: coordinated_silence|concentrated_coverage|burst|new_entity|calendar_explained|normal, window_count, baseline_count, window_agencies, distinct_days, max_day_share, ratio, upstream_volume_ratio, upstream_computed_at, owner: OwnerInfo{agency_key, agency_name, method: agency_key|coverage, share}|None, owner_window_count, owner_activity_ratio, silence_score, severity, band, confidence, explanation, flags, daily[≤28], owner_daily[≤28], samples[]=[]}`.
  - `samples` fica vazio na v1; o G3 pode preencher com uma requisição de aliases.
- **`domains[8]`** em ordem fixa (HEALTH, EDUCATION, SOCIAL, ECONOMIC, SECURITY, ENVIRONMENT, GOVERNANCE, OTHER):
  - `{domain, label, spikes, silences, concentrated, max_severity, spike_level, silence_level, spike_band, silence_band}`.

### 1.5 `ForecastReport`

- `kind="gobus.forecast"`, `params{horizon_days_requested, horizon_days, limit≤10}`.
- **`windows{"3d","7d","21d"}`:** `{window_days, baseline_days, weight, effective_weight, classified_coverage, status, business_days, baseline_overlaps_blackout}`.
- **`platform`:** `{weekday_profile, level_by_phase, profile_source: snapshot|default}`.
- **`themes[ForecastTheme]`**
  - `{label, domain, windows{key: WindowRatio|None}, per_day_rate, weekly_multiplier, momentum: accelerating|decelerating|stable|undetermined, acceleration, confidence, projection: Projection|None, flags}`.
  - `Projection{horizon_days, expected_articles, low, high, share_now, share_at_horizon, daily[{date, expected}]}`.
  - Na v1, `low`/`high` saem só do intervalo de Poisson. O `daily` da projeção é calculado (não consultado), então pode existir.

### 1.6 `agency_catalog` (G1; usado por F1, F3, F4 e F5)

- **Interface:**
  - `Agency(code, name, is_republisher)`;
  - `all()`, `get()`, `name()` (fallback = code), `codes()`;
  - `republishers()` = `isRepublisher` ∪ `{"radioagencia_nacional"}`;
  - `validate()`: primeiro um mapa curado de aliases (`ms→saude`, `trabalho/mte→trabalho-e-emprego`, `tcu`/`camara`/`senado`/`ibge` → "fora do catálogo"), depois `difflib`;
  - `active(days, limit, include_republishers)` via `topAgencies`.
- **Nomes:** `agencyAnalytics(todas, D−1, D−1, DAY)` dá 156 nomes em cerca de 1,1 s. Cache de 24 h, single-flight.
- **Consumidores:**
  - F5 exclui `dgb_{code}` com `code ∈ codes()`, nunca por `startswith("dgb_")`;
  - F3 usa `republishers()` e `codes()`;
  - F4 usa `name()` e `is_republisher`.

### 1.7 Readability (G1; usado por F1 e F4)

- Um módulo `readability.py` com clamp em [0,100] na escala inglesa, faixas únicas 0/25/50/75 com chave e rótulo PT, `weighted_metric` (ignora null), `last_period_with_data`, "janela efetiva" e `readability_score()`.
- `score_article` deixa de ter tabela própria.
- `build_readability_payload`/`render_readability_markdown` e `build_score_payload`/`render_score_markdown` já no G1. O G3 só faz o binding do app (evita reescrever duas vezes).

### 1.8 Calendário (G1)

- `BLACKOUTS=(2026-07-04..2026-10-25)`.
- `recovery_until = fim + 7 + 28` = 29/11.
- `HOLIDAYS` federais: 12/10, 02/11, 15/11, 20/11 e 25/12, mais `PONTOS_FACULTATIVOS` configuráveis (28/10 costuma ser deslocado).
- Feriado conta como domingo em `effective_days` e fica fora da estimativa do perfil semanal.
- `baseline_for()` devolve a janela e `overlaps_blackout`.
- **Contrato entre repos por teste:** data-platform e gobus fixam as mesmas datas (04/07, 25/10, 29/11/30/11) nos seus testes.

### 1.9 Contratos upstream → gobus

- **`trendingEntities`:**
  - `volumeRatio` continua não nulo (o portal tipa `number`);
  - `baselineCount`, `baselineAgencies` e `isNew` são aditivos;
  - o G2 **não** depende deles (recalcula via `entityCoverage`); usa só depois do refresh do snapshot, após o GA-1.
- **`agencyAnalytics.pctPositive`:** pode vir `null` depois do GA-1. O avaliador do gobus se baseia na nulidade e na cobertura de `avgSentimentScore`, e funciona antes e depois.
- **`articlesTimeline`:** com o GA-1 passa a dar dias em BRT. É troca opcional do `platform_daily` no gobus, que hoje usa `agencyAnalytics DAY` em UTC. Documentar que os buckets são UTC.

## 2. Sequência global, PRs e cronograma

### 2.1 PRs: 5 upstream, 3 no gobus e 1 tardio

| PR | Repo / branch (worktree a partir de `origin/main`) | Frentes | Depende de | Deploy | Alvo |
|---|---|---|---|---|---|
| INF-1 | infra / `fix/fase2.5-enrichment-model-workers-pg` | F0a (`ENRICHMENT_MODEL_ID`), F0b/F0f (remove `GRAPHQL_API_URL` dos 3 workers) | triagem, smoke do Haiku 4.5, decisão D0 | merge → `terraform-apply` | qua 07/10 |
| DS-1 | data-science / `feature/fase2.5-enrichment-observabilidade` | F0a (observabilidade, `reenrich_combined_window.py`) | INF-1; coordenação com o #38 | push em `src/news_enrichment/**` | sex 09/10 |
| DP-B | data-platform / `feature/fase2.5-trending-entities` | F2 (029, Laplace, DELETE, ≥2 dias, D2) e melhoria do script de B1 (`scripts/`, sem deploy) | — | 029 via dispatch; merge → plugins do Composer | ter 13/10 |
| GA-1 | graphql-api / `feature/fase2.5-trending-sentimento-timeline` | F2 (filtro MAX + campos), F0c, F0d, regeneração do SDL e teste de drift | 029 aplicada | push em `src/graphql_api/**` | qua 14/10 |
| G1 | gobus / `feature/fase2.5-higiene` | F1 completo, mais `calendario.py`, `payloads/common` e builders de readability/scorecard | — | push em `src/` | sex 09/10 (reserva: ter 13/10) |
| G2 | gobus / `feature/fase2.5-analytics` (empilhado sobre o G1) | F3, mais as chaves de atraso e atividade do health | G1 | push em `src/` | ter 20/10 (limite: qui 22/10) |
| G3 | gobus / `feature/fase2.5-apps-coerencia` | F4 + F5 | G2 (radares), G1 (resto) | push em `src/` | ~qui 05/11 |
| DP-A | data-platform / `feature/fase2.5-graphql-workers` | F0b (latente: `ID!`, `themL*`, `json.dumps`, contrato), F0g (documentação) | GA-1 (SDL) | merge → redeploy dos 3 workers | depois de 27/10 (~03/11) |
| INF-2 | — | reabilitar o caminho GraphQL, allowlist da SA | — | — | fora da fase: **issue** |

Quanto ao GA-1: o filtro MAX é redundante com o DELETE, mas faz parte da decisão do usuário. A allowlist e a validação de `features` saem do GA-1 e vão para a issue do INF-2, porque são dormentes.

**Grafo de dependências:**

```
triagem F0 → smoke → INF-1 → {DS-1 → B2 → B3 → B4}
INF-1 → B1 (script do branch DP-B)
029 → DP-B → GA-1 → (refresh do snapshot no G2) → DP-A
G1 → G2 → G3 (radares)
G1 → G3 (readability, scorecard, F5)
```

**Caminho crítico do prazo de 25/10:**
- upstream: 029 → DP-B;
- gobus: G1 → G2.

### 2.2 Cronograma (dias corridos; 05/10 é segunda)

| Data | Faixa principal (sessão + usuário) | Subagentes em paralelo |
|---|---|---|
| ter 06/10 | Triagem F0 (A1–A8, F0b, F0e, F0f; SQL só com autorização do secret; contagem de `jsonb_typeof`). `db-migrate status`. Smoke do Haiku 4.5. Decisão D0. Mensagens aos donos de #38, #189, #184, #203 e #11 (mutação remota: usuário confirma) | **DP-B** (TDD, worktree); **GA-1** (TDD, worktree); **G1-a**, fundação no checkout do gobus: deps/lock, Dockerfile, CI, commit de ruff format, contrato, `client`, `cache`, `route`, `calendario`, `payloads/common` |
| qua 07/10 | Merge e apply do INF-1; verificação em 2–4 h (A3/A7, feature-worker, atraso do Typesense) | **DS-1** (worktree); **G1-b**: catálogo, readability, builders, null≠0, health enxuto; **G1-c** (docs/, sem conflito); DP-B e GA-1 seguem |
| qui 08/10 | B1 com `--dry-run` e `--limit 10`, depois completo (script do branch DP-B, com OK do usuário). 029 com `dry_run` a partir do branch | PRs de DS-1 e DP-B abertos (CI). PR do G1 aberto, com smoke do Docker (`/mcp`, `/sse`, `/messages/`). **G2** começa em worktree empilhado |
| sex 09/10 | Merge do DS-1. B2 completo com o governador (até sábado). Merge do G1, se verde | GA-1 com PR aberto; G2 segue |
| sáb–dom 10–11/10 | B2 termina; ninguém dá merge | G2 local; **G3-b** (funções puras do F5) |
| seg 12/10 | **Feriado: sem merge nem deploy** | G2 e G3-b seguem local |
| ter 13/10 | 029 aplicada (`target_version=029`, depois do `status`). B3 (embeddings) → **B4** (incremental-sync de 20/05 até hoje). Merge do DP-B por volta de 21:05 UTC. Merge do G1, se não foi na sexta | G2 rebase sobre `main` depois do squash do G1 (`rebase --onto`) |
| qua 14/10 | Conferir as execuções de 03 e 09 UTC (SQL, logs, linha de log de versão). Merge do GA-1 | G2 faz refresh do snapshot do SDL e valida temas ao vivo (pós-B4). **G3-a**: infra `ui/`, mini-host, apps de readability e scorecard |
| sex 16/10 | **Gate F2 em produção** (029, DP-B e GA-1, com pelo menos 8 execuções boas) | PR do G2 aberto (CI) |
| seg–ter 19–20/10 | Validação local do G2 (stdio apontando para o worktree, `pytest -m live`). Merge do G2 na terça → deploy → checagem em produção | G3-a segue |
| qua–sex 21–23/10 | Observação (pelo menos 20 execuções). Ensaio do D2 com SQL read-only usando o baseline de override e a janela atual (não `date_end=26/10`, que cai no futuro). Janela de hotfix | G3: apps de anomalias e forecast sobre o contrato do G2 |
| sáb 24 a ter 27/10 | **Congelamento** upstream e no gobus (só hotfix). Em 25/10 termina o defeso; em 26/10 o D2 e a fase `recovery` ligam sozinhos | — |
| 27/10–29/11 | Checklist diário (§4 F2/F3). Em 02/11 (feriado) sem deploy | G3 vira PR por volta de 03/11. Validação no basic-host, no Desktop e no claude.ai via `cloudflared`. Merge por volta de 05/11, depois validação pós-deploy. DP-A por volta de 03/11. B5, se a D3 for aprovada |
| 30/11 | O D2 e a `recovery` desligam sozinhos; conferir | issues: `readability_flesch_ptbr`, INF-2, cópias de MOCK no BigQuery e no HF |

### 2.3 Regras de execução

- **Worktrees:** cada PR upstream num worktree em `<repo>/.claude/worktrees/fase2.5-<tema>`. Nunca trocar o branch do checkout principal dos outros repos (I5). O G1 pode usar o checkout principal do gobus, porque a troca leva os arquivos untracked sem conflito.
- **Python:** testes com `PYTHONPATH=<worktree>/src .venv/bin/python…`, conferindo `python -c 'import X;print(X.__file__)'`, ou com venv própria do worktree.
- **Ações remotas exigem OK explícito do usuário:** merges, `gh workflow run`, comentários em PR, `gh issue edit`, `git push --delete`, `git restore docs/deploy.md` e leitura de secrets.
- **Backfills:** sempre `--dry-run`, depois `--limit 10`, depois completo, cada etapa com OK do usuário.
- **Hosts:** o Claude Desktop e o `.mcp.json` do workspace executam o checkout principal do gobus. Para validar o G2 ou o G3 a partir de um worktree, usar uma entrada stdio separada (por exemplo `gobus-g2`).

## 3. Conflitos com trabalho de terceiros

| Item | Conflito | Resolução |
|---|---|---|
| **data-platform#189** (moderação; `027_*` + `_ROLLBACK`; mexe em `sync_to_bigquery.py` e `ci-migrations.yaml`) | Versão 027 duplicada; `_ROLLBACK` em maiúsculas é lido como migração; conflita com o DP-A em `sync_to_bigquery.py`; o #38 depende dele | Renumerar para **030** só **depois** que a 029 estiver em `main` (`test_versions_have_no_gaps`), com `030_add_summary_moderation_rollback.sql`. O DP-A fica para depois de 27/10, o que adia o conflito. Ordem: 029 → 030 aplicada → #38 |
| **data-platform#184** (bge-m3; `004_*` duplicada; `typesense/collection.py` e `indexer.py`; `ci-migrations.yaml`) | Runner rejeita; muda o schema do Typesense; conflito com o #189 no YAML de CI | Renumerar para **031** depois da 030. O B4 roda antes de qualquer mudança de schema do Typesense. Segurar até depois de 27/10 |
| **infra#203** (APPROVED; bge-m3 1024d no embeddings-api) | Com o INF-1 religando os eventos, gravaria 1024d em coluna de 768d | **Segurar** até as colunas do #184 (031) e o embeddings#11 estarem prontos. Nunca no mesmo apply do INF-1. O `terraform-plan` do INF-1 deve mostrar só os 4 serviços (diffs alheios explicados, nenhum destroy ou replace) |
| **embeddings#11** (`pubsub_handler.py`, `text_prep.py`) | Muda o texto embutido e o modelo | B3 e o reprocesso dos MOCK rodam com o modelo atual, antes do bge-m3. O script de B3 é o untracked `scripts/backfill_embeddings.py` (preservar e versionar depois) |
| **data-science#38** (APPROVED; Nova 2 Lite + guardrails) | Mesmos 4 arquivos do DS-1; mesma linha de default; depende das colunas do #189; corpo Anthropic com id Nova; a env do INF-1 passa por cima do default | **D0:** Haiku 4.5 agora via env (único compatível com o `_call_bedrock` atual). Combinar com o autor: o DS-1 entra primeiro e o #38 faz rebase. O #38 só entra com a 030 aplicada, o corpo Nova corrigido e uma decisão de modelo; nesse momento a troca é só na `var.enrichment_model_id` (um único botão), com novo smoke e `CLASSIFIER_CHANGED`. O DS-1 **não** muda o default (evita conflito); em vez disso, loga em `ERROR` quando a env falta |
| **pre-commit do data-platform** (ruff 0.14.10 line-length 100, sqlfluff, detect-secrets, `validate-feature-registry`, mypy) | Hooks não instalados; `persist.py` fora do formato | Rodar `.venv/bin/pre-commit run --files <alterados>` antes de cada commit. Commit separado `chore: ruff format persist.py`. A 029 tem de passar no sqlfluff. Fixtures do tipo `postgresql://test:test@…` podem disparar o detect-secrets (atualizar a baseline) |
| **scraper** (`feature/verify-integrity`, `checker.py` modificado; mesmo pre-commit) | Nenhum PR da fase mexe nele | Não tocar no checkout |
| **Portal** (`volumeRatio: number`, `revalidate=600`, e2e) | O badge cai de cerca de 8571× para centenas ou menos; o DELETE pode esvaziar a seção, e o portal só a esconde | Nenhum PR. O DP-B garante `volume_ratio` não nulo. Badge "novo" via `isNew` vira issue depois da fase |
| **Branches locais do usuário** (gazetteer, policies, ontologia, DNS) | Trabalho de hoje em 027/028 (9646b1a, 30e4fe9) e `db-migrate` rodado 5 vezes | `status` antes da 029. Worktrees (I5) |

## 4. Critérios de aceite por frente

**F0 (medidos por SQL read-only, logs e GraphQL)**
- **a (enriquecimento):**
  - smoke: JSON 100% parseável em 20 artigos, códigos L1 válidos, concordância de L1 com o Haiku 3 ≥ 80%, com matriz por L1 registrada para o I6;
  - 24 h depois do INF-1: `enriched` ≥ 95% dos `Result for`;
  - 7 dias seguidos com 0 `enrichment_combined_failed`;
  - depois de B2 e B4: em todo dia (BRT) desde 25/09, tema, resumo e sentimento ≥ 95%;
  - `analyticsKpis(range:{days:7}){activeThemes}` ≥ 15;
  - `trendingThemes(7,28,growthThreshold:0)` não vazio.
- **b (features):**
  - fração com `readability_flesch` ≥ 95% por dia de 20/05 até hoje (depois do B1);
  - artigo novo com `word_count` em até 15 min;
  - `count(*) WHERE jsonb_typeof(features) <> 'object'` = 0;
  - `agencyAnalytics(["saude"],"2026-09-01","2026-09-30",MONTH){avgReadabilityFlesch avgWordCount}` não nulo.
- **c (sentimento):** `agencyAnalytics(["saude"],"2026-09-01","2026-09-26",MONTH){avgSentimentScore pctPositive}` não nulo, com `pctPositive` em [0,1] e diferença ≤ 5 p.p. para a fração do Typesense no mesmo recorte.
- **d (timeline):** `articlesTimeline(range:{days:14})` devolve 14 pontos sem erro, com soma igual à contagem do Postgres por dia BRT (±2%).
- **e (`trendingScore`):** causa raiz documentada. Se corrigido, `features.trendingScore` não nulo em ≥ 90% dos artigos das últimas 24h; se não, issue aberta com evidência.
- **f (atraso do Typesense):** em 3 medições num dia útil, contagem do Typesense no dia D ≥ 98% da do Postgres depois de 30 min.
- **g (Flesch):** descrição do `feature_registry.yaml` corrigida; teste que fixa a escala inglesa verde; issue `readability_flesch_ptbr` aberta.

**F2 (gate em 16/10, observação de 19 a 23/10)**
- `SELECT count(DISTINCT computed_at) FROM entity_trending_scores` = 1; `trendingEntities(limit:50)` sem nenhuma linha com `computedAt` anterior à última execução.
- Idade de `max(computedAt)` ≤ 13 h em qualquer leitura.
- 0 linhas no padrão do piso antigo (`volume_ratio ≥ 428,6 AND volume_ratio ≈ window_count·142,857`); `max(volume_ratio)` < 300, esperado mas não rígido.
- `baseline_count IS NOT NULL` em 100% das linhas.
- A linha de log de versão do `trend_detection` aparece na primeira execução depois do deploy.
- `isNew` exposto no GraphQL. A fração de `isNew` no top-50 fica registrada diariamente (hoje é 50/50) e o alvo vem do `evaluate.py` offline.
- Teste do caso Censo (divisão 57/3) documentando o comportamento.
- `computedAt` do portal recente em `/noticias`.

**F1**
- `gobus_get_readability_recommendations("saude")` sem erro e com o pior artigo; `("trabalho")` sugere `trabalho-e-emprego`; `("ms")` sugere `saude`.
- Teste de contrato: 100% das constantes `*_QUERY` válidas contra o snapshot e todas nomeadas (inclui `agencies.py`, `themes.py` e `platform_stats.py`).
- `tools/list`: 13 tools, todas com `outputSchema` null e `readOnlyHint`; `call_tool` não traz `structuredContent` e o texto não começa com `{"result"`.
- Nenhum "0.0" de Flesch ou wordCount vindo de null nas saídas (teste com fixture de null).
- `score_article`: com Flesch nulo, "Nota indisponível" e nenhum "5.6"; com dado, nota e benchmark com `sampleSize ≥ 10`. Validar ao vivo nos dois estados: antes do B1 e com um artigo de junho.
- Health: `readability=unavailable` com tudo nulo e `ok` depois do B1; `entity_ranking=degraded` antes do F2 e `ok` depois.
- Higiene de dependências:
  - `poetry check --lock` OK com fastmcp 3.4.2, pytest 9.1.x e pytest-asyncio 1.4.x;
  - imagem construída do lock;
  - `test.yaml` verde (pytest, `ruff check`, `ruff format --check`, `mkdocs build --strict`);
  - `deploy` com `needs: ci`.
- Smoke do Docker em `/mcp`, `/sse` e `/messages/`.
- Prompts só citam tools `gobus_*` existentes (teste).
- Docs: 13 páginas em `docs/tools`, 7 em `docs/resources`, nav e contagens atualizadas.

**F3 (em produção até 20/10, limite 22/10)**
- Testes de fase para 03/07, 04/07, 25/10, 26/10, **29/11** e **30/11**. Feriados cobertos.
- Fixtures de 05/10:
  - o Markdown não tem "8571" nem nenhum `volumeRatio` do upstream;
  - temas `unavailable` com `since` 26/09;
  - payload valida o modelo, ≤ 20 KB e `summary == markdown`.
- 0 sinais com `baseline_count == 0` nas classes `coordinated_silence` e `concentrated_coverage`.
- Entidades com `max_day_share ≥ 0,8` classificadas como `burst`.
- `domain_filter` inválido devolve as opções.
- `forecast_trends(horizon_days=7)` e `(21)` dão saídas diferentes.
- Depois do B4 (≥ 14/10): ao vivo, temas `ok` e `momentum` não todo `stable`.
- Latência em produção: `detect_anomalies` p50 ≤ 2 s com cache quente e ≤ 6 s a frio; `forecast_trends` ≤ 2 s.
- Cenário `now=2026-10-30`: entidades dominadas por agências retomadas viram `calendar_explained` com a flag `recovery`.
- Ao vivo em 27/10 e 03/11: aviso `POST_BLACKOUT_RECOVERY` presente.
- `CLASSIFIER_CHANGED` ativo enquanto algum baseline cruzar a data de corte.

**F4**
- MCPJam `apps conformance` 7/7 local, no CI e em produção depois do deploy.
- Teste de wire:
  - nas 4 tools de app, `meta.ui.resourceUri` igual a `meta["ui/resourceUri"]`;
  - MIME `text/html;profile=mcp-app`;
  - `resources/read` com 0 chamadas GraphQL.
- Playwright, em todas as fixtures × claro/escuro × 320/760 px:
  - 0 erros de console e 0 violações de CSP;
  - handshake na ordem certa;
  - `size-changed` com altura entre 100 e 2000;
  - fixture XSS sem `dialog`.
- Orçamento: HTML ≤ 60 KB por app, `structuredContent` ≤ 20 KB (típico ≤ 10 KB), `summary` ≤ 6 KB.
- Renderiza no Desktop (stdio), no basic-host e no claude.ai, com checklist e screenshots no PR. O Claude Code recebe o `summary`.

**F5**
- `gobus_get_message_coherence(entity_id="Q575545", date_from="2026-08-01", date_to="2026-09-30")` em ≤ 3 s, saída ≤ 5 KB, índice de 1 a 5 com tabela de dimensões.
- Republicadoras em seção separada; `[MOCK]` ignorado; virada de dia BRT testada.
- Erro sem `entity_id` nem `theme` (ou com os dois).
- Tom presente quando a cobertura ≥ 50%.
- Aviso de tema dinâmico (some depois do B2 e do B4).
- Notas de calibração em `_experiments/coherence-calibration-2026-10/`.

## 5. Correções obrigatórias ainda não aplicadas nos rascunhos

**F0+F2**
1. **B1:**
   - passar `--date-to <amanhã>` explícito (o default do script é 2026-07-01);
   - uma única execução que cubra `content_annotations` (filtro composto, ou laço sobre `handle_feature_computation`);
   - volume de cerca de 17 mil, não 25 mil.
2. **B2:**
   - cota = cota real da AWS com margem, aplicando a fração de 0,8 uma vez só;
   - volume de cerca de 1,6 a 1,9 mil;
   - B3 e B4 logo em seguida, em 13/10 (I7).
3. **029:** rodar `status` antes. Sem índice; só `ADD COLUMN` + rollback. Passar no sqlfluff.
4. **Health:** idade de `max(computedAt)` mais a fração de `isNew`, não só `isNew`.
5. **D1/burst:**
   - teste do caso 57/3;
   - rodar o `evaluate.py` antes de decidir o `log1p`;
   - limitar o termo `agency_growth` quando `ba=0`.
6. **DP-B:**
   - código novo só em `jobs/trend_detection/`, sem imports de fora (I4), com linha de log de versão;
   - commit `chore:` de ruff format no `persist.py`;
   - pre-commit rodado à mão.
7. **Ensaio do D2:** baseline de override com a janela atual, não `date_end=26/10`. Documentar que, durante o override, `is_new` passa a significar "não visto em junho".
8. **Gate do PR-1:**
   - origem das credenciais AWS e autorização dos secrets (PG e AWS);
   - permissões IAM para o perfil `us.` e para os ARNs regionais;
   - critério do `terraform-plan`: "nenhum destroy ou replace, diffs alheios explicados".
9. **DS-1:** não mudar o default do modelo (conflito com o #38); falhar ou logar em `ERROR` quando faltar a env.
10. **#189:** a renumeração para 030 só vale com a 029 em `main`. Incluir a mesma regra para o #184 (031).
11. **Testes:**
    - o GA-1 adapta `test_invalid_range_returns_error`;
    - usar os arquivos de teste existentes (`test_postgres_bigquery.py`, `test_postgres_features.py`, `tests/auth/test_service_account.py`);
    - criar o teste de drift do SDL;
    - o DP-A reescreve os testes `tests/workers/*_graphql.py`, que fixam `themL*`;
    - a variante ao vivo do contrato fica fora de `tests/unit`.
12. **Referências e processo:**
    - corrigir N6 → N1.6 e as linhas `:40-45` e `:57-60`;
    - o #189 tem só um comentário, não uma review formal;
    - tabela de convenção de commit por repo:

      | Repo | Atribuição | Mensagens |
      |---|---|---|
      | gobus | sem atribuição ao Claude | PT, `fix:`/`feature:`… |
      | graphql-api | sem atribuição ao Claude | PT, `fix:`/`feature:`… |
      | infra | sem atribuição ao Claude | — |
      | data-platform | aceita `Co-authored-by` (histórico) | — |
      | data-science | aceita `Co-authored-by` (histórico) | — |

    - sondas futuras só com queries; registrar o incidente da mutation enviada.
13. **Issue #3 e B5:**
    - sem a IP (o repositório é público e a IP já foi exposta);
    - zerar também `content_embedding` antes do B3;
    - D3: o tema dos MOCK também é falso;
    - citar as cópias no BigQuery e no HF;
    - conferir o DAG de thumbnails para o período de 26/09 até a correção.

**F1+F3**

14. **Mover para o G1:**
    - `calendario.py` (renomeado);
    - os builders e `payloads/` de readability e scorecard;
    - o parâmetro `date_to`;
    - `readOnlyHint` em todas as tools.

    O health do G1 usa só `data_status`. Atraso e atividade vão para o G2 (A1, B2 e B9 da verificação).
15. **`detect_trends` e `agency_summary`:**
    - pedir `baselineDailyAvg`;
    - converter o limiar com g0 = B·r0/(r0·W + B − W);
    - nunca usar `growthThreshold:0`.

    O desvio de usar `topThemes` + `analyticsKpis` no anomalies/forecast, em vez de `baselineDailyAvg` como o usuário decidiu, precisa ser registrado como **decisão a confirmar** (D7). Trocar "cancela" por "atenua" para o efeito do defeso.
16. **Health:**
    - `withSentiment` com `startDate`=D−7, comparando com o total da mesma janela;
    - atraso medido no dia D, não em D−1;
    - nomes do catálogo via `agencyAnalytics` DAY de um dia;
    - aliases curados antes do `difflib`.
17. **Ranking e normalização:**
    - "janela efetiva" de readability no ranking, no report e no dashboard;
    - benchmark ancorado no `publishedAt`;
    - período do snapshot limitado por fase;
    - feriados no calendário;
    - deduplicar `(period, agencyKey)`;
    - `domain_filter` com `OTHER`;
    - normalização até **29/11** (I3).
18. **Testes, modelos e higiene:**
    - nomear as queries de `themes.py` e `platform_stats.py`;
    - incluir `test_resources.py` e os mocks com a chave `search` na tabela de testes;
    - corrigir a faixa do skill para `:15-58`;
    - pydantic com campos snake_case e `serialize_by_alias`;
    - cabeçalho do Markdown com janelas móveis (UTC) para temas e fechadas para entidades;
    - `.mcp.json` com o envelope `mcpServers` e o nome `gobus-local`;
    - `Deps` em vez de três monkeypatches;
    - `tzdata` obrigatório;
    - `test.yaml` só com `pull_request` + `workflow_call` + `workflow_dispatch`;
    - `mkdocs build --strict` validado localmente antes de virar gate;
    - smoke do Docker também em `/sse` e `/messages/`.
19. **Ações destrutivas ou remotas** (`git restore docs/deploy.md`, `push --delete`, `gh issue edit`) só com confirmação. A IP em `_plan/` deve ser omitida (redigida) antes do commit.

**F4+F5**

20. **Retorno e versão:** `ToolResult(content=markdown, …)`; versão do pacote com fallback (`__version__` ou `"0+unknown"`).
21. **Infra de teste:**
    - markers `live` e `ui` no `addopts`;
    - o Makefile já existe (acrescentar alvos; receita de uma linha com `$$!`, `until curl` e `trap`);
    - jobs no `test.yaml`;
    - sem o job `package`.
22. **`.mcp.json`:** fora do F4. Ressalva sobre o Claude Code com HTTP (CLAUDE.md, seção "MCP no Claude Code"); prever fallback para `/sse` no claude.ai.
23. **CLAUDE.md:** atualizar a regra "Tools retornam Markdown" com a exceção das tools de app (`summary` + payload, custo de tokens). Criar `docs/tools/*` para as 4 tools de app; as `gobus_dev_preview_*` ficam isentas e marcadas "DEV — dados fictícios".
24. **Payloads:**
    - sem `articlesWithFlesch` (usar os campos de §1.1);
    - `daily` de tema = `null`;
    - `samples` opcional;
    - sem `weekend_correction`;
    - a regex de "sem referência externa" deixa passar o namespace SVG;
    - TDD com mini-host e fixtures logo depois do commit 1.
25. **F5:**
    - sem `include_republishers`;
    - exclusão `dgb_{code}` via catálogo;
    - `entitySearch(limit:3)` escolhendo pelo maior volume;
    - ignorar `[MOCK]`;
    - tom por aliases de contagem agência × rótulo;
    - aviso de início truncado por taxa diária;
    - calibração tratada como sanity check, não como gabarito;
    - `analytics/` em vez de `analysis/`;
    - `calendario` em vez de `timeutil` e `blackout`.
26. **Validação no claude.ai:** túnel `cloudflared` antes do merge ou validação pós-deploy declarada, com rollback por revert. Playwright com `async_api`. Diretórios `tests/test_ui/` (puros) e `tests/browser/` (Playwright), cada um com `__init__.py`.

**Decisões pendentes do usuário**

| Id | Decisão | Recomendação |
|---|---|---|
| D0 | Modelo do hotfix e coordenação com o #38 | Haiku 4.5 agora |
| D1 | `log1p` mais limite no `agency_growth` | Decidir depois do `evaluate.py` |
| D2 | Baseline pré-defeso no upstream de 26/10 a 29/11 | Sim |
| D3 | Reenriquecer os MOCK em vez de só `UPDATE` | — |
| D4 | Guarda de burst por `max_day_share` além dos ≥2 dias | — |
| D5 | Enums do payload em inglês | Sim |
| D6 | Reenriquecer 28 dias antes do corte (cerca de 4 mil artigos) para alinhar os baselines de tema | — |
| D7 | Aceitar `topThemes` em vez de `baselineDailyAvg` no anomalies/forecast | — |

### Critical Files for Implementation
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/server.py (com os novos `payloads/common.py` e `calendario.py`)
- /Users/nitai/dev/destaquesgovbr/data-platform/src/data_platform/jobs/trend_detection/persist.py (e `signals.py`, `scorer.py`, `dags/compute_entity_trending.py`, `scripts/migrations/029_*`)
- /Users/nitai/dev/destaquesgovbr/graphql-api/src/graphql_api/datasources/postgres.py
- /Users/nitai/dev/destaquesgovbr/infra/terraform/enrichment-worker.tf (e `feature-worker.tf`, `typesense-sync-worker.tf`, `bronze-writer.tf`, `variables.tf`)
- /Users/nitai/dev/destaquesgovbr/data-science/src/news_enrichment/worker/handler.py (ponto de conflito com o data-science#38)
