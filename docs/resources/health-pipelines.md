# gobus://health/pipelines

Saúde das fontes de dados que alimentam as tools, em **JSON**. Use antes de interpretar ausências ("nenhum tema em alta", "legibilidade indisponível").

**URI:** `gobus://health/pipelines` · **MIME:** `application/json`

## Formato (`schemaVersion` 2)

```json
{
  "schemaVersion": 2,
  "checkedAt": "2026-10-05T21:28:07-03:00",
  "referenceDate": "2026-10-05",
  "calendar": {"phase": "blackout", "label": "Defeso eleitoral 2026", "blackoutEnd": "2026-10-25", "daysToEnd": 20, "…": "…"},
  "status": "unavailable",
  "pipelines": {
    "themes": {"key": "themes", "status": "unavailable", "since": "2026-09-26",
               "message": "Temas: indisponível — 0% dos artigos dos últimos 7 dias com tema (0 de 915) (desde 26/09/2026)",
               "metric": {"classified": 0, "total": 915, "ratio": 0.0, "days": 7}},
    "readability": {"key": "readability", "status": "unavailable", "since": "2026-06-30", "…": "…"},
    "sentiment_analytics": {"key": "sentiment_analytics", "status": "unavailable", "metric": {"pctPositive": 0.0, "…": "…"}},
    "entity_ranking": {"key": "entity_ranking", "status": "degraded",
                       "message": "Ranking de entidades em alta: degradado — 50 de 50 linhas no piso antigo (baseline zero); 32 execuções misturadas",
                       "metric": {"rowsTotal": 50, "rowsLastRun": 2, "rowsLegacyFloor": 50, "distinctRuns": 32, "ageHours": 3.46}},
    "indexing_lag": {"key": "indexing_lag", "status": "unavailable",
                     "message": "Indexação (Typesense): indisponível — 71 de 172 artigos de 05–06/10 (UTC) no Typesense (41%); faltam 101",
                     "metric": {"indexed": 71, "stored": 172, "missing": 101, "ratio": 0.413}},
    "agency_activity": {"key": "agency_activity", "status": "ok",
                        "message": "Atividade das agências: ok — 156 agências de 06/06/2026 a 04/10/2026; 45 sem publicar há ≥14 dias; 17 retomadas",
                        "metric": {"agencies": 156, "silenced": 45, "resumed": 17, "days": 121}}
  },
  "agencyActivity": {
    "silenced": [{"key": "gestao", "name": "Ministério da Gestão e da Inovação em Serviços Públicos", "silentSince": "2026-07-04", "lastActive": "2026-07-03"}, "…"],
    "resumed": [{"key": "…", "name": "…", "resumedOn": "2026-09-30"}, "…"]
  },
  "notices": [{"code": "THEMES_UNCLASSIFIED", "severity": "error", "message": "…", "since": "2026-09-26", "affects": ["themes"]}]
}
```

## Chaves e regras de status

Status por fonte: `ok | degraded | unavailable`; `status` geral = o pior. A detecção é sempre **dinâmica** (na própria resposta da API); `since` é só uma dica de início para incidentes conhecidos.

| Chave | Medida | `unavailable` | `degraded` |
|-------|--------|---------------|------------|
| `themes` | Σ `topThemes` ÷ `analyticsKpis.total`, últimos 7 dias | < 50% classificados | < 80% |
| `readability` | fração de artigos (5 agências mais ativas, 7 dias fechados) em linhas com `avgReadabilityFlesch` — **nulo não conta como dado** | < 10% | < 80% |
| `sentiment_analytics` | fração com `avgSentimentScore` não nulo; `pctPositive` (fração 0..1) só como métrica, porque vem 0.0 sem dado | < 10% | < 80% |
| `entity_ranking` | `trendingEntities(50)`: linhas no piso antigo (`volumeRatio/windowCount ≥ 100`), execuções misturadas (`computedAt` espalhado), idade da última execução | vazio ou última execução > 7 dias | linhas legadas, execuções misturadas ou idade > 13 h |
| `indexing_lag` | artigos do dia D (UTC) no Typesense (`articles{found}`) ÷ artigos do mesmo dia no Postgres (soma do `agencyAnalytics` DAY de todas as agências, sem duplicatas). Com menos de 20 artigos em D (começo do dia UTC), a amostra vira D−1..D. Faltar até 5 artigos não conta como atraso | < 50% indexados | < 90% |
| `agency_activity` | snapshot `agencyAnalytics` DAY das 156 agências (D−90 a D−1; no defeso e na recuperação, desde 28 dias antes do defeso), cache de 6 h. Lista as **silenciadas** (≥ 14 dias sem publicar até D−1) e as **retomadas** (voltaram depois de um silêncio de ≥ 14 dias, nos últimos 35 dias) no bloco `agencyActivity` | falha da consulta (`agencyActivity: null`) | — |

Cada fonte não-ok vira um aviso em `notices` (`THEMES_UNCLASSIFIED`, `READABILITY_UNAVAILABLE`, `SENTIMENT_UNAVAILABLE`, `TRENDING_ENTITIES_STALE`, `INDEXING_LAG`). Uma consulta que falha deixa só a sua chave `unavailable`, com o erro na mensagem.

O atraso de indexação é medido no dia D, e não em D−1, porque o sync diário completa D−1 e esconderia o tempo real parado. O `calendar` traz `silencedAgencies` e `resumedAgencies` do snapshot de atividade, que é o mesmo cache usado por `gobus_detect_anomalies` e `gobus_forecast_trends`.
