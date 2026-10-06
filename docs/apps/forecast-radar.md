# ui://forecast-radar

**MCP App** de [`gobus_forecast_trends`](../tools/forecast-trends.md): radar de tendências dos temas por share-of-voice, com projeção ciente do calendário. Ver [MCP Apps](index.md).

**URI:** `ui://forecast-radar` · **MIME:** `text/html;profile=mcp-app` · `_meta.ui.prefersBorder: true`
**Dados:** nenhum no HTML. O app desenha o `structuredContent` da tool (`kind: "gobus.forecast"`, `schemaVersion: 1`, o `ForecastReport` de `payloads/forecast.py`). Lido sem a tool, o resource é só o template.

## Card inline

- **Radar** com um eixo por tema (até 8 no card, todos no fullscreen), em **escala log2**: o anel tracejado é **1×** (o baseline); fora dele o tema ganha espaço, dentro perde. Os anéis vizinhos são ½×, 2×, 4×… conforme o maior desvio. Dois polígonos: o **ritmo semanal** (`weeklyMultiplier`, cheio, pontos coloridos pelo momentum) e a **fatia no fim do horizonte ÷ fatia de hoje** (`projection.shareAtHorizon / shareNow`, tracejado). Em tela estreita os eixos levam só o número, com a lista dos temas embaixo.
- **Top-3** com o **momentum** (↑ acelerando, → estável, ↓ desacelerando, ? indeterminado; ícone e texto), o ritmo em ×/semana, a confiança, os artigos esperados no horizonte com o intervalo de 95% e a sparkline da projeção diária (fim de semana e feriados mais baixos).
- **Chips:** defeso (dias restantes) ou recuperação, janelas degradadas ou indisponíveis com a cobertura de classificação, e o horizonte (com o pedido, se foi ajustado).
- Banner quando o horizonte cruza o fim do defeso (o nível de volume por dia útil muda a partir de 26/10) ou na recuperação.
- Avisos em `<details>`; tabela dos temas (ritmo, momentum, confiança, esperados e a razão de cada janela) em `<details>`.
- Ações: **Expandir** e **Explicar no chat** (`ui/message` com o top-3, os avisos de janela e a pergunta sobre a pauta).

## Fullscreen e interações

- **Horizonte** 7/14/21/28 dias (opções do payload `horizonOptions`) → `tools/call` da mesma tool com `horizon_days` e o `limit` atual.
- Tabela **Janelas e pesos**: baseline, peso nominal e efetivo (renormalizado nas janelas utilizáveis), cobertura de classificação, status e dias úteis equivalentes.
- Clique num tema do top-3 → `ui/update-model-context`.
- Em host sem fullscreen, o controle de horizonte e a tabela de janelas aparecem no card.

## Estados

| `status` | Quando | O app mostra |
|----------|--------|--------------|
| `ok` | as 3 janelas ok | radar, top-3 e tabelas |
| `partial` | alguma janela degradada ou indisponível (ex.: 05/10, só a de 21 dias, degradada) | radar com o que há, chips das janelas; momentum "indeterminado" quando faltam janelas |
| `empty` | janelas com cobertura, mas nenhum tema com volume para a razão | "Nenhum tema com dados suficientes" |
| `unavailable` | nenhuma janela utilizável (temas sem classificação, graphql-api fora do ar) | "Forecast indisponível" com o motivo, sem radar |

## Payload e orçamento

`compact_forecast_payload` mantém a série diária da projeção (`projection.daily`) só no **top-3** (`MAX_SERIES_THEMES`), que o app desenha; os demais temas ficam com total, intervalo e fatias. No cenário de teste (6 temas, horizonte de 28 dias), o payload cai de ~16 KB para ~12 KB; com 10 temas, são 7 séries de 28 dias a menos. O `content` leva o Markdown completo e o `summary` é o mesmo texto até 6 KB.

Campo novo (opcional, `schemaVersion` continua 1): `horizonOptions`.
