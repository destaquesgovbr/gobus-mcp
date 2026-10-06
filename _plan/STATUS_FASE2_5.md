# STATUS — Execução do PLANO_FASE2_5 (handoff)

> **Snapshot:** 2026-10-06 19:48 UTC (16:48 BRT).
> **Plano:** `gobus-mcp/_plan/PLANO_FASE2_5.md`. O §14 tem o registro detalhado de execução; a versão mais completa é a cópia **não versionada do checkout principal**, ver §8.
> **Anexos de desenho:** `gobus-mcp/_plan/fase2_5/` (investigacao/ e desenho/; `integration.md` prevalece).
> Este documento substitui o histórico da sessão anterior. Leia-o inteiro antes de agir.

---

## 1. Resumo executivo

- **Prazo duro (25/10, fim do defeso): cumprido.** O gate F2 foi atingido em 06/10 03:01Z.
- **Incidentes de dados (F0): resolvidos em produção.**
  - O enriquecimento voltou (Haiku 4.5).
  - Os workers estão no caminho PG.
  - O re-scrape não apaga mais resumo nem embedding.
  - O NER parou de rodar em duplicidade.
- **gobus-mcp: G1, G2 e G3 em produção.** São 14 tools, das quais 4 são MCP Apps validadas pelo usuário. MCPJam 7/7 em produção.
- **Em andamento, sem intervenção:** dois executores locais encadeados (§4). Fazem o B2, o B3 e o B4 finais e o histórico do BigQuery. Levam ~2–3 dias.
- **Pendências com data:** merge do DP-A depois de 27/10; reverter as URLs de defeso do scraper depois de 25/10 (§5).

---

## 2. PRs da Fase 2.5

| PR | Frente | Estado | Observação |
|---|---|---|---|
| infra#215 | F0a/b/f (INF-1) | ✅ merge e apply em 06/10 00:19Z | `ENRICHMENT_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0`; `GRAPHQL_API_URL` removido dos 3 workers; <colaboradora externa> removida do tfvars (o disco da devvm foi destruído, com OK do usuário) |
| clipping#25 | CL-1 | ✅ merge e deploy às 00:37Z | Sonnet 4 (EOL em 14/10) trocado por Sonnet 4.6; parse do digest tolera cercas ```json |
| data-platform#202 | F2 (DP-B) | ✅ merge às 01:13Z | Migração 029 aplicada às 01:06Z; trending v2 (snapshot único, Laplace, ≥2 dias, baseline pré-defeso de 26/10 a 29/11) |
| graphql-api#28 | F2/F0c/F0d (GA-1) | ✅ merge às ~01:16Z | `trendingEntities` só da última execução, mais `baselineCount`/`isNew`; sentimento aninhado; `articlesTimeline` em Postgres |
| graphql-api#29 | hotfix | ✅ merge às ~01:35Z | Regressão do #28: `Decimal` no Float do graphql-core 3.3 (sem lockfile) → `_as_float()` |
| gobus-mcp#8 | F1 (G1) | ✅ merge às 01:20Z | Higiene, dados honestos (null≠0), fundações, teste de contrato, CI |
| data-science#43 | F0a (DS-1) | ✅ merge às ~09:55Z | Falha combinada visível (logs estáveis), NER no máximo 1 vez por uid, script de re-enriquecimento |
| gobus-mcp#9 | F3 (G2) | ✅ merge às ~09:55Z | Anomalias (silêncio coordenado) e forecast cientes do defeso |
| scraper#64 | SC-1 | ✅ merge às 11:55Z | O re-scrape preserva summary, temas, image_url e embedding; só republica se o conteúdo mudou ou se o artigo ainda não tem tema |
| data-science#44 | DS-2 | ✅ merge às 11:55Z | `--select null-summary` com prompt enxuto |
| gobus-mcp#10 | F4+F5 (G3) | ✅ merge às ~19:35Z | 4 MCP Apps e `gobus_get_message_coherence`; validado pelo usuário no Desktop e no claude.ai |
| embeddings#13 | B3 | ✅ merge (sem deploy) | Script `backfill_embeddings.py` versionado, com `--require-summary` e identity token do Cloud Run |
| **data-platform#204** | **DP-A** | 🟡 **aberto. NÃO mergear antes de 28/10.** Evitar 02/11 e 20/11 | Caminho GraphQL latente, tipos do parquet do BigQuery, `allow_update` com COALESCE, Flesch, **`previous_day_window`** (o sync carregava 2 dias). O deploy afeta 4 workers, `composer-deploy-dags` e `postgres-docker-build` |

**Comentários postados em PRs de terceiros** (ODenteAzul, com OK do usuário): data-science#38 (Nova; entra depois do DS-1 e da migração de moderação), data-platform#189 (renumerar para **030**), data-platform#184 (renumerar para **031**), infra#203 (**segurar**; aplicar por último no pacote bge-m3), embeddings#11.
Migrações em produção: até a **029**. A 030 e a 031 estão reservadas para #189 e #184.

---

## 3. Status por frente e aceite

| Frente | Status | Evidência e pendências |
|---|---|---|
| **F0a** enriquecimento | ✅ | H1 confirmada: o Claude 3 Haiku teve EOL em 10/09 e quebrou em 25/09. O Haiku 4.5 está no ar desde 00:19Z de 06/10 (revisões 00019 e 00020). O Sonnet caiu de 8,7M para ~0,3M tokens/dia logo depois do INF-1 (a amplificação parou; o consumo de 06/10 é dos jobs de backfill). **Pendente:** B2 (§4) |
| **F0b** features | ✅ | B1: 20.472 artigos, 0 falhas, Flesch ≥94,5% por dia desde 20/05. Workers no caminho PG |
| **F0c** sentimento (graphql-api) | ✅ | `agencyAnalytics` sem erro; set/2026 com sentimento |
| **F0d** articlesTimeline | ✅ | 7 pontos sem erro |
| **F0e** trendingScore por artigo | 🟡 | Causa: o `sync_facts` falhava (`has_image` INT32). Voltou depois do B1 (06/10 10:01Z carregou 05/10). O histórico está no executor (§4). Hardening no DP-A |
| **F0f** atraso do Typesense | ✅ | Tempo real religado. B4 parcial: 22.834 e depois 38.833 indexados, 0 erros |
| **F0g** Flesch inglês | ✅ (decisão) | Mantido; descrição corrigida no DP-A; issue data-platform#203 (pt-BR) |
| **F1** G1 | ✅ | `readability_recommendations("saude")` ok; 13 (agora 14) tools sem outputSchema; contrato verde |
| **F2** trending | ✅ **gate** | 06/10 03:01Z: 1 execução, 32 linhas, `max(vr)` de 8571 para 24, `baseline_count` 100%, log `trend_detection v2`. Observação diária pendente até 29/11 (D2 liga em 26/10 e desliga em 30/11) |
| **F3** G2 | ✅ | Sem "8571" na saída; avisos de defeso e de troca de classificador; baseline pequeno, burst e new_entity limitados a "atenção" |
| **F4** apps | ✅ | MCPJam 7/7 em produção; validação visual feita pelo usuário (Desktop e claude.ai); basic-host ok |
| **F5** coerência | ✅ (v1) | Q575545 ago–set em ~2 s; calibração por tema **não reproduz** o UC-03 (E≈0,03–0,07); pesos provisórios |
| **SC-1/DS-2** resumos | ✅ | 6.332 resumos recuperados; de jun a ago não sobrou tema sem resumo |
| **B3** embeddings | ✅ parcial | 6.797 gerados (01/03 a 05/10 com resumo). A sobra (~1.245, que esperam resumo do B2) está no executor |

---

## 4. ⚙️ Processos em execução (locais, desacoplados da sessão)

> **Requisitos:** a máquina ligada, o gcloud logado e `/private/tmp` intacto. Um reboot no macOS limpa `/private/tmp` e mata os executores e os logs.
> **Pasta:** `SP=/private/tmp/claude-501/-Users-nitai-dev-destaquesgovbr/335dcec3-2035-416b-8cc8-21611b53f11a/scratchpad`. É o scratchpad da sessão antiga; a nova sessão terá outro, então use esse caminho absoluto.

| Executor | PID (snapshot) | Estado | O que faz |
|---|---|---|---|
| `$SP/backfill_runner.sh` | 748 | `waiting_d1` | 1) confirma que o DS-2 principal está zerado (já ok); 2) **a partir de 07/10 BRT (03:00Z)**, passada final do DS-2 para 06/10; 3) **B2** `--select null-theme --date-from 2026-06-01 --date-to 2026-10-07` (lotes de 500, 2 workers). Usa o governador de **16M tokens/dia** (cota 20M × 0,8, decisão do usuário); espera o dia UTC seguinte quando esgota; para no primeiro throttling ou em passada sem `ok` |
| `$SP/post_runner.sh` | 7855 | `waiting_b2` | Espera `backfill_runner.state` = `done` e então: **B3** da sobra (`--require-summary`, [01/03, 07/10), 3 workers) → **B4** (`typesense-maintenance-sync` incremental [01/03, 07/10]) → **BigQuery**: `DELETE` das linhas parciais de 29/06 e 30/06 (OK do usuário) → **64 execuções do DAG** `sync_pg_to_bigquery` (logical dates de 31/05 a 04/10, de 2 em 2 dias, run-id `backfill_fase25_<data>`) → conferência BigQuery × Postgres por dia UTC. Para no primeiro erro |

**Monitorar:**
```bash
SP=/private/tmp/claude-501/-Users-nitai-dev-destaquesgovbr/335dcec3-2035-416b-8cc8-21611b53f11a/scratchpad
cat $SP/backfill_runner.state $SP/post_runner.state
grep -E 'FIM|THROTTL|esgotado|vazia|sem ok|FALHA|CONFERÊNCIA' $SP/backfill_runner.log $SP/post_runner.log | tail -20
pgrep -fl 'backfill_runner|post_runner|reenrich_combined|backfill_embeddings'
```

**Se algum parar** (o estado fica `stopped` ou `failed`): leia o log, corrija e reinicie com `nohup $SP/<script>.sh >/dev/null 2>&1 & disown`. Os scripts são idempotentes e retomáveis: a seleção exclui o que já foi feito.
- **Atenção:** nunca edite um `.sh` que está rodando, porque o bash lê o arquivo incrementalmente. Mate o processo antes.
- **Já feito no BigQuery** (não repetir): 28/05 e 29/05 foram carregados no teste (248 e 274 linhas, iguais ao Postgres); 05/10 entrou pelo sync normal de 06/10.

**Helper de SQL somente leitura:** `$SP/ro_sql.sh` lê o SQL do stdin, roda em `BEGIN READ ONLY … ROLLBACK` com `default_transaction_read_only=on` e busca o secret via gcloud sem imprimi-lo.

---

## 5. 📅 Pendências com data

| Quando | Ação | Detalhe |
|---|---|---|
| diário até ~09/10 | Acompanhar os executores (§4) | Conferir também que o worker ao vivo não sofre throttling (logs do `destaquesgovbr-enrichment-worker`: `enrichment_model_unavailable`, `ThrottlingException`) |
| **24–27/10** | **Congelamento** (só hotfix) | Fim do defeso em 25/10 (2º turno) |
| **depois de 25/10** | **Reverter as 14 URLs temporárias de defeso do scraper** | Checklist no scraper#61 (miguellsfilho). Ver memória `project_dgb_defeso_eleitoral_2026` |
| 26/10 → 29/11 | Observação diária F2/F3 | O D2 (baseline pré-defeso no trending) liga sozinho em 26/10; o gobus entra na fase `recovery`. Conferir que `POST_BLACKOUT_RECOVERY` aparece e que as agências que voltaram viram `calendar_explained` |
| **a partir de 28/10** (evitar 02/11 e 20/11) | **Mergear o data-platform#204 (DP-A)** | Deploy de 4 workers, `composer-deploy-dags` e `postgres-docker-build`. Depois: conferir os logs dos workers e o `sync_facts` da manhã seguinte (janela de 1 dia) |
| 30/11 | Conferir que o D2 e a `recovery` desligaram | — |

---

## 6. Decisões

- **Tomadas:**
  - D0 (Haiku 4.5);
  - D2 (baseline pré-defeso de 26/10 a 29/11);
  - D4 (≥2 dias + `max_day_share`);
  - D5 (enums em inglês);
  - D7 (share-of-voice com topThemes);
  - Flesch inglês por ora;
  - governador de 16M/dia;
  - prioridade DS-2 → B2;
  - SC-1 opção (b) (republica sem tema);
  - remoção da <colaboradora externa>.
- **Pendentes, com o usuário:**
  - **D1:** `log1p` / limite do `agency_growth` no scorer do trending. O harness `research/trend-detection` já usa o código de produção; falta rodar o `evaluate.py`, que precisa de DATABASE_URL e scikit-learn.
  - **D3:** MOCK (4.600 artigos com summary `[MOCK]` e tema falso). Opções: re-enriquecer (~US$90, `reenrich_combined_window.py --select mock`) ou `UPDATE` com nulos, sempre seguido de `content_embedding=NULL`, B3 e B4. **A issue gobus-mcp#3 continua com o texto antigo (DELETE perigoso) e precisa ser reescrita.**
  - **D6:** re-enriquecer os 28 dias anteriores ao corte de classificador (25/09) para alinhar os baselines de tema.

---

## 7. Issues abertas nesta fase

| Issue | Tema |
|---|---|
| infra#216 | Métricas de log e alert policies para falhas silenciosas |
| data-platform#203 | Flesch pt-BR (Martins/1996) como chave nova |
| graphql-api#30 | Lockfile/pin de dependências (incidente Decimal) |
| graphql-api#31 | `newsBatchForBigquery`: datas str no asyncpg e janela BETWEEN (bloqueia o INF-2) |
| data-platform#205 | Teste de integração do BigQuery roda DDL em produção com ADC |
| data-platform#206 | Reindex do `entity_canonical` no Typesense antes de ~20/05 |
| data-platform#207 | Dedup do histórico do `fato_noticias` (2–6% em mar–mai) — destrutivo, exige OK |

**Candidatas a issue, ainda não abertas:**
- **INF-2:** religar o caminho GraphQL dos workers (allowlist de SA, `SERVICE_ACCOUNT_AUDIENCE`, `clients/` nos plugins do Composer).
- **Scraper:** re-enriquecer quando o `content_hash` muda (hoje o resumo fica defasado).
- **data-science:** `is_already_enriched` exigir tema e resumo (defesa extra).
- **Portal:** badge "novo" via `isNew`.
- **G2:** dona por cobertura dentro do defeso (estender o período da dona ao pré-defeso).
- **G3/F5:** excluir entidades de agência com QID (MDS, INSS…); calibrar a coerência com um conjunto rotulado.
- **Registry:** `agencyKey` errado (PGF → Fundação Joaquim Nabuco).
- **DLQ:** `dgb.news.scraped--enrichment-dlq` pode ter mensagens dos 503 de set/out; não reprocessar sem filtro.

Já existiam antes da fase e seguem abertas: gobus-mcp#3 (MOCK), infra#214 (DNS `dgb.app.gov.br`), streamlit-panorama-dgb#1–#4.

---

## 8. Higiene e estado local (não perder trabalho)

- **Checkout principal do gobus-mcp:** continua no branch velho `feature/fase2-analytics`, com arquivos não versionados.
  - `_plan/PLANO_FASE2_5.md`: **a versão com o §14 mais completo existe só aqui**, e o origin/main tem a versão do G1. Commitar a atualização num PR de docs.
  - Este `STATUS_FASE2_5.md`.
  - Também: `_plan/fase2_5/`, `_experiments/`, `docs/experimentos/`, `docs/deploy.md` modificado (errado) e `mkdocs.yml`.
  - **O `CLAUDE.md` desse checkout está desatualizado** e é o que o Claude Code carrega no contexto: diz `baseDailyAvg`, "3 resources", `"command": "python"` e que tools sempre devolvem Markdown. O correto é o de `origin/main` (`git show origin/main:CLAUDE.md`). Não confie nele até colocar o checkout em `main`.
  - Antes de trocar para `main`, confira: quase tudo já está em main pelo G1. Pendências de higiene que precisam de OK: tag no 7021868, reset do `main` local, apagar branches remotos já mergeados.
- **Worktrees desta fase**, em `<repo>/.claude/worktrees/`. **NÃO remover enquanto os executores rodam:**
  - `data-science/.claude/worktrees/ds2-run` (detached em origin/main; usado pelo backfill_runner);
  - `embeddings/.claude/worktrees/fase2.5-backfill-script` (usado pelo post_runner).

  Os demais estão mergeados e podem ser removidos depois:
  - infra `fase2.5-enrichment-model-workers-pg`;
  - clipping `fase2.5-digest-fences`;
  - data-platform `fase2.5-trending-entities`;
  - graphql-api `fase2.5-trending-sentimento-timeline` e `hotfix-pct-float`;
  - gobus-mcp `fase2.5-higiene`, `fase2.5-analytics` e `fase2.5-apps-coerencia`;
  - data-science `fase2.5-enrichment-observabilidade` e `fase2.5-backfill-resumos`;
  - scraper `fase2.5-rescrape-preserva-resumo`.

  Mantenha o data-platform `fase2.5-graphql-workers` até o merge do #204.

  Os worktrees `agent-*` e `dashboard-panorama` (Dropbox) **não são desta fase**; não mexa neles.
- `.git/info/exclude` recebeu `.claude/worktrees/` (e `.venv/`, onde preciso) em vários repos. É local e inócuo.

---

## 9. Gotchas de ambiente (essenciais para a nova sessão)

- **Python:**
  - `python` é só alias do zsh; use caminhos absolutos dos venvs (gobus: `gobus-mcp/.venv/bin/python3.12`; venv misto 3.12/3.13).
  - O `pip` global aponta para um índice privado; nos venvs use `PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple`.
  - **Poetry está quebrado** (`python` não encontrado); use `pip install -e .`.
- **`gh pr edit --body-file` falha em silêncio** (deprecação do Projects classic). Use `gh api -X PATCH repos/<org>/<repo>/pulls/<n> -F body=@arquivo`.
- **API de embeddings:** exige IAM do Cloud Run (identity token) além da `X-API-Key`.
- **Commits:** sem `Co-Authored-By` em gobus-mcp, graphql-api, infra, clipping e scraper (CLAUDE.md); com ele em data-platform, data-science e embeddings. Português, prefixos `fix:`, `feature:`, `test:`, `chore:` e `docs:`, TDD com red → green.
- **Regras:**
  - nunca rodar terraform local;
  - nunca usar gcloud mutante sem OK;
  - nunca enviar mutations GraphQL em sondas (houve um incidente, recusado com FORBIDDEN);
  - nunca editar `~/.claude.json`, que ainda aponta o "gobus" para `/sse` e é ajuste manual do usuário.
- **Ações que exigem OK explícito do usuário:** merges, backfills, `gh workflow run`, comentários e edições em PR/issue, operações destrutivas no banco ou no BigQuery, leitura de secrets.
- **Airflow 3 (Composer 3.1):** `logical_date` = horário da execução. Para disparos manuais: `gcloud composer environments run destaquesgovbr-composer --location=southamerica-east1 --project=inspire-7-finep dags trigger -- <dag> --logical-date <ISO> --run-id <id>`.
- O MCP `gobus` desta workspace roda em stdio pelo checkout principal (branch velho). Para testar o código de main, use o Cloud Run `/mcp` ou um worktree.

---

## 10. Próximos passos sugeridos (nova sessão)

1. Rodar o bloco "Monitorar" do §4 e confirmar que os dois executores estão vivos e progredindo.
2. Quando o `post_runner` chegar a `done`:
   - ler a linha `CONFERÊNCIA` (dias faltando, duplicatas, contagens diferentes);
   - conferir `SELECT count(*) FROM news WHERE summary IS NULL AND published_at >= '2026-06-01'`;
   - conferir os temas de 25/09 a 05/10;
   - conferir os embeddings.
3. Commitar o `PLANO_FASE2_5.md` (§14) e este `STATUS` num PR de docs no gobus-mcp, redigindo IPs e e-mails.
4. Reescrever a issue gobus-mcp#3 (MOCK) e levar D1, D3 e D6 ao usuário.
5. Agenda do §5: reverter as URLs de defeso depois de 25/10; merge do DP-A a partir de 28/10; observação do D2 até 30/11.
6. Higiene (§8), com OK: limpar worktrees e branches; colocar o checkout principal do gobus em `main`.
