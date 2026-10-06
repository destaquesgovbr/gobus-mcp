# forecast_trends

Projeta a cobertura de temas em três janelas móveis (3, 7 e 21 dias) por **share-of-voice**. Para cada tema, dá o ritmo composto, o momentum, a confiança e os artigos esperados no horizonte pedido. A projeção leva em conta os dias úteis, os feriados e o nível de volume de cada fase do calendário (defeso eleitoral e recuperação).

!!! info "MCP App"
    Tool de app: em hosts com suporte abre o radar [`ui://forecast-radar`](../apps/forecast-radar.md) (ritmo semanal em escala log2 com o anel 1× e o top-3 com momentum; no fullscreen, o horizonte 7/14/21/28). O `content` é o Markdown completo abaixo; o `structuredContent` traz o `ForecastReport` com o mesmo Markdown até 6 KB em `summary`, como primeiro campo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `horizon_days` | `int` | Não | `21` | Horizonte **efetivo** da projeção, de 1 a 28 dias. Fora disso é ajustado, com aviso no Markdown |
| `limit` | `int` | Não | `5` | Máximo de temas (1–10), ordenados pelo ritmo composto |

## Retorno

```
## Forecast de Tendências — Horizonte 21 dias (05/10 → 25/10/2026)
**Janelas móveis até 05/10 23:06 (BRT; contagens em UTC):** 3d (peso 0,00) · 7d (peso 0,00) · 21d (peso 1,00) · share-of-voice entre os artigos classificados
**Calendário:** o horizonte cruza o fim do defeso (25/10/2026) — o volume esperado sobe de ~178 para ~311 artigos por dia útil a partir de 26/10.

> **Avisos**
> - Janela 3d: indisponível (cobertura de classificação 26%); fora do composto.
> - Janela 21d: degradada (cobertura de classificação 61%); confiança no máximo baixa.

| Tema | Ritmo (×/semana) | Momentum | Confiança | Artigos esperados (21d) | Janelas |
|---|---|---|---|---|---|
| Justiça e Direitos Humanos | 1,07× | indeterminado | baixa | 147 (124–171) | 3d — · 7d — · 21d 1,5× |
```

- **Ritmo:** multiplicador semanal da fatia do tema, `exp(7·k)`.
- **Artigos esperados:** soma da projeção diária no horizonte, com o intervalo de Poisson de 95%.
- **Janelas:** razão de share-of-voice de cada janela ("—" quando a janela está fora ou o tema tem pouco volume nela).

## Algoritmo

1. **Contagens:** `topThemes` + `analyticsKpis` nos ranges 3, 14, 7, 28, 21 e 84. Cada janela (3d, 7d, 21d) fica dentro do seu range (14, 28, 84). O baseline anterior à janela é o range menos a janela, sem sobreposição.
2. **Share-of-voice:** fatia do tema entre os artigos classificados na janela contra a fatia no baseline anterior, com Laplace. A razão só conta com **≥ 5 artigos** do tema na janela e no baseline (`w + b_prev`); tema sem nenhuma janela assim fica fora da lista.
3. **Taxa log por dia:** `k = ln(r) / (B/2)`, a distância entre os centros da janela e do baseline (3/14 → 7 dias; 7/28 → 14; 21/84 → 42). Assim as janelas ficam comparáveis.
4. **Composto:** pesos 0,5 / 0,3 / 0,2, **renormalizados** nas janelas utilizáveis. Uma janela com cobertura de classificação < 50% (ou com a consulta falhando) sai do composto; entre 50% e 80%, fica degradada e a confiança vai para baixa.
5. **Momentum:** `k3 − k7` (sem a janela de 3 dias, `k7 − k21`) contra ±ln(1,10)/7 (±10% por semana): acelerando, desacelerando, estável ou **indeterminado** quando faltam duas taxas.
6. **Confiança:** alta com as 3 janelas ok e ≥ 20 artigos em 7 dias; média com ≥ 2 janelas e ≥ 5 artigos. Cai **um nível na recuperação** pós-defeso (26/10 a 29/11).
7. **Projeção amortecida:** fatia `s(t) = s0·exp(k·φ(1−φᵗ)/(1−φ))`, com φ = 0,9 e o multiplicador limitado a [0,2; 5]. Os artigos esperados no dia `t` são `s(t)` × o volume esperado da plataforma nesse dia, que é o nível da fase × o peso do dia da semana.
   - **Perfil de dia útil:** estimado dos últimos 56 dias do snapshot de atividade das agências, sem feriados. Sem snapshot, vale o perfil padrão (sábado 0,26; domingo 0,12) e o payload marca `profileSource: "default"`.
   - **Feriados** contam como domingo: 12/10, 02/11, 15/11, 20/11 e 25/12 (e os anteriores, no perfil).
   - **Nível por fase:** artigos por dia útil equivalente, medidos no snapshot no defeso e fora dele. A partir de 26/10 vale o nível normal; um horizonte que cruza 25/10 sobe de nível.
   - Não há chave de fim de semana: a correção fica sempre ligada.

## Avisos

| Código | Quando |
|---|---|
| `ELECTORAL_BLACKOUT` | durante o defeso (04/07–25/10/2026) |
| `POST_BLACKOUT_RECOVERY` | na recuperação (26/10–29/11): confiança −1 nível |
| `CLASSIFIER_CHANGED` | enquanto algum baseline (14, 28 ou 84 dias) cruzar a troca de classificador (25/09/2026), ou seja, até 17/12/2026 |
| `THEMES_UNCLASSIFIED` | cobertura de classificação baixa em alguma janela (a janela some do composto ou fica degradada) |

Falha do snapshot de atividade: o Markdown avisa ("perfil semanal padrão") e a tool segue.

## Payload (`ForecastReport`)

`build_forecast_output` devolve `(ForecastReport, Markdown completo)`; o modelo pydantic (`kind: "gobus.forecast"`, `schemaVersion: 1`) vai no `structuredContent` e é desenhado pelo app [`ui://forecast-radar`](../apps/forecast-radar.md):

- `windows{3d,7d,21d}`: peso nominal e efetivo, cobertura, status, dias úteis equivalentes e `baselineOverlapsBlackout`;
- `platform`: perfil semanal, nível por fase e origem do perfil;
- `themes[]`: razão por janela, `perDayRate`, `weeklyMultiplier`, momentum, confiança, `projection` e flags;
- `horizonOptions`: os horizontes do controle do app (7, 14, 21 e 28).

A série diária da projeção (`projection.daily`) fica só no top-3, que o app desenha (`compact_forecast_payload`); os demais temas mantêm total, intervalo e fatias. Se ainda passar de 20 KB, as séries restantes saem do último tema para o primeiro.

## Limitações

- As janelas são móveis em UTC e terminam no instante da consulta (com cache de até 5 min).
- Enquanto a classificação de temas não cobre as janelas curtas, o forecast usa só a janela de 21 dias, sem momentum.
- A troca do classificador (25/09) cria degraus artificiais nas razões até os baselines saírem do corte.
- A série histórica diária por tema não existe na v1. Só a projeção é diária.
- A projeção assume que a fatia observada vale para todo o volume da plataforma, inclusive os artigos ainda sem tema.
