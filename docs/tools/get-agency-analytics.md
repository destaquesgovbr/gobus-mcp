# get_agency_analytics

Retorna métricas de publicação de uma ou mais agências num período: volume de artigos, sentimento médio, percentual positivo/negativo, legibilidade e tamanho médio dos textos, agregados por período. Use para comparar a atividade comunicacional entre agências ou acompanhar a evolução de uma agência ao longo do tempo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `agencies` | `list[str]` | Sim | — | Lista de agency_keys (ex: `["mec", "ms"]`) |
| `date_from` | `str` | Sim | — | Data de início ISO (ex: `"2024-01-01"`) |
| `date_to` | `str` | Sim | — | Data de fim ISO (ex: `"2024-12-31"`) |
| `granularity` | `str` | Não | `"MONTH"` | Granularidade — `DAY`, `WEEK` ou `MONTH` |

## Retorno

Retorna Markdown com um cabeçalho do período e granularidade, seguido de seções por período. Em cada período, cada agência aparece com volume de artigos, percentual de positivos, sentimento médio e legibilidade.

**Exemplo de saída:**

```
# Analytics: mec, ms
**2024-01-01 → 2024-06-30** (granularity: MONTH)

## 2024-01
- **Ministério da Educação**: **112** artigos · 😊 64% positivos · sentimento 0.18 · legibilidade médio
- **Ministério da Saúde**: **98** artigos · 😊 58% positivos · sentimento 0.11 · legibilidade difícil

## 2024-02
- **Ministério da Educação**: **103** artigos · 😊 61% positivos · sentimento 0.14 · legibilidade médio
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
- A legibilidade é classificada pelo índice Flesch: acima de 70 "fácil", acima de 50 "médio", abaixo "difícil".
- Informe as agências pela `agency_key` (código curto), não pelo nome completo.
