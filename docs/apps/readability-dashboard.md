# ui://readability-dashboard

**MCP App** de [`gobus_get_readability_recommendations`](../tools/get-readability-recommendations.md): ranking do Flesch por agência e diagnóstico da agência. Ver [MCP Apps](index.md).

**URI:** `ui://readability-dashboard` · **MIME:** `text/html;profile=mcp-app` · `_meta.ui.prefersBorder: true`
**Dados:** nenhum no HTML. O app desenha o `structuredContent` da tool (`kind: "gobus.readability"`, `schemaVersion: 1`, o `ReadabilityReport` de `payloads/readability.py`). Lido sem a tool, o resource é só o template.

## Card inline

- Barras do Flesch (limitado a 0–100) do **top-8** do ranking, coloridas pelas faixas do payload (`bands`), com as metas 30 (institucional) e 50 (serviço) e a faixa-alvo ≥ 50.
- Chips de cobertura ("Flesch em N de M meses") e de **janela efetiva** ("dados até 06/2026") quando o Flesch parou antes do fim da janela pedida.
- Agências sem dado aparecem com "—" ("sem dado"), nunca com 0. O valor bruto aparece quando houve clamp: "0,0 (bruto −22,9)".
- Ações: **Expandir** (fullscreen, se o host oferece) e **Ver último período com dados** (a mesma tool com `date_to` no fim da janela efetiva).
- Tabela equivalente em `<details>` (todas as agências do payload, com e sem dado).

## Fullscreen e interações

- Ranking inteiro.
- Clique numa agência → `tools/call` da mesma tool com `agency_key` → **detalhe da agência**: Flesch médio e gap até a meta, barras contra o benchmark da Agência Brasil, pior e melhor artigo da amostra (abertos pelo host com `ui/open-link`), as 3 recomendações de estilo e **Pedir reescrita ao chat** (`ui/message`). O app avisa o modelo do que está na tela (`ui/update-model-context`). **Voltar ao ranking** não consulta de novo.

## Estados

| `status` | Quando | O app mostra |
|----------|--------|--------------|
| `ok` | janela com Flesch | barras e tabela |
| `partial` | janela efetiva deslocada ou cobertura parcial | barras da janela efetiva, chip e aviso |
| `unavailable` | nenhum Flesch no histórico consultado, ou parâmetro inválido | "Legibilidade indisponível" com o motivo, ou a mensagem do parâmetro (ex.: agência fora do catálogo) |

Erro da tool (`isError`), resultado sem `structuredContent`, consulta cancelada e payload de versão desconhecida têm estados próprios.

## Orçamento

O ranking com `limit=50` ainda cabe em 20 KB: `fit_readability_budget` corta primeiro as agências sem dado (das menos ativas para as mais ativas) e depois a cauda do ranking, contando o que saiu em `omittedWithData` / `omittedWithoutData`. O `summary` traz o ranking em texto.
