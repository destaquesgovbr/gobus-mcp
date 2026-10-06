# get_agency_summary

Resumo executivo de uma agência numa única chamada: volume, legibilidade, sentimento e temas em alta. Combina [get_agency_analytics](get-agency-analytics.md) e [detect_trends](detect-trends.md) filtrado para a agência.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `agency_key` | `str` | Sim | — | Código da agência (ex: `"saude"`) — ver `gobus://agencies` |
| `days` | `int` | Não | `30` | Janela em dias fechados (D−days … D−1) |

## Retorno

```
# Resumo: Ministério da Saúde (`saude`)

**Período:** 05/09/2026–04/10/2026 (30 dias)
**Volume:** 116 artigos publicados
**Legibilidade:** indisponível — nenhum artigo do período com Flesch
**Sentimento:** indisponível — nenhum artigo do período com sentimento
> Legibilidade (Flesch): indisponível — 0% dos artigos com valor (0 de 116) (desde 30/06/2026)
> Temas: indisponível — 2% dos artigos dos últimos 7 dias com tema (20 de 934) (desde 26/09/2026)

## Temas em alta (últimos 7 dias, razão ≥ 1.5× sem sobreposição)

Temas indisponíveis: a classificação de temas não cobre a janela.
```

Com dados, a legibilidade aparece como `55.0 (médio) — 40 de 42 artigos com Flesch` e cada tema como `📈 **Vacinação** · razão 3.0× · growthScore 2.0 · 42 artigos`, com até 2 artigos representativos.

## Exemplos

> "Me dá um resumo rápido do Ministério da Saúde"

> "Como está a comunicação do MTE no último mês?"

## Notas

- **Nulo nunca vira 0:** legibilidade e sentimento sem dado aparecem como "indisponível", com aviso.
- **Legibilidade:** média ponderada por artigos, ignorando períodos sem Flesch; valor limitado a 0–100 com as faixas únicas (0/25/50/75).
- **Temas em alta:** `trendingThemes` (7/28 dias) com limiar de razão 1,5× **sem sobreposição**, convertido para o limiar da API (ver [detect_trends](detect-trends.md)). Sem temas, a cobertura de classificação diz se é estabilidade ou falta de dado.
- **Agência inválida** devolve sugestões (ex: `"trabalho"` → `trabalho-e-emprego`).
- Não substitui `gobus_get_agency_analytics` quando for preciso granularidade diária/semanal ou comparar agências.
