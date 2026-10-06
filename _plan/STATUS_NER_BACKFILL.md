# Status: Backfill NER v2 (Canonicalização de Entidades)

> **Data de referência:** 2026-06-29

---

## Cobertura atual de entidades

Os dados abaixo são da última medição verificada nos arquivos do projeto (psql read-only, 2026-06-17/18, pós-backfill iniciado):

| Métrica | Valor |
|---|---|
| `news` total | 335.268 |
| Com features | 26.925 (8,0%) |
| Com entidades NER (qualquer versão) | 21.463 (6,4%) — maioria legado Haiku 3 |
| Re-NERados com `ner-v1` (Sonnet 4.6) | 4.732 — janela 2026-05-12→06-17 |
| Com `canonical_id` | 3.909 (quase todos via gazetteer, não LLM) |
| `entity_registry_seen` pending | 20.724 (pending) / 118 (resolved) / 65 (needs_review) — estado 2026-06-17 |
| Grafo Neo4j (estado 2026-06-18, pós backfill ativo) | **1.085 nós** / **1.964 arestas** |
| Typesense `entity_canonical` (2026-06-18) | **1.079** distintos |

**Janela de dados NER v1:** artigos com NER novo (Sonnet 4.6, taxonomia Eventos/Políticas/QID Wikidata) cobrem principalmente 2026-05-12 em diante — a fatia de validação de ~1 mês processada manualmente antes do backfill ser orquestrado.

O backfill orquestrado foi ativado em **2026-06-18**. A medição do grafo mostra crescimento real (242→1.085 nós), confirmando que o processo estava em execução nessa data. Não há medição posterior disponível nos arquivos locais — o estado atual exato (2026-06-29) só pode ser obtido via consulta direta ao banco ou logs do Composer.

---

## Job de backfill

Existem **dois jobs distintos**, ambos implementados e deployados:

### Job 1 — NER Backfill (`destaquesgovbr-ner-backfill`)

- **Lógica:** `data-science/scripts/backfill_ner_corpus.py` (repo data-science)
- **Imagem Docker:** `docker/ner-job/` (repo data-science)
- **Orquestração:** DAG Airflow `ner_backfill`
  - Arquivo: `data-platform/src/data_platform/dags/ner_backfill.py` (idêntico ao deployed em `airflow/dags/ner_backfill.py`)
  - Schedule: `"0 2-23/6 * * *"` — 4×/dia nos horários 02:00, 08:00, 14:00, 20:00 UTC
  - Defasado 2h do canon (que roda 00:00, 06:00, 12:00, 18:00)
- **O que faz:** seleciona `news` SEM `news_llm_raw` task='ner' prompt_version='ner-v1' (~314k artigos históricos sem NER), roda o NER via Bedrock (Sonnet 4.6), grava em `news_features`, popula `entity_registry_seen`
- **Args padrão:** `--limit 5000 --order desc --workers 10`
- **Teto:** governador de cota (ledger `llm_daily_usage`); `BACKFILL_QUOTA_FRACTION=1.0` (NER usa o saldo do dia após o canon ter usado 80%)

### Job 2 — Canonicalization Backfill (`destaquesgovbr-canon-backfill`)

- **Lógica:** `data-science/src/news_enrichment/canonicalization_job.py` (repo data-science)
- **Imagem Docker:** `docker/canon-job/` (repo data-science)
- **Orquestração:** DAG Airflow `canonicalize_backfill`
  - Arquivo: `data-platform/src/data_platform/dags/canonicalize_backfill.py` (idêntico ao deployed)
  - Schedule: `"0 */6 * * *"` — 4×/dia (00:00, 06:00, 12:00, 18:00 UTC)
- **O que faz:** percorre `entity_registry_seen` com formas pendentes, resolve via gazetteer → Wikidata → LLM (Sonnet 4.6), grava `canonical_id`
- **Args padrão:** `--since 2018-01-01 --limit 5000 --workers 10`
- **Teto:** `BACKFILL_QUOTA_FRACTION=0.8` (80% da cota diária de 6,0M tokens Sonnet 4.6)

---

## Bloqueio: infra#198

O `infra#198` mencionado na memória do projeto foi o PR que setou `NER_MODEL_ID=us.anthropic.claude-sonnet-4-6` e `CANON_MODEL_ID=us.anthropic.claude-opus-4-6-v1` no Terraform. **Este PR foi mergeado em 2026-06-11** (conforme registro na memória: "infra#198 mergeado").

Portanto, **infra#198 não é mais um bloqueio** — foi resolvido antes do backfill orquestrado ser ativado.

Os PRs relevantes da infraestrutura de backfill são:
- `infra#200` — Neo4j e Fase 6
- `infra#204` — aceleração do backfill (quota $50/dia, 10 workers, timeout 2h)
- `infra#205` — redução do teto de 9,05M para 6,0M tokens/dia (após ThrottlingException confirmado empiricamente em 2026-06-18)

---

## Variáveis de modelo

As variáveis estão definidas em `infra/terraform/variables.tf` e são aplicadas via Terraform aos Cloud Run Jobs:

| Variável | Valor em prod (default) | Onde usada |
|---|---|---|
| `NER_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | Job `ner-backfill` |
| `CANON_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | Job `canon-backfill` |
| `BEDROCK_DAILY_TOKEN_QUOTA` | `{"us.anthropic.claude-sonnet-4-6":6000000}` | Ambos os jobs |
| `BACKFILL_QUOTA_FRACTION` | `"0.8"` | Job canon (80% do teto diário) |
| `NER_BACKFILL_QUOTA_FRACTION` | `"1.0"` | Job NER (100%; efetivamente recebe os ~20% restantes) |

**Nota sobre Opus:** `us.anthropic.claude-opus-4-8` deu `AccessDeniedException` na conta AWS <AWS-ACCOUNT-ID>. O config atual usa Sonnet 4.6 para ambos (NER e canonicalização), o que simplifica o pool de cota (um único pool compartilhado por worker ao vivo + NER backfill + canon backfill).

As variáveis estão **configuradas no Terraform** e não há override em `terraform.auto.tfvars` ou `terraform.tfvars` — os defaults de `variables.tf` são os valores de produção.

---

## Estado: rodando / bloqueado / não iniciado

**Estado: RODANDO** (desde 2026-06-18).

Evidências factuais:
1. Os dois DAGs (`ner_backfill`, `canonicalize_backfill`) estão no Composer com schedule ativo (4×/dia cada)
2. Os Cloud Run Jobs (`destaquesgovbr-ner-backfill`, `destaquesgovbr-canon-backfill`) estão provisionados via Terraform (PRs #204 + #205 mergeados)
3. O grafo cresceu de 242 para 1.085 nós entre 2026-06-17 e 2026-06-18, confirmando execução real
4. A migração 023 (`llm_daily_usage`) foi aplicada em prod — o governador de cota tem onde registrar consumo
5. As Airflow Variables (`canon_job_name`, `ner_job_name`, `cloud_run_jobs_region`) são provisionadas via Secret Manager no Terraform

**Limitante ativo:** a cota diária do AWS Bedrock (Sonnet 4.6 cross-region on-demand) é de ~6,0M tokens/dia (~$33/dia). Com ~314k artigos sem NER e ~20k+ formas pendentes de canonicalização, o backfill é um **grind de semanas** dentro dessa cota — o que é esperado pelo design (resumível, diário).

---

## Próximos passos

Para monitorar o progresso real (estado 2026-06-29):

1. **Medir cobertura atual** via psql read-only (`<IP-CLOUD-SQL>`, banco `govbrnews`):
   ```sql
   -- Artigos re-NERados com modelo novo
   SELECT COUNT(*) FROM news_llm_raw WHERE task='ner' AND prompt_version='ner-v1';
   
   -- Formas pendentes de canonicalização
   SELECT status, COUNT(*) FROM entity_registry_seen GROUP BY status;
   
   -- Consumo de cota hoje
   SELECT * FROM llm_daily_usage WHERE day = CURRENT_DATE;
   
   -- Progresso do grafo
   SELECT COUNT(*) FROM entity_registry WHERE entity_id IS NOT NULL;
   ```

2. **Verificar execuções no Composer:** confirmar que os DAGs `ner_backfill` e `canonicalize_backfill` aparecem como `success` nas últimas runs (UI do Cloud Composer ou `gcloud composer environments run`).

3. **Verificar imagens nos Cloud Run Jobs:** confirmar que as imagens dos jobs deixaram de ser o placeholder `us-docker.pkg.dev/cloudrun/container/hello:latest` e passaram a ser as imagens reais do CI (requer acesso ao GCP Console ou `gcloud run jobs describe`).

4. **Dedup ORG pendente:** o threshold de ORG foi corrigido para 0.85 (data-science#32/33/34/35), mas a fusão manual de near-duplicatas pode continuar gerando ruído. Monitorar `entity_registry` por clusters de nomes similares.

5. **Typesense re-sync:** após ganho expressivo em `canonical_id`, reindexar via `typesense-maintenance-sync.yaml` (incremental, por date range) para que o portal reflita as novas entidades.

6. **Cleanup de nós stale no Neo4j:** resolvido em data-platform#186 (18/jun) — `sync_graph_to_neo4j` já faz `DETACH DELETE` de nós ausentes do Postgres ao fim de cada sync.
