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
                       "metric": {"rowsTotal": 50, "rowsLastRun": 2, "rowsLegacyFloor": 50, "distinctRuns": 32, "ageHours": 3.46}}
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

Cada fonte não-ok vira um aviso em `notices` (`THEMES_UNCLASSIFIED`, `READABILITY_UNAVAILABLE`, `SENTIMENT_UNAVAILABLE`, `TRENDING_ENTITIES_STALE`). Uma consulta que falha deixa só a sua chave `unavailable`, com o erro na mensagem.

Atraso de indexação (Typesense) e atividade das agências entram no G2.
