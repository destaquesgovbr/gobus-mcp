# gobus://readability-report

Relatório **JSON** de legibilidade (Flesch pt-BR, Martins et al., 1996) das agências ativas, com gap até a meta, janela efetiva e cobertura.

**URI:** `gobus://readability-report` · **MIME:** `application/json`
**Fonte:** as 20 agências mais ativas dos últimos 90 dias (`topAgencies`, via catálogo) e `agencyAnalytics(MONTH)` da janela de 90 dias fechada em ontem.

## Formato (`schemaVersion` 3)

```json
{
  "schemaVersion": 3,
  "generatedAt": "2026-10-06T00:30:00+00:00",
  "referenceDate": "2026-10-05",
  "scale": "flesch_ptbr_martins1996",
  "scaleLabel": "Flesch pt-BR (Martins et al., 1996), limitado a 0–100",
  "scaleFallback": false,
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
  "dataStatus": [{"key": "readability", "status": "unavailable", "since": null, "message": "…", "metric": {}}],
  "notices": [],
  "agencies": [
    {
      "agencyKey": "agencia_brasil", "agencyName": "Agência Brasil", "isRepublisher": true,
      "articleCount": 2576, "articlesWithData": 2576,
      "flesch": 15.6, "fleschRaw": 15.6, "band": "very_hard",
      "gapToTarget": -34.4, "avgWordCount": 470.3
    }
  ]
}
```

## Regras

- **Escala:** `scale` = `flesch_ptbr_martins1996` (média do `avgReadabilityFleschPtbr` pelos `readabilityFleschPtbrCount` artigos que o têm), com as faixas de Martins (`very_hard` 0–25, `hard` 25–50, `easy` 50–75, `very_easy` 75–100). Sem o pt-BR, a fórmula inglesa do `textstat` (`flesch_en_textstat`), com `scaleFallback: true` e o aviso `READABILITY_LEGACY_SCALE` em `notices`.
- **Mudança do `schemaVersion` 3:** `flesch`/`fleschRaw` substituem `avgReadabilityFlesch`/`avgReadabilityFleschRaw` (nomes da escala inglesa); as chaves de `band` passaram a ser as de Martins (`easy`/`very_easy` no lugar de `medium`/`easy`).
- **Nulo continua nulo:** agência sem Flesch tem `flesch` e `gapToTarget` `null` (nunca 0.0) e vai para o fim da lista.
- **Janela efetiva:** se o Flesch parou antes do fim da janela pedida, os valores vêm de uma janela do mesmo tamanho terminando no último mês com dado (`windowShifted`, `note`). `coverage` e `dataStatus` descrevem a janela **pedida**.
- `flesch` é limitado a 0–100; `fleschRaw` é a média bruta (pode sair de 0–100).
- `agencies` em ordem decrescente de Flesch.
