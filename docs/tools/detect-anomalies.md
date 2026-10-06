# detect_anomalies

Detector de anomalias comunicacionais: **picos sustentados** de temas (presentes em duas janelas) e **cobertura concentrada** de entidades (alto volume relativo coberto por poucas agências).

!!! warning "Reescrita na Fase 2.5 (G2)"
    O comportamento descrito aqui é o atual. O G2 reescreve a tool com share-of-voice de temas (`topThemes` + `analyticsKpis`), sinais de entidade recalculados via `entityCoverage` com Laplace, classes de silêncio coordenado/rajada/explicado pelo calendário e o calendário do defeso eleitoral. Enquanto isso, com os temas sem classificação desde 26/09/2026 e o ranking de entidades com linhas legadas, a saída é pouco confiável — confira `gobus://health/pipelines`.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `sensitivity` | `str` | Não | `"medium"` | `high` \| `medium` \| `low` — quão sensível é o detector de concentração |

## Retorno

Markdown com as seções `### Picos Sustentados`, `### Cobertura Concentrada` e `### Tendências Normais`.

## Notas

- Picos sustentados: temas presentes nas janelas 3d/21d e 7d/28d do `trendingThemes`.
- Cobertura concentrada: entidades do `trendingEntities` com `volumeRatio` acima do limiar e poucas agências cobrindo (limiares por sensibilidade).
- O `volumeRatio` upstream hoje vem de linhas com baseline zero (valores de centenas a milhares); a correção está no PR DP-B (data-platform) e no G2.
