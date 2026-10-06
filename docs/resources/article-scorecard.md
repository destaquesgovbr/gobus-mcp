# ui://article-scorecard

**MCP App** de [`gobus_score_article`](../tools/score-article.md): nota editorial 0–10 com semáforos por dimensão, benchmark e comparação lado a lado. Ver [MCP Apps](../apps.md).

**URI:** `ui://article-scorecard` · **MIME:** `text/html;profile=mcp-app` · `_meta.ui.prefersBorder: true`
**Dados:** nenhum no HTML. O app desenha o `structuredContent` da tool (`kind: "gobus.scorecard"`, `schemaVersion: 1`, o `ScoreReport` de `payloads/scorecard.py`).

## Card inline

- Nota geral e um **semáforo por dimensão** (legibilidade, concisão, densidade de entidades), sempre com ícone e texto, não só cor: ✓ verde (≥ 7), ! amarelo (≥ 4), ✕ vermelho, – cinza (sem nota). Os limiares e as cores vêm do payload (`light`, `overallLight`).
- Chip de estado: **nota completa**, **parcial** (sem benchmark de concisão; média renormalizada) ou **nota recusada** (sem Flesch ou sem contagem de palavras: nunca um número).
- Benchmark: barras do Flesch do artigo contra as medianas da agência e da Agência Brasil (90 dias antes da publicação), palavras contra as medianas e o tamanho real das amostras.
- Ações: **Comparar** (a mesma tool com `compare_with` = a primeira sugestão), **Pedir reescrita** (`ui/message` com título, `uniqueId` e métricas) e **Expandir**.
- Tabela das dimensões em `<details>`.

## Fullscreen e comparação

- No fullscreen, as até 2 sugestões de comparação (`suggestedComparisons`: o maior Flesch da amostra da agência e o da Agência Brasil) aparecem com o motivo.
- Com `comparison` no payload, os dois artigos ficam **lado a lado** (um embaixo do outro abaixo de ~560 px), cada um com nota, estado e semáforos. O app avisa o modelo da comparação (`ui/update-model-context`).
- O título do artigo abre pelo host (`ui/open-link`, só `https`).

## Estados

| `scoreStatus` | `status` | O app mostra |
|---------------|----------|--------------|
| `scored` | `ok` | nota, semáforos e benchmark |
| `partial` | `partial` | nota renormalizada, concisão em cinza ("indisponível") |
| `refused` | `unavailable` | "—", "Nota recusada" com o motivo, semáforos cinza, sem botão de reescrita |

Artigo inexistente: a tool devolve só o texto ("Artigo não encontrado"), que o app mostra. `compare_with` inexistente ou igual ao artigo vira um aviso (`comparisonError`), sem derrubar a nota.
