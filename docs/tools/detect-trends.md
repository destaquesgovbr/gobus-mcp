# detect_trends

Detecta temas em crescimento comparando o volume de publicações de uma janela recente com um baseline histórico. Use como radar de pautas: descobrir o que está crescendo agora no acervo, opcionalmente filtrado por agência.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `window_days` | `int` | Não | `7` | Janela recente em dias |
| `baseline_days` | `int` | Não | `28` | Baseline histórico em dias (maior que `window_days`) |
| `min_articles` | `int` | Não | `3` | Mínimo de artigos na janela recente |
| `growth_threshold` | `float` | Não | `1.5` | Razão mínima **sem sobreposição** (ex: `1.5` = 50% a mais por dia que nos dias anteriores do baseline; mínimo `1.0`) |
| `agency_key` | `str` | Não | — | Filtrar por agência (ex: `"saude"`) |
| `limit` | `int` | Não | `10` | Máximo de temas |

## Retorno

Retorna Markdown com um cabeçalho dos parâmetros e do limiar e um ranking de temas em crescimento. Cada tema mostra a **razão sem sobreposição** (ou "novo", sem artigos antes da janela), o `growthScore` da API, a contagem de artigos na janela, a média diária do baseline, as agências e até 3 artigos no formato `` [título](url) · `id` `` (a URL vem do `ArticleSummary.url` do GQL-1; sem ela, só o título e o id).

**Exemplo de saída:**

```
# Radar de Tendências

**Janela:** últimos 7 dias · **Baseline:** 28 dias (os 21 anteriores à janela) · **Limiar:** razão ≥ 1.5× sem sobreposição (= growthScore ≥ 1.33 na API, cujo baseline inclui a janela)

## 2 temas em crescimento

1. 📈 **Saúde** · razão **3.0×** · growthScore 2.0 · 42 artigos (janela) vs 3.0/dia (baseline)
   Agências: [saude] Ministério da Saúde (1) · [secom] Secretaria de Comunicação Social (1)
   - [Novo imunizante aprovado](https://www.gov.br/saude/...) · `a1`
2. 🔥 **Educação** · **novo** (sem artigos antes da janela) · growthScore 4.0 · 21 artigos (janela) vs 0.8/dia (baseline)

_Razão = …_

**Para explorar:**
- `gobus_get_article(unique_id="a1")` — artigo-chave
- `gobus_search_news(query="Saúde", date_from="2026-09-28", date_to="2026-10-04")` — artigos do tema na janela
- `gobus_forecast_trends()` — o tema segue em alta?
```

## Exemplos

**Radar semanal:**
> "Quais temas estão em alta no Gov.BR nos últimos 7 dias?"

**Foco em agência:**
> "Mostre as pautas em crescimento do Ministério da Saúde"

**Janela customizada:**
> "Detecte temas em alta comparando os últimos 14 dias com os 60 dias anteriores, com crescimento mínimo de 2×"

## Notas

- **Baseline sobreposto:** o `trendingThemes` da API calcula `growthScore = (w/W) ÷ (b/B)` com um baseline de `B` dias que **inclui** a janela. O limiar do usuário `r0` é a razão sem sobreposição e é convertido para o limiar da API: `g0 = B·r0 / (r0·W + B − W)` (1,5× em 7/28 → 1,33). A conversão é monotônica: a ordem e o `limit` continuam corretos. `growthThreshold: 0` nunca é enviado (dispara N+1 de `topArticles` no resolver).
- **Razão sem sobreposição** = artigos/dia na janela ÷ artigos/dia nos dias anteriores do baseline (`b_prev = baselineDailyAvg·B − w`), com suavização de Laplace.
- **Temas indisponíveis:** sem temas, a tool mede a cobertura de classificação (`topThemes` ÷ `analyticsKpis.total`) da janela. Abaixo de 50% ela avisa "Temas: indisponível" em vez de dizer que nada cresceu (a classificação parou em 26/09/2026).
- Os indicadores visuais refletem o `growthScore`: 🔥 ≥ 3.0, 📈 ≥ 2.0, ↗ abaixo disso.
- **Virada da taxonomia (tema 26):** quando o baseline cruza a data da virada, os temas afetados da lista (Segurança Pública, Meio Ambiente e Sustentabilidade, Desenvolvimento Social, Defesa e Forças Armadas e Defesa Civil e Gestão de Desastres) ganham "taxonomia mudou no baseline" na linha, e o cabeçalho ganha uma nota com a data. O crescimento do 26 e a queda do 19 logo depois da virada podem ser só a migração de Defesa Civil.
- `min_articles` evita ruído de temas com poucos artigos na janela recente.
- **Órgãos dos top artigos** ([#17](https://github.com/destaquesgovbr/gobus-mcp/issues/17)): a linha "Agências:" conta os órgãos pelo código (`ArticleSummary.agencyKey`, do GQL-1; na query antiga, o `agencyName`, que carrega a key) e mostra `[código] Nome` com o nome do catálogo de agências, resolvido uma vez por resposta. Antes ela mostrava só os códigos. Com o catálogo fora do ar, sai `[código]`.
- **Para explorar:** com temas, o artigo mais representativo, a busca do 1º tema nos dias fechados da janela (com a `agency_key`, se houver) e o forecast; sem temas, `gobus_detect_anomalies()` e o mesmo radar com limiar 1,2×.
- **Compatibilidade:** sem o `ArticleSummary.url` na API, a tool repete a consulta sem o campo (`TrendingThemesLegacy`) e segue assim por 1 h.
