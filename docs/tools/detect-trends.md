# detect_trends

Detecta temas em crescimento comparando o volume de publicações de uma janela recente com um baseline histórico. Use como radar de pautas: descobrir o que está crescendo agora no acervo, opcionalmente filtrado por agência.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `window_days` | `int` | Não | `7` | Janela recente em dias |
| `baseline_days` | `int` | Não | `28` | Baseline histórico em dias |
| `min_articles` | `int` | Não | `3` | Mínimo de artigos na janela recente |
| `growth_threshold` | `float` | Não | `1.5` | Score mínimo de crescimento (ex: `1.5` = 1.5×) |
| `agency_key` | `str` | Não | — | Filtrar por agência (ex: `"ms"`) |
| `limit` | `int` | Não | `10` | Máximo de temas |

## Retorno

Retorna Markdown com um cabeçalho dos parâmetros da janela e um ranking de temas em crescimento. Cada tema mostra um indicador visual de intensidade, o score de crescimento, a contagem de artigos na janela e a média diária do baseline.

**Exemplo de saída:**

```
# Radar de Tendências

**Janela:** últimos 7 dias · **Baseline:** 28 dias · **Threshold:** 1.5×

## 4 temas em crescimento

1. 🔥 **Enchentes no Rio Grande do Sul** · Growth: **4.8×** · 31 artigos (janela) vs 0.9/dia (baseline)
2. 📈 **Reforma Tributária** · Growth: **2.3×** · 18 artigos (janela) vs 2.8/dia (baseline)
3. ↗ **Vacinação contra a Dengue** · Growth: **1.7×** · 12 artigos (janela) vs 2.5/dia (baseline)
```

## Exemplos

**Radar semanal:**
> "Quais temas estão em alta no Gov.BR nos últimos 7 dias?"

**Foco em agência:**
> "Mostre as pautas em crescimento do Ministério da Saúde"

**Janela customizada:**
> "Detecte temas em alta comparando os últimos 14 dias com os 60 dias anteriores, com crescimento mínimo de 2×"

## Notas

- Esta tool requer que a query `trendingThemes` esteja disponível e habilitada na `graphql-api`. Se não estiver, nenhum tema é retornado.
- Os indicadores visuais refletem a intensidade do crescimento: 🔥 para crescimento ≥ 3.0×, 📈 para ≥ 2.0×, ↗ abaixo disso.
- `min_articles` evita ruído de temas com poucos artigos na janela recente.
