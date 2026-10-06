# Plano: Correção de Bugs de Features

Data: 2026-06-29

---

## Bug 1: topArticles vazio em trendingThemes

### Diagnóstico

Arquivo-chave: `graphql-api/src/graphql_api/schema/resolvers/analytics.py`

O resolver `trending_themes()` (linha 176–241) constrói a lista de temas crescentes via duas queries de facets no Typesense (janela `window_days` e baseline `baseline_days`). Para cada tema que ultrapassa o `growth_threshold`, instancia um `TrendingThemeResult` — mas na **linha 232** o campo `top_articles` está **explicitamente hardcoded como lista vazia**:

```python
results.append(TrendingThemeResult(
    theme_label=theme,
    theme_code=None,
    window_count=w_count,
    baseline_daily_avg=round(baseline_daily, 3),
    growth_score=round(growth, 3),
    top_articles=[],   # ← nunca implementado
))
```

O tipo `ArticleSummary` (em `graphql-api/src/graphql_api/schema/types/analytics.py`, linha 67–73) está corretamente definido com os campos `unique_id`, `title`, `agency_name`, `published_at`, `trending_score` — mas o código que o popula simplesmente não foi escrito.

A coleção Typesense `news` tem os campos correspondentes disponíveis: `unique_id` (= document `id`), `title`, `agency` (agency_name), `published_at` (Unix timestamp int64), `trending_score` (float, ordenável). Confirmar via `data-platform/src/data_platform/typesense/collection.py` linhas 19–20 e 137.

### Causa raiz

Implementação incompleta: o campo `top_articles` no tipo GraphQL foi criado (schema correto), mas o código que busca os artigos em Typesense para cada tema trending não foi escrito. Não é um bug de JOIN ou schema — é código ausente.

### Correção proposta

Em `graphql-api/src/graphql_api/schema/resolvers/analytics.py`, após ordenar `results` e truncar com `[:limit]`, adicionar uma query Typesense por tema para popular `top_articles`. O esquema é idêntico ao das queries de facets já feitas no mesmo resolver.

**Passo a passo:**

1. Após a linha `return results[:limit]`, transformar o fluxo: calcular `results[:limit]` em uma variável, depois preencher `top_articles` antes de retornar.

2. Para cada tema no top-limit, fazer uma query Typesense:

```python
TOP_ARTICLES_PER_THEME = 5

final_results = results[:limit]
for result in final_results:
    # Typesense: artigos do tema na janela recente, ordenados por trending_score desc
    safe_label = result.theme_label.replace('"', '\\"')
    theme_filter = (
        _ts_filter(window_days)
        + agency_filter
        + f' && theme_1_level_1_label:="{safe_label}"'
    )
    art_resp = ts.client.collections["news"].documents.search({
        "q": "*",
        "per_page": TOP_ARTICLES_PER_THEME,
        "filter_by": theme_filter,
        "sort_by": "trending_score:desc,published_at:desc",
        "include_fields": "id,unique_id,title,agency,published_at,trending_score",
    })
    hits = art_resp.get("hits", [])
    result.top_articles = [
        ArticleSummary(
            unique_id=h["document"].get("unique_id") or h["document"].get("id", ""),
            title=h["document"].get("title") or "",
            agency_name=h["document"].get("agency"),
            published_at=(
                datetime.fromtimestamp(
                    h["document"]["published_at"], tz=timezone.utc
                ).isoformat()
                if h["document"].get("published_at")
                else None
            ),
            trending_score=h["document"].get("trending_score"),
        )
        for h in hits
    ]
return final_results
```

3. Importar `ArticleSummary` no topo do resolver (já importado via `analytics` types — confirmar que está na lista de imports em `analytics.py` linha 6–16; se não estiver, adicionar).

**Custo de latência**: até `limit` queries adicionais ao Typesense (default 10). Typesense local é sub-ms em geral; aceitável.

**Fallback seguro**: se a query de artigos falhar (timeout, erro), envolver em `try/except` e manter `top_articles=[]` — o comportamento atual é a degradação graciosa.

**Como testar**:
```bash
# graphql-api local (make dev)
curl -sf -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ trendingThemes(windowDays:7, baselineDays:28, growthThreshold:1.0, limit:3) { themeLabel topArticles { uniqueId title agencyName trendingScore } } }"}'
# Esperado: topArticles com 1–5 artigos por tema (antes vinha [])
```

---

## Bug 2: avgFleschScore null em artigos recentes (junho/2026)

### Diagnóstico do pipeline

O `readability_flesch` é computado pela função `compute_readability_flesch()` em `data-platform/src/data_platform/workers/feature_worker/features.py` (linha 56–63), chamada por `compute_all()` (linha 245–273). O resultado é gravado em `news_features.features` como JSONB (`{"readability_flesch": <float>}`).

O pipeline é **event-driven**: quando um artigo é scrapeado, o tópico Pub/Sub `dgb.news.enriched` dispara o Cloud Run `feature-worker`. O handler (`feature_worker/handler.py`, `handle_feature_computation()`) busca o artigo, chama `compute_all()`, e chama `upsert_features()` no Postgres.

A query SQL em `graphql-api/src/graphql_api/datasources/postgres.py`, constante `_AGENCY_ANALYTICS_SQL` (linha 326–343), usa:
```sql
AVG((nf.features->>'readability_flesch')::float) AS avg_readability_flesch
```
via `LEFT JOIN news_features nf ON n.unique_id = nf.unique_id`. O SQL é **correto** — o problema é ausência de dados, não lógica de query.

Há dois sub-casos possíveis:

**Sub-caso A** — artigos de junho/2026 **não têm linha em `news_features`**: o feature-worker não processou o evento Pub/Sub (worker estava down, mensagem expirou, erro não-ACK). O `LEFT JOIN` retorna NULL para toda a linha de features, logo `avg_readability_flesch` = NULL.

**Sub-caso B** — artigos têm linha em `news_features` mas sem a chave `readability_flesch`: o worker processou, mas o artigo tinha `content=NULL` ou menos de 10 palavras no momento do processamento (ver `compute_readability_flesch()` linha 57: `if not content or len(content.split()) < 10: return None`). Nesse caso `flesch is None` e a feature não é inserida (linha 269–271 de `compute_all()`).

Para distinguir: rodar SQL diagnóstico:
```sql
-- Quantos artigos de jun/2026 têm linha em news_features?
SELECT
    COUNT(*) FILTER (WHERE nf.unique_id IS NULL) AS sem_features,
    COUNT(*) FILTER (WHERE nf.unique_id IS NOT NULL AND nf.features ? 'readability_flesch') AS com_flesch,
    COUNT(*) FILTER (WHERE nf.unique_id IS NOT NULL AND NOT nf.features ? 'readability_flesch') AS sem_flesch_mas_com_features
FROM news n
LEFT JOIN news_features nf ON n.unique_id = nf.unique_id
WHERE n.published_at >= '2026-06-01'
  AND n.published_at < '2026-07-01';
```

### Causa raiz

Com base no padrão observado (feature_worker é event-driven, sem reprocessamento automático), a causa mais provável é o **Sub-caso A**: artigos de junho/2026 sem entrada em `news_features` porque o worker não processou os eventos Pub/Sub correspondentes. Pode ter havido um gap de deploy, erro de Pub/Sub, ou os artigos foram inseridos por um caminho que não emite `dgb.news.enriched`.

O Sub-caso B é possível para artigos com conteúdo curto, mas improvável como causa *universal* de junho inteiro.

Não há DAG Airflow de backfill de Flesch — a única DAG relacionada ao feature_worker é evento-by-evento via Pub/Sub. As DAGs de Airflow (`compute_trending`, `aggregate_engagement`) operam sobre features *já existentes*, não as computam.

### Correção proposta

**Imediata (diagnóstico):** Rodar o SQL acima contra o banco de produção via `make bootstrap-env && psql $DATABASE_URL` para confirmar qual sub-caso está ocorrendo.

**Backfill (solução):** Criar e rodar um script de backfill análogo ao existente `data-platform/scripts/backfill_annotations_window.py`, mas para features básicas (incluindo Flesch). Modelo:

```python
#!/usr/bin/env python3
"""
Backfill de features básicas (readability_flesch, word_count, etc.) para janela.

Processa artigos de jun/2026 sem readability_flesch em news_features.
Idempotente: faz UPSERT merge via ||.

Uso:
    DATABASE_URL=... python scripts/backfill_features_window.py \
        --date-from 2026-06-01 --date-to 2026-07-01 --limit 50000
"""
import argparse, os, sys, time
import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from data_platform.workers.feature_worker.features import compute_all

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", default="2026-06-01")
    ap.add_argument("--date-to",   default="2026-07-01")
    ap.add_argument("--limit",     type=int, default=50000)
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur  = conn.cursor()

    # Seleciona artigos sem readability_flesch (sub-caso A: sem linha; sub-caso B: linha sem a chave)
    cur.execute("""
        SELECT n.unique_id, n.content, n.image_url, n.video_url, n.published_at
        FROM news n
        LEFT JOIN news_features nf ON nf.unique_id = n.unique_id
        WHERE n.published_at >= %s::timestamptz
          AND n.published_at <  %s::timestamptz
          AND (nf.unique_id IS NULL OR NOT nf.features ? 'readability_flesch')
        ORDER BY n.published_at DESC
        LIMIT %s
    """, (args.date_from, args.date_to, args.limit))

    rows = cur.fetchall()
    print(f"artigos para backfill: {len(rows)}")

    t0 = time.time()
    for i, (uid, content, image_url, video_url, published_at) in enumerate(rows, 1):
        article = {
            "content":     content,
            "image_url":   image_url,
            "video_url":   video_url,
            "published_at": published_at,
        }
        features = compute_all(article)
        if not features:
            continue
        cur.execute("""
            INSERT INTO news_features (unique_id, features, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (unique_id) DO UPDATE SET
              features   = news_features.features || EXCLUDED.features,
              updated_at = NOW()
        """, (uid, Json(features)))

        if i % 500 == 0:
            conn.commit()
            elapsed = time.time() - t0
            print(f"  {i}/{len(rows)}  ({elapsed:.0f}s, {i/elapsed:.0f} art/s)")

    conn.commit()
    print(f"FIM: {len(rows)} artigos em {time.time()-t0:.0f}s")
    conn.close()

if __name__ == "__main__":
    main()
```

Salvar em `data-platform/scripts/backfill_features_window.py`.

**Executar** (substituindo a connection string pelo secret real):
```bash
cd data-platform
source .venv/bin/activate   # ou poetry shell
DATABASE_URL=$(gcloud secrets versions access latest \
    --secret=govbrnews-postgres-connection-string \
    --project=inspire-7-finep) \
python scripts/backfill_features_window.py \
    --date-from 2026-06-01 \
    --date-to   2026-07-01 \
    --limit      100000
```

**Prevenção:** Verificar nos logs do Cloud Run `feature-worker` (Logs Explorer, `resource.type="cloud_run_revision"`, serviço `feature-worker`) se houve erros em junho/2026. Se confirmar gap de deployment, pode ser necessário também verificar a trigger Pub/Sub e reprocessar via re-publicação dos eventos (ou o backfill acima substitui isso).

**Como verificar correção (após backfill):**
```sql
-- Deve retornar avg_readability_flesch != NULL para jun/2026
SELECT
    DATE_TRUNC('week', n.published_at) AS semana,
    COUNT(*) AS artigos,
    AVG((nf.features->>'readability_flesch')::float) AS avg_flesch
FROM news n
JOIN news_features nf ON n.unique_id = nf.unique_id
WHERE n.published_at >= '2026-06-01'
GROUP BY 1 ORDER BY 1;
```

---

## Ordem de execução sugerida

**1. Bug 1 (topArticles) — fazer primeiro**

- Mudança de código pura (graphql-api), sem dependência de dados
- Escopo isolado: um resolver, um arquivo
- Rollback simples: reverter o PR
- Resultado imediato e verificável com um `curl`
- Impacto alto no Gobus: as tools `detect_trends` e `get_agency_summary` passam a retornar artigos representativos por tema

**2. Bug 2 (Flesch backfill) — fazer segundo**

- Requer diagnóstico SQL primeiro (confirmar sub-caso A vs B)
- Backfill leva alguns minutos contra o banco de produção (Cloud SQL via `DATABASE_URL` do secret)
- Não requer redeploy — é um script pontual
- Após o backfill, os valores aparecem imediatamente nas queries `agencyAnalytics` via graphql-api (que lê diretamente de Postgres)
- Não requer sync no Typesense: o campo `readability_flesch` no Typesense (`data-platform/src/data_platform/typesense/collection.py`) é opcional e não é consultado por `_AGENCY_ANALYTICS_SQL`; só `news_features` é relevante aqui
