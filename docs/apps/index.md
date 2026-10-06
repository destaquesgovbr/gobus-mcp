# MCP Apps

Quatro tools do Gobus abrem um **MCP App** ([SEP-1865](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx), protocolo `2026-01-26`) nos hosts que renderizam apps (Claude Desktop, claude.ai, basic-host do ext-apps, MCPJam): um painel HTML num iframe isolado, alimentado pelo resultado da tool.

| App (resource) | Tool | O que mostra |
|----------------|------|--------------|
| [`ui://readability-dashboard`](readability-dashboard.md) | [`gobus_get_readability_recommendations`](../tools/get-readability-recommendations.md) | Ranking do Flesch por agência com as metas; detalhe da agência |
| [`ui://article-scorecard`](article-scorecard.md) | [`gobus_score_article`](../tools/score-article.md) | Nota 0–10 com semáforos, benchmark e comparação lado a lado |
| [`ui://anomaly-radar`](anomaly-radar.md) | [`gobus_detect_anomalies`](../tools/detect-anomalies.md) | 8 gauges por domínio (picos e silêncios), chips do defeso e dos temas; lista de sinais no fullscreen |
| [`ui://forecast-radar`](forecast-radar.md) | [`gobus_forecast_trends`](../tools/forecast-trends.md) | Radar do ritmo semanal dos temas (log2, anel 1×), top-3 com momentum; horizonte no fullscreen |

Para validar o render sem depender dos dados de produção, há as tools de preview `gobus_dev_preview_*`, só em desenvolvimento: ver [Desenvolvimento e validação](desenvolvimento.md).

## Como funciona

1. A **definição** da tool (`tools/list`) aponta para o resource em `_meta.ui.resourceUri` (e na chave legada `_meta["ui/resourceUri"]`).
2. O host lê o resource (`resources/read`, MIME `text/html;profile=mcp-app`, `prefersBorder`): um **HTML estático**, sem dado nenhum e sem I/O no servidor. O host pode fazer cache dele.
3. O host chama a tool. O resultado traz `content` (o Markdown **completo**, para o modelo e para hosts sem UI) e `structuredContent` (o payload pydantic em camelCase, com `schemaVersion: 1`, que o app desenha).
4. Dentro do iframe, o app conversa com o host por JSON-RPC via `postMessage`: `ui/initialize` → `ui/notifications/initialized`, recebe `tool-input` e `tool-result`, e informa a altura (`size-changed`).
5. As interações passam pelo host: `tools/call` da mesma tool (outra agência, outra sensibilidade, outro horizonte, comparação), `ui/message` (pedido ao chat), `ui/open-link` (só `https`), `ui/update-model-context` e `ui/request-display-mode` (fullscreen). Cada uma só aparece se o host anunciar a capacidade.

!!! note "Lido direto, o resource é uma casca vazia"
    Um cliente que leia `ui://…` sem chamar a tool recebe só o template, que fica em "Carregando…". Os dados vêm sempre do `structuredContent` da tool.

## `content`, `summary` e o que o Claude Code recebe

- `content`: o Markdown completo da tool, sem corte (o que o modelo lê nos hosts com app e nos hosts sem UI).
- `structuredContent.summary`: o **mesmo** Markdown, cortado em fim de linha em 6 KB se passar disso (com o aviso "resumo truncado"); é o **primeiro campo** do payload. Quando o Markdown cabe em 6 KB, os dois são idênticos.
- O Claude Code não renderiza apps e mostra o `structuredContent`: o modelo lê o resumo antes dos dados. O payload inteiro fica abaixo de 20 KB (cerca de 7 mil tokens no pior caso).

Os payloads levam só o que o app desenha: nos radares, as séries diárias ficam só nos sinais exibidos (anomalias: os 6 sinais anômalos mais severos; forecast: o top-3) e as tendências normais têm teto. O que fica de fora é contado no payload (`entities.omitted`) e continua no Markdown do `content`.

## Regras do HTML

- Um documento só: `_base.html` + `_tokens.css` + o CSS do app num `<style>`, e `_bridge.js` + `_dom.js` + `_svg.js` + o JS do app num único `<script type="module">`. Sem SDK e sem biblioteca de gráficos (SVG à mão: barras no núcleo comum; gauges, sparklines e o radar no JS de cada app).
- Funciona com a CSP padrão da spec (`default-src 'none'`, script e style inline, `connect-src 'none'`): nenhuma URL externa em `src`, `href`, `url(` ou `import`.
- DOM só com `createElement`/`textContent` (nada de `innerHTML` ou `eval`); sem armazenamento do navegador (o sandbox não tem same-origin).
- Limiares, cores, opções de controle (sensibilidade, horizonte) e datas vêm do payload; o JS não fixa nada disso.
- Tema claro e escuro pelas variáveis do host (`--color-*`, `--font-*`, `--border-radius-*`) com fallback próprio; mínimo de 320 px; todo gráfico tem tabela equivalente em `<details>`.
- `render_app` recusa o HTML que quebre essas regras ou passe de 60 KB (hoje: legibilidade ~37 KB, scorecard ~35 KB, radar de anomalias ~49 KB, radar de tendências ~42 KB).
- Payload de `kind` ou `schemaVersion` desconhecido mostra "versão incompatível" (proteção contra HTML antigo em cache no host). A URI `ui://` só muda numa quebra de compatibilidade.

## Testes

| Camada | Onde | Comando |
|--------|------|---------|
| Montagem e guards do HTML | `tests/test_ui/test_render_app.py` | `make test` |
| Payloads dos radares (compactação, opções no payload) | `tests/test_ui/test_*_radar_payload.py` | `make test` |
| Fixtures (contrato pydantic, orçamentos, em dia com os builders) | `tests/test_ui/test_fixtures_contract.py` | `make test` |
| Formato no fio (`fastmcp.Client` em memória) | `tests/test_server/test_apps_wire.py` | `make test` |
| Previews dev e CORS de dev | `tests/test_server/test_dev_preview.py`, `test_cors_dev.py` | `make test` |
| Render headless num mini-host (Playwright) | `tests/browser/` (marker `ui`) | `make ui-install` (uma vez) e `make ui` |
| MCPJam apps conformance (7 checagens do lado do servidor) | servidor local em HTTP | `make conformance` |

O **mini-host** (`tests/browser/minihost.html`) faz o papel do host: iframe `sandbox="allow-scripts"` com a CSP padrão da spec, `hostContext` claro ou escuro, `tool-input` e `tool-result` só depois do `initialized`. Cada fixture roda em claro/escuro × 320/760 px e falha com erro de console, violação de CSP, `alert()` (fixtures XSS), altura fora de 100–2000 px ou overflow horizontal. `GOBUS_UI_ARTIFACTS=<dir>` grava screenshots (no CI, viram artifact do job `ui`).

As fixtures (`tests/fixtures/ui/<app>/<estado>.json`, "DEV — dados fictícios") são geradas pelos builders reais com um `FakeGraphQLClient`. Depois de mudar builder, Markdown ou payload: `make ui-fixtures`.

## Validação nos hosts

O MCPJam não testa o handshake nem o render; o mini-host cobre isso. A validação visual final usa o basic-host oficial do ext-apps (roteiro em [Desenvolvimento e validação](desenvolvimento.md)), o Claude Desktop (stdio) e o claude.ai (conector remoto em `/mcp`), com checklist e screenshots no PR.
