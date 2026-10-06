# get_agency_analytics

Retorna métricas de publicação de uma ou mais agências num período: volume de artigos, sentimento médio, percentual positivo/negativo, legibilidade e tamanho médio dos textos, agregados por período. Use para comparar a atividade comunicacional entre agências ou acompanhar a evolução de uma agência ao longo do tempo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `agencies` | `list[str]` | Sim | — | Lista de agency_keys (ex: `["mec", "saude"]`) |
| `date_from` | `str` | Sim | — | Data de início ISO (ex: `"2024-01-01"`) |
| `date_to` | `str` | Sim | — | Data de fim ISO (ex: `"2024-12-31"`) |
| `granularity` | `str` | Não | `"MONTH"` | Granularidade — `DAY`, `WEEK` ou `MONTH` |

## Retorno

Retorna Markdown com um cabeçalho do período e granularidade, avisos de cobertura de dados (quando não estão ok) e seções por período. Em cada período, cada agência aparece com volume de artigos, sentimento médio e percentual de positivos, legibilidade e palavras por artigo.

**Exemplo de saída:**

```
# Analytics: saude, mec
**2026-06-01 → 2026-07-31** (granularity: MONTH)

> Legibilidade (Flesch): degradado — 53% dos artigos com valor (352 de 666) (desde 30/06/2026)
> Sentimento (analytics): indisponível — 0% dos artigos com valor (0 de 666)

## 2026-06-01
- **Ministério da Educação**: **270** artigos · sentimento indisponível · legibilidade 12.3 (muito difícil) · 📝 644 palavras/artigo
- **Ministério da Saúde**: **82** artigos · sentimento indisponível · legibilidade 14.8 (muito difícil) · 📝 734 palavras/artigo

## 2026-07-01
- **Ministério da Educação**: **164** artigos · sentimento indisponível · legibilidade indisponível · 📝 palavras/artigo indisponível
```

## Exemplos

**Comparação entre agências:**
> "Compare o volume e o sentimento das publicações do MEC e do Ministério da Saúde no primeiro semestre de 2024"

**Evolução semanal:**
> "Mostre as métricas semanais do Ministério da Economia em março de 2024"

**Acompanhamento anual:**
> "Quantos artigos a Anvisa publicou por mês em 2024 e qual a legibilidade média?"

## Notas

- As datas devem estar no formato ISO `"YYYY-MM-DD"`.
- Granularidades válidas: `DAY`, `WEEK`, `MONTH` (convertidas para maiúsculas automaticamente).
- A legibilidade usa o índice Flesch limitado a 0–100, com as faixas únicas 0–25 muito difícil · 25–50 difícil · 50–75 médio · 75–100 fácil (o valor bruto aparece quando foi limitado).
- **Nulo não é zero:** métrica sem dado aparece como "indisponível". Sem `avgSentimentScore`, o `pctPositive` 0.0 da API é artefato e não é exibido. Um aviso no topo mostra a cobertura de legibilidade e de sentimento no período.
- Os nomes das agências vêm do catálogo. Informe as agências pelo código (`agency_key`); sem dados, a tool sugere o código certo para chaves inválidas (ex: `"ms"` → `saude`).
