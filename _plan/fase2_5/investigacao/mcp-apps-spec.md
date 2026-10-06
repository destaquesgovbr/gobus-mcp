> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — relatório de investigação, gerado em 2026-10-05 por agente read-only (wf_98f5ad51-e18). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# MCP Apps (`ui://`) no gobus-mcp: padrão atual e recomendação para os 3 apps novos

Hoje o gobus **não tem nenhum MCP App que um host chegue a renderizar**. O `ui://readability-dashboard` está registrado com o MIME correto, mas nenhuma tool aponta para ele e o HTML não faz o handshake do protocolo. O fastmcp 3.4.2 instalado já tem suporte nativo completo, então os 3 apps novos não precisam de biblioteca nova.

Verifiquei o que segue com o `Client(mcp)` em memória (`python -c`, sem gravar arquivos) e com uma chamada real ao `gobus_detect_anomalies` a partir desta sessão do Claude Code.

## 1. O que o venv já oferece (fastmcp 3.4.2 / mcp 1.28.0)

**Versões instaladas:** `fastmcp-3.4.2` e `mcp-1.28.0`. O `poetry.lock:298-299` diz fastmcp 2.1.2, mas não vale nada na prática: o `Dockerfile:7` roda `pip install .` e resolve `^3.0` de novo a cada build.

**Suporte nativo:**
- O pacote é `fastmcp.apps`: `AppConfig`, `ResourceCSP`, `ResourcePermissions`, `UI_MIME_TYPE`, `UI_EXTENSION_ID`, `app_config_to_meta_dict`.
- O caminho antigo `fastmcp.server.apps` está deprecado desde a 3.2.0 (`server/apps.py:1-6`).
- O `@mcp.tool(...)` aceita `app: AppConfig | dict | bool` (`server/server.py:1657`) e grava em `meta["ui"]` via `app_config_to_meta_dict` (`:1759-1764`).
- O `@mcp.resource(...)` também aceita `app` (`:1824`):
  - aplica `resolve_ui_mime_type`, de modo que todo `ui://` recebe `text/html;profile=mcp-app` automaticamente (`:1887-1888`, `utilities/mime.py:7,10-27`);
  - rejeita `resource_uri` e `visibility` em resources (`:1892-1902`);
  - repassa o `meta` para cada item de conteúdo do `resources/read` (`resources/base.py:310-336`), que é o lugar que o draft da spec prefere.
- Campos do `AppConfig` (`apps/config.py`): `resource_uri→resourceUri`, `visibility: list["app"|"model"]`, `csp: ResourceCSP(connect_domains, resource_domains, frame_domains, base_uri_domains)`, `permissions`, `domain`, `prefers_border→prefersBorder`.
- O servidor já anuncia `capabilities.extensions["io.modelcontextprotocol/ui"] = {}` (`server/low_level.py:217-231`). Confirmei ao vivo: `SERVER CAPS … 'extensions': {'io.modelcontextprotocol/ui': {}}`.
- Para retornar dados ao app, usar `fastmcp.tools.ToolResult(content=..., structured_content=dict, meta=...)` (`tools/base.py:69-130`). Anotar o retorno da tool como `-> ToolResult` desliga o `outputSchema` automático (`tools/function_parsing.py:255-272`).
- **Detecção de host com UI:** `ctx.client_supports_extension(UI_EXTENSION_ID)` existe (`server/context.py:587-612`), mas **devolve sempre False no Cloud Run**. O `server.py` sobe com `stateless_http=True`, e o `_client_params` só é preenchido no `initialize` (`mcp/server/session.py:94-98,180`, `fastmcp/server/low_level.py:62-64`). Não dá para condicionar o retorno a isso.
- `FastMCPApp` / Prefab (`app=True` → `ui://prefab/renderer.html`, `server/providers/local_provider/decorators/tools.py:53-89`) exigem `prefab-ui`, que **não está instalado**. Não recomendo: é renderer externo e dependência nova, para viz que é SVG simples.
- **Ferramenta de dev:** `fastmcp dev apps <spec>` (`cli/cli.py:336-394`, `cli/apps_dev.py`):
  - também exige `prefab-ui` (`pip install 'fastmcp[apps]'`);
  - fixa ext-apps 1.0.1 / SDK TS 1.25.2 (`apps_dev.py:174-177`) e baixa o `app-bridge.js` do npm + esm.sh em tempo de execução;
  - sobe o servidor com `fastmcp run … --transport http` (`:1662-1690`) e expõe `/launch?tool=X&args={…}`;
  - não aplica CSP.

**Teste do wire format** (servidor descartável em memória):

```
TOOL meta {'ui/resourceUri': 'ui://gobus/anomaly-radar/v1', 'ui': {'resourceUri': 'ui://gobus/anomaly-radar/v1'}, ...} outputSchema None
RES list  ui://gobus/anomaly-radar/v1 text/html;profile=mcp-app {'ui': {'prefersBorder': True}, ...}
RES read  text/html;profile=mcp-app {'ui': {'prefersBorder': True}}
CALL {'content': [{'type':'text','text':'## md'}], 'structuredContent': {'v':1,'items':[...]}, 'isError': False}
```

## 2. O que a spec oficial exige (SEP-1865, estável 2026-01-26; existe também um draft)

**MIME e declaração**
- O MIME do resource **tem de ser** `text/html;profile=mcp-app`. O HTML vai em `text` (ou `blob` base64), um único payload.
- A tool declara o app em `_meta.ui.resourceUri` na **definição** (aparece no `tools/list`), não no resultado. A chave plana `_meta["ui/resourceUri"]` está deprecada, mas o `registerAppTool` oficial (ext-apps 1.7.5) ainda grava as duas.
- `visibility` vale `["model","app"]` por padrão. O host **MUST** rejeitar `tools/call` vindo do app para tools sem `"app"`.
- Mapeamento OpenAI: `openai/outputTemplate` corresponde a `_meta.ui.resourceUri`, e `text/html+skybridge` corresponde ao MIME padrão. O alias é opcional.

**Dados (host → app)**
- Notificações: `ui/notifications/tool-input` (argumentos), `tool-input-partial` (opcional), `tool-result` (o `CallToolResult` inteiro: `content`, `structuredContent`, `_meta`) e `tool-cancelled`.
- `structuredContent` é o canal da UI ("not added to model context"); `content` é o texto para o modelo e para hosts sem UI.
- Não se embute dado no HTML: o host "MAY prefetch and cache" o resource.

**Handshake (JSON-RPC 2.0 via postMessage; o SDK é opcional, raw é explicitamente permitido)**
- O app envia `ui/initialize` com os campos obrigatórios `{protocolVersion:"2026-01-26", appInfo:{name,version}, appCapabilities:{availableDisplayModes?}}`.
- O host responde `{protocolVersion, hostInfo, hostCapabilities, hostContext}`. O `hostContext` traz `theme`, `styles.variables`, `displayMode`, `containerDimensions`, `locale`, `timeZone`, `platform`, `safeAreaInsets`, `toolInfo`…
- Em seguida o app envia `ui/notifications/initialized`.
- App → host: `ui/notifications/size-changed {width,height}` (o host MUST ouvir), `tools/call`, `resources/read`, `ui/message`, `ui/open-link`, `ui/update-model-context`, `ui/request-display-mode` e `ui/download-file` (draft).
- Host → app: `ui/notifications/host-context-changed`, `ui/resource-teardown` (é request, exige resposta).

**CSP padrão**
```
default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'
```
- **Script e style inline são permitidos.**
- Domínios externos só via `_meta.ui.csp` (`connectDomains`, `resourceDomains`, `frameDomains`, `baseUriDomains`), declarado no resource. No Claude, `frameDomains` está restrito.
- `ui.domain` no Claude é `{sha256(url)[:32]}.claudemcpcontent.com` e só faz sentido com OAuth próprio. Não precisamos.

**Limites práticos (docs do Claude)**
- Resultado de tool com mais de ~150k caracteres no claude.ai/Desktop vira ponteiro de arquivo e o app não hidrata.
- O Claude Code tem limite de 25k tokens (`MAX_MCP_OUTPUT_TOKENS`).
- Card inline: altura se ajusta ao conteúdo, sem scroll interno, até 2 ações, 4-5 dados, sem drill-in nem dropdown. Detalhe vai para fullscreen.
- Largura mínima de 320px; dark mode obrigatório; usar os tokens `--color-*`, `--font-*`, `--border-radius-*`.

**Hosts que renderizam:** Claude (web, Desktop, iOS/Android via WebView, Cowork), ChatGPT, VS Code, Goose, Postman, MCPJam, mcp-use, Alpic.
- **O Claude Code não renderiza.** A doc diz "Claude Code calls the tool as text and doesn't render the UI", e a issue anthropics/claude-code#95149 está aberta, marcada como duplicate.
- Observado nesta sessão: o Claude Code **mostra o `structuredContent` em vez do `content`**. A chamada ao `gobus_detect_anomalies` devolveu `{"result":"## Detector de Anomalias…"}`, que é o wrapper automático do fastmcp. A doc do Claude confirma: com `structuredContent`, o `tool_result` vira esse JSON em string.
- Isso também mostra que o `volumeRatio` de até 8571× ainda está no ar.

**SDK ext-apps:** latest 2.0.3 (25/09/2026, par do SDK TS v2); a linha 1.x está em 1.7.5. O `app-with-deps.js` tem **337 KB** (78 KB gzip) na 1.7.5 e **418 KB** (98 KB gzip) na 2.0.3.

## 3. Auditoria de `ui://readability-dashboard`

O que está conforme:
- O MIME é `text/html;profile=mcp-app` (automático; confirmado no `resources/list`).
- Não há referência externa, e o script inline é aceito pela CSP padrão.
- O servidor anuncia a extensão.

O que não está:
1. **Nenhuma tool aponta para o resource.** Todas as tools têm `meta={'fastmcp':{'tags':[]}}` e `gobus_get_readability_recommendations` (`server.py:254-271`) não tem `app=`. Como os hosts só renderizam a partir de uma tool com `_meta.ui.resourceUri`, o dashboard nunca aparece como app.
2. **Não há handshake** (sem `ui/initialize`, `initialized` nem `size-changed`): o script em `readability_dashboard.py:158-190,255` só lê a JSON island. Pelo troubleshooting do Claude, isso resulta em app invisível ou com altura zero.
3. **O dado é buscado durante o `resources/read`** (`readability_dashboard.py:89-104`, `date.today()` na `:98`, `client.execute` na `:102`, registro em `server.py:375-378`). Com host fazendo cache ou prefetch, o dado fica velho e a GraphQL é chamada sem necessidade. O certo é template estático com os dados no `structuredContent` da tool.
4. **Código morto que os testes protegem:**
   - a `class Chart` falsa e o `<canvas>` escondido (`:160-173`, `:210`, `:226`);
   - `tests/test_resources/test_readability_dashboard.py:24-29` exige `"<canvas"` e `"Chart"`, então esses asserts precisam ser reescritos.
5. **Sem tema nem responsividade:** cores fixas (`:203`, `_flesch_color` na `:36`) e SVG com `width="600"` fixo (`:82`).
6. **Escape:**
   - `agencyName` é interpolado sem escape na tabela (`:246`) e no SVG;
   - a JSON island (`:154`, `:221-223`) não escapa `</`.
7. `_ACTIVE_AGENCIES` está hardcoded (`:6`) e as barras usam Flesch negativo sem clamp (`:58-60`); isso já está na frente 1.

## 4. Padrão recomendado para anomaly-radar, forecast-radar e article-scorecard

**Lado servidor** (vale para os três e para a migração do readability):

```python
from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult
from mcp.types import TextContent

ANOMALY_UI = "ui://anomaly-radar"

@mcp.tool(app=AppConfig(resource_uri=ANOMALY_UI), meta={"ui/resourceUri": ANOMALY_UI})
async def gobus_detect_anomalies(sensitivity: str = "medium") -> ToolResult:
    data = await build_anomalies(_client, sensitivity)          # dict com schemaVersion: 1, compacto
    return ToolResult(content=[TextContent(type="text", text=render_markdown(data))],
                      structured_content=data)

@mcp.resource(ANOMALY_UI, app=AppConfig(prefers_border=True))
def anomaly_radar_ui() -> str:
    return render_app("anomaly_radar")                           # lru_cache, estático, sem I/O
```

- O markdown passa a ser derivado do `dict`, que vira a única fonte de verdade. Os testes de texto atuais continuam valendo.
- **Ponto de atenção no Claude Code:** como ele mostra o `structuredContent`, o modelo deixa de ver o markdown. Recomendo incluir `"summary": <markdown>` no `structuredContent` dos 3 tools. Custa ~2-4 KB e mantém paridade.
  - Alternativa: dados em `_meta` do resultado, sem `structuredContent`. Funciona, mas foge do caminho canônico.
  - Condicionar por capability não é opção no Cloud Run (seção 1).
- **Interações:**
  - toggles (pico/silêncio, `sensitivity`, `horizon_days`, correção de fim de semana) chamam a **mesma** tool via `tools/call`, com visibility padrão, e re-renderizam;
  - comparar 2 artigos chama `gobus_score_article` de novo;
  - drill-down e perguntas vão para o chat via `ui/message`;
  - link de artigo usa `ui/open-link`;
  - seleção do usuário vai para `ui/update-model-context`;
  - inline mostra um resumo; o detalhe vai para fullscreen via `ui/request-display-mode`.
- **Não usar `connectDomains`** para a GraphQL. Todo dado passa por `tools/call`, o que mantém auth e caminho único e evita problemas de CORS e do Referer no iOS.

**Estrutura de arquivos e reaproveitamento:**

```
src/gobus_mcp/ui/
  __init__.py        # render_app(name): concatena base + css + js, lru_cache, valida "</script" ausente
  _base.html         # <!doctype>, <meta color-scheme="light dark">, <style>/*CSS*/</style>, <script type="module">/*JS*/</script>, skeleton
  _tokens.css        # var(--color-text-primary, #141413) etc., com fallback e prefers-color-scheme
  _bridge.js         # cliente JSON-RPC raw, ~100 linhas (esboço abaixo)
  _svg.js            # escape, escala linear, barras, polígono radar, arco gauge, sparkline
  anomaly_radar.{js,css}  forecast_radar.{js,css}  article_scorecard.{js,css}  readability_dashboard.{js,css}
```

Os arquivos são concatenados num único `<script type="module">`, sem `import` entre eles. O Dockerfile copia `src/` e o poetry-core empacota os arquivos não-.py, então `importlib.resources` funciona.

**Esboço do bridge** (substitui o SDK de 337-418 KB; a spec permite raw):

```js
const pend=new Map();let id=0;const send=m=>parent.postMessage({jsonrpc:"2.0",...m},"*");
const req=(method,params)=>new Promise((res,rej)=>{const i=++id;pend.set(i,{res,rej});send({id:i,method,params});});
addEventListener("message",e=>{if(e.source!==parent)return;const m=e.data;if(m?.jsonrpc!=="2.0")return;
 if(m.id!=null&&!m.method){const p=pend.get(m.id);pend.delete(m.id);return m.error?p?.rej(m.error):p?.res(m.result);}
 ({"ui/notifications/tool-input":p=>onInput(p.arguments),"ui/notifications/tool-result":onResult,
   "ui/notifications/host-context-changed":applyCtx,"ui/resource-teardown":()=>send({id:m.id,result:{}})}[m.method]
  ??(()=>m.id!=null&&send({id:m.id,error:{code:-32601,message:"unsupported"}})))(m.params);});
const r=await req("ui/initialize",{protocolVersion:"2026-01-26",appInfo:{name:"gobus-anomaly-radar",version:"1"},
  appCapabilities:{availableDisplayModes:["inline","fullscreen"]}});
applyCtx(r.hostContext);send({method:"ui/notifications/initialized",params:{}});
new ResizeObserver(()=>send({method:"ui/notifications/size-changed",params:{width:innerWidth,
  height:document.documentElement.scrollHeight}})).observe(document.body);
export const callTool=(name,args)=>req("tools/call",{name,arguments:args});
```

Os listeners têm de ser registrados **antes** do `ui/initialize`. O `applyCtx` aplica `styles.variables` no `:root` e `theme` em `color-scheme`.

**Bibliotecas e limites:**
- SVG à mão. Radar/spider é um polígono com N eixos (~60 linhas), gauge é um arco (~30 linhas), semáforo é CSS puro.
- Chart.js 4 UMD tem 208 KB e D3 7 min tem 280 KB (medidos no unpkg). Embutidos nos 3 apps, seriam 0,6-0,85 MB de resources, e o canvas é pior em acessibilidade. Se faltar algo, vendorizar só `d3-scale`/`d3-shape`.
- Orçamento sugerido: HTML até 60 KB por app (meta ~25 KB) e `structuredContent` até 20 KB.
- Versionamento: URI estável e `schemaVersion` no payload. Só mudar a URI em breaking change, porque os hosts fazem cache.

## 5. Como testar

**(a) pytest, sem browser, com `Client(mcp)` em memória** (padrão que usei acima; GraphQL via `fake_client`):
- `tools/list`: as 3 tools têm `_meta.ui.resourceUri` apontando para um resource existente, com `mimeType == "text/html;profile=mcp-app"`.
- `resources/read`: um único conteúdo; `<!doctype html>`; nenhum `https?://` em `src`/`href`/`url(`/`import`; contém `ui/initialize` e `size-changed`; sem `</script` no JS; tamanho abaixo do orçamento.
- `call_tool_mcp`: `content[0].text` é o markdown e `structuredContent` passa no Pydantic (`AnomalyRadarPayload.model_validate`), com `schemaVersion == 1` e menos de 20 KB.
- O fixture JSON é compartilhado com o teste de browser (`tests/fixtures/ui/*.json`).

**(b) Render headless:**
- O `playwright` Python **não está** no venv do gobus. O portal tem `@playwright/test` 1.57.0 e há Chromium em cache em `~/Library/Caches/ms-playwright` (chromium-1243 e outros).
- Proposta: dev-dep `playwright` mais o marker `@pytest.mark.ui`. Um mini-host de ~60 linhas:
  - cria `<iframe sandbox="allow-scripts" srcdoc=…>` com meta CSP igual à padrão da spec;
  - responde `ui/initialize` com `hostContext` (light/dark e as variáveis da tabela do Claude);
  - depois do `initialized`, envia `tool-input` e `tool-result` a partir do fixture;
  - intercepta `tools/call`.
- Asserts: zero erros no console, zero `securitypolicyviolation`, `size-changed` com altura > 0, DOM esperado, e screenshots em 320/760px nos dois temas.
- Mais fiel aos hosts reais: usar o `AppBridge` do ext-apps no mini-host, como faz o `fastmcp dev apps`.

**(c) Hosts reais e inspetores locais** (com o gobus em `PORT=8000`, que serve HTTP em `/mcp`):
- **basic-host oficial:** `git clone https://github.com/modelcontextprotocol/ext-apps && cd ext-apps && npm install && SERVERS='["http://localhost:8000/mcp"]' npm start`, depois abrir `:8080`. Usa sandbox proxy em `:8081` com iframe duplo, igual ao Claude web. O default seria `localhost:3001/mcp`.
- **MCPJam CLI para CI** (`@mcpjam/cli` 5.13.0): `npx @mcpjam/cli apps conformance --url http://localhost:8000/mcp --reporter junit-xml`. Faz 7 checagens (`ui-tool-metadata-valid`, `ui-listed-resources-valid`, `ui-resource-contents-valid`…) e sai com 0/1/3.
  - Render de uma tool: `npx @mcpjam/cli tools call --url … --tool-name gobus_detect_anomalies --tool-args '{"sensitivity":"medium"}' --ui --theme dark`.
  - Visual: `npx @mcpjam/inspector@latest` (3.13.0), que emula Claude e ChatGPT.
- **`fastmcp dev apps src/gobus_mcp/server.py:mcp`:** exige `prefab-ui`, usa ext-apps 1.0.1 (velho) e não aplica CSP.
- **Claude Desktop via stdio:** sem `PORT`, o `main()` sobe em stdio. Ativar Developer Mode e abrir as devtools com Cmd+Opt+I. Depois validar no claude.ai com custom connector na URL do Cloud Run **`/mcp`** — o `gobus-mcp/.mcp.json` ainda aponta para `/sse`.

## 6. Correções necessárias no BLUEPRINT

- **`:85` e `:211`** dizem que a CSP bloqueia CDN e que o dado vem "embutido como JSON". Na verdade CDN é liberável via `resourceDomains`, e o dado deve vir por `structuredContent`/tool-result.
- **`:212`** diz que "a tool anexa no seu retorno a referência ao ui://". A referência fica na **definição** da tool (`_meta.ui.resourceUri` no `tools/list`).
- **`:216`** chama o dashboard de "HTML estático com dados embutidos, sem tool-call". Sem binding de tool, nenhum host renderiza.

## Implicações para o plano

- **Frente 1:**
  - Fixar `fastmcp = ">=3.4,<4"`. O `fastmcp.apps` não existe na 2.1.2 do lock, e o Docker resolve `^3.0` sem lock.
  - Regenerar o `poetry.lock`.
  - Trocar `.mcp.json` para `/mcp`.
- **Frente 4, ordem:**
  1. Infra comum `src/gobus_mcp/ui/` (base, tokens, bridge, svg, `render_app`).
  2. Migrar `ui://readability-dashboard` para template estático ligado a uma tool, com dados via `structuredContent`. Reescrever `test_html_contem_canvas_chartjs` e remover a `class Chart`/canvas.
  3. Os 3 apps.
- **Contrato das 3 tools:** retornar `-> ToolResult` com markdown no `content` e payload Pydantic versionado no `structuredContent` (mais `summary` para o Claude Code). Primeiro refatorar as tools para gerar `dict → markdown`.
- **Binding:**
  - nas tools: `app=AppConfig(resource_uri=...)` mais `meta={"ui/resourceUri": ...}`;
  - nos resources: `app=AppConfig(prefers_border=True)`, sem CSP extra (tudo inline).
  - Não ramificar por `client_supports_extension`, que fica sempre False com `stateless_http`.
- **Sem SDK ext-apps embutido** (337-418 KB) e **sem Chart.js/D3**: bridge raw de ~100 linhas e SVG à mão. Orçamento: até 60 KB de HTML e até 20 KB de payload por app.
- **UX conforme as guidelines do Claude:** card inline-resumo, fullscreen para detalhe, controles visíveis (sem dropdown), dark mode via tokens, mínimo de 320px, skeleton durante o `tool-input`, follow-ups via `ui/message`.
- **Gates de teste do PR:**
  - pytest de wire format e payload (obrigatório);
  - Playwright headless com o mini-host (marker `ui`, novo dev-dep);
  - `npx @mcpjam/cli apps conformance` no CI;
  - validação manual no basic-host e no Claude Desktop (stdio) antes do deploy.
- **Escopo do aceite:** o Claude Code não renderiza apps. A validação visual tem de acontecer no Claude Desktop, no claude.ai ou no basic-host.
- **Pré-requisitos de dado (frentes 2 e 3) antes do anomaly-radar e do forecast-radar:** o `volumeRatio` de até 8571× está sendo devolvido agora ("Censo Escolar 2025 · 8571.4×"). Sem as correções, os radares vão destacar artefato.

**Fontes**
- Spec estável: https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx
- Spec draft: https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/draft/apps.mdx
- Repositório e basic-host: https://github.com/modelcontextprotocol/ext-apps · https://github.com/modelcontextprotocol/ext-apps/tree/main/examples/basic-host
- Blog de lançamento: https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
- VS Code: https://code.visualstudio.com/blogs/2026/01/26/mcp-apps-support
- Docs do Claude: https://claude.com/docs/connectors/building/mcp-apps/quickstart · https://claude.com/docs/connectors/building/mcp-apps/troubleshooting · https://claude.com/docs/connectors/building/mcp-apps/design-guidelines
- Issue do Claude Code: https://github.com/anthropics/claude-code/issues/95149
- FastMCP Apps: https://gofastmcp.com/apps/low-level
- MCPJam: https://docs.mcpjam.com/cli/apps-conformance · https://github.com/MCPJam/inspector
- Migração OpenAI: https://apps.extensions.modelcontextprotocol.io/api/documents/migrate-openai-app.html
