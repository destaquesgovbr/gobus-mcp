# gobus://readability-report

Relatório **JSON** de legibilidade (Flesch) das agências ativas, com gap até a meta, janela efetiva e cobertura.

**URI:** `gobus://readability-report` · **MIME:** `application/json`
**Fonte:** as 20 agências mais ativas dos últimos 90 dias (`topAgencies`, via catálogo) e `agencyAnalytics(MONTH)` da janela de 90 dias fechada em ontem.

## Formato (`schemaVersion` 2)

```json
{
  "schemaVersion": 2,
  "generatedAt": "2026-10-06T00:30:00+00:00",
  "referenceDate": "2026-10-05",
  "scale": "flesch_en_textstat",
  "targetFlesch": 50,
  "bands": [{"key": "very_hard", "label": "muito difícil", "lower": 0.0, "upper": 25.0}, "…"],
  "requestedWindow": {"start": "2026-07-07", "end": "2026-10-04", "days": 90},
  "effectiveWindow": {"start": "2026-04-02", "end": "2026-06-30", "days": 90},
  "windowShifted": true,
  "note": "dados até 06/2026",
  "coverage": {
    "periodsTotal": 4, "periodsWithData": 0, "articlesTotal": 9081,
    "articlesInPeriodsWithData": 0, "lastPeriodWithData": "2026-06-01 00:00:00+00"
  },
  "dataStatus": [{"key": "readability", "status": "unavailable", "since": "2026-06-30", "message": "…", "metric": {}}],
  "agencies": [
    {
      "agencyKey": "agencia_brasil", "agencyName": "Agência Brasil", "isRepublisher": true,
      "articleCount": 2576, "articlesWithData": 2576,
      "avgReadabilityFlesch": 33.6, "avgReadabilityFleschRaw": 33.6, "band": "hard",
      "gapToTarget": -16.4, "avgWordCount": 470.3
    }
  ]
}
```

## Regras

- **Nulo continua nulo:** agência sem Flesch tem `avgReadabilityFlesch` e `gapToTarget` `null` (nunca 0.0) e vai para o fim da lista.
- **Janela efetiva:** se o Flesch parou antes do fim da janela pedida, os valores vêm de uma janela do mesmo tamanho terminando no último mês com dado (`windowShifted`, `note`). `coverage` e `dataStatus` descrevem a janela **pedida**.
- `avgReadabilityFlesch` é limitado a 0–100; `avgReadabilityFleschRaw` é a média bruta (escala inglesa, pode ser negativa).
- `agencies` em ordem decrescente de Flesch.
