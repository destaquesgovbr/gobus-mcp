> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — rascunho de desenho, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# F4 (MCP Apps) e F5 (message_coherence) no gobus-mcp: desenho

## 0. O que conferi nesta sessão

Fiz tudo em modo somente leitura: fastmcp 3.4.2 na `.venv`, `Client` em memória, GraphQL público e `/mcp` de produção, com `PYTHONDONTWRITEBYTECODE`.

- **Formato no fio (servidor descartável em memória):**
  - `@mcp.tool(app=AppConfig(resource_uri=U, visibility=["model","app"]), meta={"ui/resourceUri": U})` com `-> ToolResult` gera `meta = {'ui/resourceUri': U, 'ui': {'resourceUri': U, 'visibility': ['model','app']}}` e `outputSchema None`.
  - A chamada devolve `content` e `structuredContent` como foram passados.
  - Com `@mcp.tool(output_schema=None) -> str` sai só `content`, sem `structuredContent`.
  - O default `-> str` sai embrulhado em `{"result": md}`.
  - `@mcp.resource(U, app=AppConfig(prefers_border=True))` gera `text/html;profile=mcp-app` e o `_meta.ui.prefersBorder` aparece também no item do `resources/read`.
- **Produção (`/mcp`):** serverInfo 3.4.2, `extensions: {'io.modelcontextprotocol/ui': {}}`, 13 tools, 7 resources. Produção (`GOBUS_REQUEST_TIMEOUT=15.0`) já anuncia a extensão.
- **Empacotamento:** o `pyproject` não declara `packages`, e o poetry-core (`masonry/utils/module.py:50-60`, `package_include.py:85-93`) detecta `src/gobus_mcp` e inclui **todos os arquivos** com `glob("**/*")`, menos `__pycache__` e os ignorados pelo VCS. Arquivos `.html/.css/.js` vão para o wheel sem configuração. O `Dockerfile` copia `src/` e define `PYTHONPATH=/app/src`, então o runtime lê os assets da árvore de qualquer jeito. Em dev, a instalação é editável (`gobus_mcp.pth`).
- **Spec ext-apps (`src/spec.types.ts`, main/v2.0.3):**
  - `ui/initialize` recebe `{appInfo, appCapabilities, protocolVersion:"2026-01-26"}`. O exemplo do `.mdx` usa `clientInfo`, mas os tipos do SDK, que os hosts validam com zod, usam `appInfo`.
  - `ui/message` recebe `{role:"user", content: ContentBlock[]}` (array).
  - O host não pode mandar nada antes de `ui/notifications/initialized`. `tool-input` vem exatamente uma vez e antes de `tool-result`.
- **CSP padrão:** `default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' data:; connect-src 'none'`.
- **basic-host:**
  - O navegador conecta direto em `SERVERS` com `StreamableHTTPClientTransport` (`implementation.ts:52-66`). Por isso o gobus em HTTP local **precisa de CORS**.
  - O `npm run start` usa `bun`, que vem como devDependency na raiz do monorepo.
  - `fastmcp.run(..., middleware=[...])` repassa os kwargs para `run_http_async` (`server/mixins/transport.py:236`).
- **Cloud Run é público:** `infra/terraform/gobus-mcp.tf:125-130` concede `roles/run.invoker` a `allUsers`. O gobus não tem auth nenhuma; o comentário do TF que diz "MCP layer faz autenticação" está errado. A config também tem `min_instance_count=0`, `max_instance_count=1` e `timeout 3600s`.
- **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json` já tem `gobus` em stdio (`.venv/bin/python3.12 -m gobus_mcp` com `PYTHONPATH` e `GOBUS_GRAPHQL_URL`). O log fica em `~/Library/Logs/Claude/mcp-server-gobus.log`. O `cloudflared` está instalado em `/opt/homebrew/bin`.
- **MCPJam (`@mcpjam/cli` 5.13.0):**
  - `apps conformance --url … | --command … --args …` e `--reporter junit-xml`.
  - Faz 7 checagens do lado do servidor e **não** valida o handshake (`ui/initialize` nem a ordem de `tool-input`).
- **Dados ao vivo para F5:**
  - `articles(limit:250, filter:{entityCanonical:["Q575545"], startDate, endDate})` com `features{entities{canonicalId type salience count}}`: 62 artigos, 0,45 s, 83 KB. `salience` não nula em 100%, `canonicalId` em 79%.
  - `publishedAt` vem em UTC (`+00:00`), e `publicationHour` é a hora UTC.
  - `startDate`/`endDate` aceitam offset: `"…T00:00:00-03:00"` deu 197 artigos contra 200 no recorte UTC em 01/10.
  - Tom via aliases `articles(limit:1, filter:{…, sentiment:[label]}){found}`: 24 aliases em 0,62 s. Depois de 27/09 o resultado é 0.
  - `Article` **não tem campo de sentimento**.
  - Texto disponível para enquadramento depois de 26/09:
    - título: 100%;
    - `tags`: cerca de 95%;
    - `editorialLead`: cerca de 30%;
    - `subtitle`: cerca de 4%;
    - `summary`: 0.
- **Benchmark do scorecard:** duas amostras com alias (`ag:` saude e `ab:` agencia_brasil), 250 artigos cada, de 17/03 a 15/06, em 1,7 s e 241 KB. Mediana de Flesch 14,6 contra 33,2 e mediana de palavras 641 contra 439. Na saude, 24 de 234 valores são negativos.

## 1. Infra comum `src/gobus_mcp/ui/`

```
src/gobus_mcp/ui/
  __init__.py           # AppSpec, APPS, render_app(), app_result(), app_tool_kwargs(), register_ui_resources(mcp)
  assets/
    _base.html          # <!doctype html>, <meta charset>, viewport, color-scheme, <style>/*__CSS__*/</style>,
                        # skeleton (min-height 120px), <script type="module">/*__JS__*/</script>
    _tokens.css         # --gb-* = var(--color-*, fallback) + [data-theme=dark] + prefers-color-scheme; [data-mode=fullscreen]
    _bridge.js          # JSON-RPC raw, ~100 linhas (contrato abaixo)
    _dom.js             # h(tag, attrs, ...children) só com textContent/createElement; formatadores pt-BR (Intl), datas BRT
    _svg.js             # escala linear/log, barras horizontais, arco-gauge, polígono radar, sparkline, semáforo; tudo createElementNS
    readability_dashboard.{css,js}  article_scorecard.{css,js}  anomaly_radar.{css,js}  forecast_radar.{css,js}
src/gobus_mcp/payloads/  # contratos Pydantic (alias camelCase, by_alias no dump)
  common.py  readability.py  scorecard.py  anomalies.py  forecast.py  coherence.py
```

**`render_app(name)`** (`@lru_cache(maxsize=None)`):
- Lê os assets com `importlib.resources.files("gobus_mcp.ui") / "assets"`.
- Monta o CSS (`_tokens.css` + `<name>.css`) e o JS (`_bridge` + `_dom` + `_svg` + `<name>.js`, num único module script sem `import`). As variáveis de topo seguem o prefixo por arquivo: `bridge`, `dom`, `svg` e `app*`.
- Substitui `__APP_NAME__` (`gobus-<name>`), `__APP_VERSION__` (`importlib.metadata.version("gobus-mcp")`) e `__APP_TITLE__` (passado por `html.escape`).
- Lança `ValueError` se encontrar:
  - `</script` ou `</style` nos assets;
  - `https?://` em `src=`, `href=`, `url(` ou `import`;
  - `innerHTML` ou `eval(`;
  - mais de 60 KB.
- Nada de dado entra no HTML: sem JSON island e sem I/O.

**Contrato do `_bridge.js`** (formato do SDK v2):
- **Antes do initialize:** registra os listeners e só aceita mensagens com `e.source === parent` e `jsonrpc === "2.0"`.
- **Handshake:** `ui/initialize {protocolVersion:"2026-01-26", appInfo:{name,version}, appCapabilities:{availableDisplayModes:["inline","fullscreen"]}}`, depois `applyHostContext`, depois `ui/notifications/initialized`.
- **`applyHostContext`:** copia `styles.variables` para o `:root`, `theme` para `data-theme` e `color-scheme`, `displayMode` para `data-mode`, e guarda `hostCapabilities`.
- **Altura:** `ResizeObserver` com rAF manda `ui/notifications/size-changed {width, height: documentElement.scrollHeight}` só quando a altura muda.
- **Handlers:**
  - `tool-input`: skeleton com os parâmetros;
  - `tool-result`: `onResult`;
  - `tool-cancelled`: estado "cancelado";
  - `host-context-changed`;
  - `ui/resource-teardown`: responde `{}`;
  - qualquer outro request: erro `-32601`.
- **API exposta:** `callTool(name, args)`, `sendMessage(text)` (com `content:[{type:"text",text}]`), `openLink(url)` (só `https:`), `updateModelContext(text)`, `requestDisplayMode(mode)` (só se o host anunciar o modo).
- **Gating:** os controles que chamam tools só aparecem com `hostCapabilities.serverTools`, e os links só com `openLinks`. `message` e `updateModelContext` são tentados em try/catch e o botão some se der erro.
- **Restrições:** sem `localStorage`, porque o sandbox sem same-origin lança exceção.

**Orçamento:**

| Item | Limite rígido (teste) | Meta |
|---|---|---|
| HTML por app | 60 KB | ≤ 25 KB (núcleo comum ≤ 14 KB) |
| `structuredContent` | 20 KB (fixture "máximo") | ≤ 10 KB |
| `summary` | 6 KB | — |

Muito abaixo de ~150k caracteres (claude.ai/Desktop) e de 25k tokens (Claude Code).

## 2. Contratos dos apps

**`payloads/common.py`:**
- `PayloadBase`, com os campos nesta ordem: `schemaVersion: Literal[1]`, `kind`, `summary: str` (Markdown; **é o primeiro campo legível no Claude Code**), `status`, `generatedAt` (ISO, America/Sao_Paulo), `asOf` (último dia completo D−1 em BRT), `timezone`, `params`, `notices: list[DataNotice]`.
- `status`: `ok | partial | empty | unavailable`.
- `DataNotice {code, severity: info|warn|error, message, since: date|None, affects: list[str]}`, com estes códigos:
  - `THEMES_UNCLASSIFIED`
  - `SENTIMENT_UNAVAILABLE`
  - `READABILITY_UNAVAILABLE`
  - `TRENDING_ENTITIES_STALE`
  - `BASELINE_ZERO_SUPPRESSED`
  - `ELECTORAL_BLACKOUT`
  - `POST_BLACKOUT_RECOVERY`
  - `INDEXING_LAG`
  - `SAMPLE_TRUNCATED`
- `BlackoutInfo {phase: none|active|recovery, start, end, recoveryUntil, affectedAgencies}`. O calendário vem de F3.
- **Regra null ≠ 0:** todo valor indisponível sai `null` (dump com `exclude_none=False`), e o app mostra "—" com o rótulo "indisponível".

**`app_result(payload, markdown)`:** grava `summary = markdown` (truncado em 6 KB com "…") e devolve `ToolResult(content=[TextContent(text=markdown)], structured_content=payload.model_dump(mode="json", by_alias=True))`. Acima de 20 KB, registra warning (os testes falham antes disso).

### 2.1 `ui://readability-dashboard` ← `gobus_get_readability_recommendations`

`kind:"gobus.readability"`:
- `params {agencyKey|null, days, dateFrom, dateTo}`;
- `scale {name:"flesch_en_textstat", clampMin, clampMax, targetService:50, targetInstitutional:30, bands[]}`. O clamp vale na escala atual, conforme F1.
- `coverage {articlesTotal, articlesWithFlesch, lastDayWithData}`;
- `agencies[≤30] {agencyKey, agencyName, isRepublisher, articleCount, articlesWithFlesch, fleschRaw|null, fleschDisplay|null, wordCountAvg|null, gapToTarget|null, label}`;
- `benchmark {agencyKey:"agencia_brasil", fleschDisplay|null}`;
- `detail|null {agencyKey, agencyName, worstArticles[≤3], bestArticles[≤3] {uniqueId,title,url,publishedAt,flesch,wordCount}, recommendations[{title,tips[3]}]}`.

A tool ganha o parâmetro `date_to: str = ""` (combinar com F1). Sem ele não dá para mostrar mar–jun, o único período com Flesch.

### 2.2 `ui://article-scorecard` ← `gobus_score_article(unique_id, compare_with="")`

`kind:"gobus.article_scorecard"`:
- `articles[1..2]`, cada um com:
  - `uniqueId, title, url, agencyKey, agencyName, publishedAt`;
  - `status: scored|partial|refused`, `refusalReason`, `overall|null`;
  - `dimensions[{key: readability|conciseness|entity_density, score 0–10|null, weight, rawValue, rawUnit, light: green|yellow|red|gray, percentileInAgency|null, note}]`;
  - `benchmarks {agencyMedian, agenciaBrasil}` do tipo `BenchmarkSet {window{from,to}, sampleSize, coverage, fleschMedian, wordCountMedian, entityDensityMedian}`.
- `suggestedComparisons[≤2] {uniqueId,title,reason}`.

**Recusa:** `overall` só existe com as 3 dimensões disponíveis. Faltando Flesch ou wordCount, o status é `refused` ou `partial` e não há nota. Isso acaba com o 5,6 constante.

**Benchmark:**
- Janela `[pub−90d, pub]` ancorada na **data do artigo**, não em hoje, para que artigos de mar–jun tenham base válida.
- Uma requisição com alias `ag:` e `ab:` (mesma query medida acima), com a mediana calculada no cliente.
- Com menos de 10 artigos com feature, o benchmark fica `null`.
- Isso troca o `agencyAnalytics` ponderado; os testes de `test_score_article.py` precisam ser reescritos.

### 2.3 `ui://anomaly-radar` ← `gobus_detect_anomalies(sensitivity, domain_filter)`

**Contrato compartilhado F3↔F4: F3 produz, F4 consome.**

`kind:"gobus.anomalies"`:
- `params {sensitivity, domainFilter}`;
- `windows {spike:{days,start,end}, baseline:{…}}`;
- `blackout`;
- `domains[8]`, em ordem fixa HEALTH, EDUCATION, SOCIAL, ECONOMIC, SECURITY, ENVIRONMENT, GOVERNANCE, OTHER: `{domain, label, spikeLevel 0–1, silenceLevel 0–1, spikeBand, silenceBand: normal|atencao|alerta, nSpikes, nSilences}`. O F3 calcula as faixas, para que o app não reimplemente limiares.
- `spikes[≤15] {id, source: theme|entity, label, entityId|null, type|null, domain, windowCount, baselineDaily|null, ratio, ratioByWindow{"3d","7d"}, sustained, agencies|null, isNewEntity, score, band, confidence, daily[≤28], samples[≤2]{uniqueId,title,url,agencyKey,publishedAt}}`;
- `silences[≤15] {entityId, label, type, domain, owner{agencyKey, agencyName, source: entity.agencyKey|coverage_dominant, shareBaseline}, ownerMentions{window, baselineDaily}, ownerOutput{windowDaily, baselineDaily, ratio|null, inBlackout, lastActiveDate}, others{mentions, agencies, ratio|null}, score, band, confidence, suppressed, suppressedReason, ownerDaily[≤28], samples[≤2]}`;
- `suppressedCount {reason: n}`.

### 2.4 `ui://forecast-radar` ← `gobus_forecast_trends(horizon_days, weekend_correction, limit)`

**Contrato compartilhado F3↔F4.**

`kind:"gobus.forecast"`:
- `params {horizonDays, weekendCorrection, limit}`;
- `windows[{key: "3d"|"7d"|"21d", windowDays, baselineDays, weight, effectiveWeight, available, businessDays, weekendShare}]`;
- `themes[≤10] {label, code|null, composite, ratios{3d,7d,21d}|null, rawGrowth{…}, windowCounts{…}, momentum: acelerando|estavel|desacelerando|indeterminado, momentumDelta|null, confidence, projection|null {horizonDays, expectedDaily, low, high, method}, daily[≤28]}`;
- `blackout`.

As razões são as verdadeiras, recuperadas de `baselineDailyAvg`. O campo `projection` é opcional e o F3 decide se preenche.

### 2.5 UX, interações e estados

| App | Card inline (≤ 4–5 dados, ≤ 2 ações) | Fullscreen | Interações | Estados |
|---|---|---|---|---|
| readability | top-8 barras com faixa-alvo, chip de cobertura; ações "Expandir" e "Pedir recomendações" | ranking completo, tabela, detalhe da agência (pior/melhor artigo, dicas) | clique na barra → `tools/call` da mesma tool com `agency_key`; "Ver último período com dados" → mesma tool com `date_to=lastDayWithData`; link do artigo → `ui/open-link`; seleção → `ui/update-model-context` | `unavailable` (Flesch nulo desde 30/06; botão para o período com dado); `empty`; valor bruto negativo mostrado como "0 (bruto −22,9)" |
| scorecard | nota com 3 semáforos (ícone + texto, não só cor) e mediana/AB; ações "Comparar" e "Pedir reescrita" | lado a lado de 2 artigos, percentis, barras contra a mediana e contra a AB | "Comparar" → `tools/call gobus_score_article{unique_id, compare_with}` usando `suggestedComparisons`; `ui/message` "Reescreva…"; `ui/open-link` | `refused` ("nota recusada: Flesch/wordCount indisponíveis desde 30/06"); `partial`; benchmark `null` |
| anomaly-radar | grade de 8 gauges (pico laranja, silêncio azul), "N picos · M silêncios", chips de defeso e de temas sem classificação; ações "Detalhar" e "Investigar no chat" | gauges e lista com toggle pico/silêncio local (sem tool call); `sensitivity` em controle segmentado; `domain_filter` em chips; sparkline da dona | sensibilidade/domínio → `tools/call` da mesma tool; item → `ui/update-model-context`; "Investigar" → `ui/message` sugerindo `gobus_get_entity_profile` / `gobus_get_message_coherence`; amostras → `ui/open-link` | `empty`; `unavailable` (entidades suspensas por baseline zero ou temas sem classificação); defeso: banner "silêncios de agências em defeso suprimidos"; `recovery` até ~22/11: banner de normalização |
| forecast-radar | radar com eixos = temas (≤ 8), anel 1× = baseline, escala log2, polígono atual e projeção; top-3 com badge ↑ → ↓ | tabela de razões por janela com `effectiveWeight`; controles de horizonte (7/14/21/28) e de correção de fim de semana | horizonte e correção → `tools/call` da mesma tool; tema → `ui/update-model-context`; "Explicar" → `ui/message` | `unavailable` (temas sem classificação desde 26/09 com `asOf` antigo); `empty`; nota do defeso |

Em todos os apps:
- Payload com `kind` ou `schemaVersion` desconhecido mostra "versão incompatível". Isso protege contra cache de HTML no host.
- Resultado com `isError` sem `structuredContent` mostra o texto do `content`.
- Cada gráfico tem tabela equivalente em `<details>` e SVG com `role="img"` e `<title>`.
- Largura mínima de 320 px; light e dark.

## 3. Migração do `ui://readability-dashboard`

1. Remover `src/gobus_mcp/resources/readability_dashboard.py` inteiro: `fetch_readability_dashboard`, `_render_bar_chart_svg`, `_flesch_color`, `_ACTIVE_AGENCIES`, a `class Chart` falsa e o `<canvas>`. As cores passam para os tokens CSS e as faixas para `scale.bands`.
2. Em `tools/get_readability_recommendations.py`, separar `build_readability_payload(client, agency_key, days, date_to, today) -> ReadabilityPayload` de `render_readability_markdown(p) -> str`. Usa os helpers de F1 (clamp, média que ignora `null`, `agency_catalog`, query `articles(limit, filter:{agencies}, sort:DATE)`). O `"~33.5"` fixo sai.
3. O resource vira `render_app("readability_dashboard")`, estático e sem I/O.
4. Reescrever `tests/test_resources/test_readability_dashboard.py`:
   - apagar os 6 testes atuais, incluindo `test_html_contem_canvas_chartjs`;
   - criar `tests/test_ui/test_render_app.py` e `tests/test_server/test_apps_wire.py` (seção 5a);
   - adicionar testes de payload em `tests/test_tools/test_get_readability_recommendations.py`: `null` não vira 0, `None` vai para o fim da ordenação, benchmark AB, `detail` no modo agência, escape é responsabilidade do DOM.
5. Recomendações de dashboard que dependem de dados F0 continuam como `unavailable` até o pipeline voltar.

## 4. Registro em `server.py` e saída para o Claude Code

```python
from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult
from gobus_mcp.ui import APPS, app_result, register_ui_resources

def app_tool_kwargs(name):            # em ui/__init__.py
    uri = APPS[name].uri
    return {"app": AppConfig(resource_uri=uri, visibility=["model", "app"]),
            "meta": {"ui/resourceUri": uri}}          # chave legada: ext-apps ainda grava as duas

@mcp.tool(**app_tool_kwargs("anomaly_radar"))
async def gobus_detect_anomalies(sensitivity: str = "medium", domain_filter: str = "") -> ToolResult:
    report = await build_anomaly_report(_client, sensitivity, domain_filter or None)
    return app_result(report, render_anomalies_markdown(report))

register_ui_resources(mcp)   # for spec in APPS.values(): mcp.resource(spec.uri, name=…, title=…,
                             #   description=…, app=AppConfig(prefers_border=True))(_factory(spec.name))
```

- **URIs estáveis:** `ui://readability-dashboard`, `ui://article-scorecard`, `ui://anomaly-radar`, `ui://forecast-radar`. A versão fica em `schemaVersion`; a URI só muda (`…-v2`) em quebra de compatibilidade.
- **Tools de app:** anotação `-> ToolResult`, o que suprime o `outputSchema` (verificado); `structuredContent` = payload com `summary`; `content` = o mesmo Markdown. **Não declarar `output_schema=Payload.model_json_schema()` na v1.** Isso obrigaria todo estado de erro a seguir o schema e aumentaria o `tools/list`. O JSON Schema vai para `docs/apps/contratos.md`, gerado de `model_json_schema(by_alias=True)`.
- **Tools sem app (F1 e F5):** `output_schema=None` e `-> str`, então o Claude Code vê o Markdown limpo.
- **Claude Code nas tools de app:** ele mostra o `structuredContent`, então o modelo lê `summary` (primeiro campo) mais os dados (≤ 20 KB, cerca de 7k tokens). Isso fica documentado.
- **Não ramificar por `client_supports_extension`:** com `stateless_http` ele é sempre False.
- **Anotações:** adicionar `annotations={"readOnlyHint": True}` às tools. Hipótese a testar no claude.ai: reduz prompts de permissão nos `tools/call` vindos do app.
- **CORS só para dev:** `Settings.cors_origins: str = ""`. Se preenchido, `main()` passa `middleware=[Middleware(CORSMiddleware, allow_origins=…, allow_methods=["GET","POST","DELETE","OPTIONS"], allow_headers=["*"], expose_headers=["mcp-session-id","mcp-protocol-version"])]` para `mcp.run(transport="http", …)`. O Terraform nunca define essa variável; um teste garante que sem ela não há header `access-control-*`.
- **Tools de preview só para dev:** `GOBUS_DEV_FIXTURES=<abs>/tests/fixtures/ui` registra `gobus_dev_preview_<app>(state="ok")`, uma por app, ligadas à mesma URI e devolvendo a fixture. Serve para validar o estado `ok` de forecast e anomalias nos hosts reais enquanto F0 não volta. Nunca é configurada no Cloud Run.

## 5. Testes

**(a) pytest de formato no fio** (sem browser), em `tests/test_server/test_apps_wire.py`. Usa `fastmcp.Client(mcp)` em memória e `monkeypatch.setattr("gobus_mcp.server._client", FakeGraphQLClient())`.
- `list_tools`:
  - nas 4 tools de app, `meta.ui.resourceUri == meta["ui/resourceUri"] == uri`, visibility com `model` e `app`, `outputSchema is None`;
  - nas outras, sem `ui`, `outputSchema None` e sem `structuredContent` na chamada.
- `list_resources` e `read_resource_mcp`:
  - um único conteúdo com MIME `text/html;profile=mcp-app` e `_meta.ui.prefersBorder`;
  - HTML começa com `<!doctype html>`, contém `ui/initialize`, `appInfo` e `ui/notifications/size-changed`;
  - sem referência externa nem `innerHTML`, menos de 60 KB;
  - `fake.execute.await_count == 0`, ou seja, sem I/O na leitura.
- `call_tool_mcp`:
  - `content[0].text == structuredContent["summary"]`;
  - `Model.model_validate(sc)`, `schemaVersion == 1`, menos de 20 KB, `isError False`;
  - GraphQL lançando exceção dá `isError` com texto.
- `capabilities.extensions["io.modelcontextprotocol/ui"]` presente.
- `tests/test_ui/test_render_app.py`: assets via `importlib.resources`, cache `lru_cache` e rejeição de `</script`.
- `tests/test_ui/test_fixtures_contract.py`: toda fixture valida no Pydantic e respeita o orçamento.

**(b) Mini-host Playwright headless** (marker `ui`).
- **Deps:** `playwright = "^1.63"` no grupo dev; `pytest.importorskip("playwright.sync_api")`.
- **pyproject:** `markers=["ui: render headless (Playwright)"]` e `addopts="-m 'not ui'"`.
- **`tests/ui/minihost.html`**, cerca de 70 linhas:
  - `<iframe sandbox="allow-scripts" srcdoc>`, com a CSP padrão da spec injetada por `<meta http-equiv>` logo após `<head>`;
  - responde `ui/initialize` com `hostContext` light ou dark e variáveis `--color-*` e `--font-*`;
  - **só depois de `initialized`** envia `tool-input` e depois `tool-result`, ambos da fixture;
  - grava em `window.__gb` `toolCalls`, `messages`, `links`, `ctx` e `sizes`;
  - `tools/call` responde com `fixture.toolCallResults[args]`;
  - `request-display-mode` responde e manda `host-context-changed`.
- **Fixtures:** `tests/fixtures/ui/<app>/<estado>.json` com `{toolName, toolInput, result:{content, structuredContent, isError}, toolCallResults}`. Estados:
  - readability: `ok`, `unavailable`, `agency_detail`;
  - scorecard: `scored`, `refused`, `compare`;
  - anomaly: `ok`, `empty`, `unavailable`, `blackout`, `recovery`;
  - forecast: `ok`, `unavailable`;
  - mais uma fixture `xss` com `agencyName = "<img src=x onerror=alert(1)>"`.
  
  São as mesmas usadas pelo pytest (a) e pelas tools de preview.
- **Asserts:**
  - zero `pageerror` e zero mensagens de console de erro ou "Refused to";
  - ordem do handshake e `appInfo.name == "gobus-<app>"`;
  - último `size-changed` com altura entre 100 e 2000;
  - DOM por `data-testid` (indisponível mostra "—", nunca "0");
  - tema dark aplica as variáveis;
  - em 320 e 760 px, sem overflow horizontal;
  - clique em sensibilidade gera `toolCalls[-1]` esperado e re-render;
  - "Investigar" gera `ui/message` com `content` array;
  - fixture XSS não dispara `dialog`.
- **Screenshots:** em `$GOBUS_UI_ARTIFACTS` (tmp local, artifact no CI). Sem comparação por pixel na v1.

**(c) MCPJam:** `npx -y @mcpjam/cli@5.13.0 apps conformance --url http://127.0.0.1:8000/mcp --reporter junit-xml`. Os resources são estáticos e a checagem não chama tools, então roda com GraphQL apontando para um endereço morto.

**Comandos locais** (Makefile novo, com venv):
```bash
.venv/bin/python3.12 -m pytest -q                       # rápido (exclui ui)
.venv/bin/python3.12 -m playwright install chromium     # 1x
.venv/bin/python3.12 -m pytest -m ui
PORT=8000 GOBUS_GRAPHQL_URL=http://127.0.0.1:9/graphql .venv/bin/python3.12 -m gobus_mcp &   # make conformance
npx -y @mcpjam/cli@5.13.0 apps conformance --url http://127.0.0.1:8000/mcp ; kill %1
```

**CI:** jobs adicionados ao `ci.yaml` criado em F1.
- `ui`: `poetry install --with dev`, `poetry run python -m playwright install --with-deps chromium`, `pytest -m ui`, upload dos screenshots.
- `apps-conformance`: setup-node 20, servidor em background, espera por `curl`, MCPJam com junit.
- `package`: `poetry build -f wheel` e checa `gobus_mcp/ui/assets/_bridge.js` no `namelist()`.

## 6. Validação manual nos 3 hosts

Antes de cada sessão, conferir **qual servidor está ligado**. O conector remoto do claude.ai também aparece no Desktop, então ele deve se chamar "Gobus (prod)" e o local deve ser desligado ou ligado de propósito.

**(A) Claude Desktop (stdio).** `~/Library/Application Support/Claude/claude_desktop_config.json` (já existe; acrescentar só o que está marcado):
```json
{ "mcpServers": { "gobus": {
  "command": "/Users/nitai/dev/destaquesgovbr/gobus-mcp/.venv/bin/python3.12",
  "args": ["-m", "gobus_mcp"],
  "env": {
    "PYTHONPATH": "/Users/nitai/dev/destaquesgovbr/gobus-mcp/src",
    "GOBUS_GRAPHQL_URL": "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql",
    "GOBUS_LOG_LEVEL": "DEBUG",
    "GOBUS_DEV_FIXTURES": "/Users/nitai/dev/destaquesgovbr/gobus-mcp/tests/fixtures/ui"
  } } } }
```
Passos:
1. Help > Troubleshooting > Enable Developer Mode.
2. Developer > Reload MCP Configuration.
3. `Cmd+Opt+I` para ver o iframe interno; log em `~/Library/Logs/Claude/mcp-server-gobus.log`.
4. Prompts:
   - readability com `date_to=2026-06-29`, `days=120`;
   - `score_article` em artigo de junho (`scored`) e de outubro (`refused`), depois "Comparar";
   - `detect_anomalies sensitivity=high` (avisos de temas e defeso);
   - `forecast_trends horizon_days=14` (`unavailable`);
   - os 4 `gobus_dev_preview_*` para os estados `ok`.
5. Checklist por app: inline sem scroll interno; fullscreen; tema claro e escuro; `ui/message` cria a mensagem; `open-link` abre o browser; depois de um toggle, perguntar "o que estou vendo?" (prova o `update-model-context`); console limpo.

**(B) basic-host oficial** (clone fora do workspace):
```bash
git clone --depth 1 https://github.com/modelcontextprotocol/ext-apps.git ~/dev/tools/ext-apps
cd ~/dev/tools/ext-apps && npm install            # prepare→build; bun vem das devDependencies
# terminal 1
cd /Users/nitai/dev/destaquesgovbr/gobus-mcp && PORT=8000 GOBUS_CORS_ORIGINS=http://localhost:8080 \
  GOBUS_DEV_FIXTURES=$PWD/tests/fixtures/ui \
  GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql .venv/bin/python3.12 -m gobus_mcp
# terminal 2
cd ~/dev/tools/ext-apps/examples/basic-host && SERVERS='["http://localhost:8000/mcp"]' npm run start   # abrir http://localhost:8080
```
- O host usa iframe duplo (8080 → 8081) e o `AppBridge` com validação zod. É o teste de fidelidade do bridge raw (`appInfo` e `content` como array).
- Se o `npm run start` falhar sem bun: `npm run build && npx tsx serve.ts` dentro do basic-host.
- Opcional: `npx -y @mcpjam/cli@5.13.0 tools call --url http://localhost:8000/mcp --tool-name gobus_score_article --tool-args '{"unique_id":"…"}' --ui --theme dark`.

**(C) claude.ai (custom connector).**
1. Merge em main tocando `src/` dispara o deploy.
2. Smoke: `npx -y @mcpjam/cli@5.13.0 apps conformance --url https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp`.
3. No claude.ai, Settings > Connectors > Add custom connector, nome "Gobus (prod)", URL `https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp`, sem OAuth. Habilitar no chat e repetir os prompts de (A).

Implicações do Cloud Run público e sem auth:
- O conector funciona sem OAuth. As chamadas saem dos IPs da Anthropic, então não precisa de CORS. `ui.domain` não é necessário (só serve com OAuth próprio).
- Qualquer pessoa com a URL consegue chamar. Os dados já são públicos via GraphQL; o risco é abuso e custo.
- `min_instance_count=0` gera cold start na primeira chamada; `max_instance_count=1` limita concorrência.
- Em conta Team/Enterprise, um owner precisa adicionar o conector.
- Nenhuma mudança de infra é necessária nesta fase. Se for preciso (instância mínima ou auth), só por PR em `infra/`.
- **Validação antes do merge (opcional):** `cloudflared tunnel --url http://localhost:8000` gera `https://<x>.trycloudflare.com/mcp` para usar como conector temporário. Remover depois.

Validar depois de 25/10 também mostra ao vivo o estado `recovery` do radar.

## 7. F5: `gobus_get_message_coherence`

**Assinatura:**
```python
@mcp.tool(output_schema=None)
async def gobus_get_message_coherence(entity_id: str = "", theme: str = "", agencies: list[str] | None = None,
                                      date_from: str = "", date_to: str = "", include_republishers: bool = False) -> str
```
- Exatamente um entre `entity_id` e `theme`.
- Se `entity_id` não parecer `Q\d+` ou `dgb_*`, resolve por `entitySearch(limit:1)` e avisa.
- `date_to` padrão = D−1 BRT; `date_from` = `date_to − 13`; janela máxima de 92 dias.
- Com `theme` e janela depois de 25/09, emite aviso `THEMES_UNCLASSIFIED` e sugere `entity_id`.
- Janela que cruza 04/07–25/10 recebe nota de defeso (calendário de F3).

**Queries:** constantes `*_QUERY`, cobertas pelo teste de contrato de F1.
```graphql
query CoherenceArticles($filter: ArticleFilter!, $page: Int!) {
  articles(limit: 250, page: $page, filter: $filter, sort: DATE) { found page
    articles { uniqueId title url agency agencyName publishedAt subtitle editorialLead summary tags
      features { entities { canonicalId text type salience count } } } } }
# filter = {entityCanonical:[id]} | {themeLabel}, + agencies?, startDate:"<from>T00:00:00-03:00", endDate:"<to>T23:59:59-03:00"
query CoherenceTone($pos: ArticleFilter!, $neg: ArticleFilter!, $neu: ArticleFilter!) {
  pos: articles(limit: 250, filter: $pos) { found articles { uniqueId } }
  neg: articles(limit: 250, filter: $neg) { found articles { uniqueId } }
  neu: articles(limit: 250, filter: $neu) { found articles { uniqueId } } }
# mesmo filtro + sentiment:[label]; endDate cortado no último dia com sentimento (25/09, detectado via health de F1)
query CoherencePrior($id: String!, $from: String!, $to: String!) {
  entityCoverage(entityId: $id, dateFrom: $from, dateTo: $to, granularity: DAY) { period agencyKey articleCount } }
# [date_from−30d, date_from) — dateTo exclui o dia; só no caminho por entidade
```
A lista de republicadoras vem de `agency_catalog` (F1, com cache TTL): `agencies{code label isRepublisher}`, hoje agencia_brasil, tvbrasil e ebc.

**Limites de custo:**
- Página 1; com `found > 250`, páginas 2–4 em `gather`. Teto de 1000 artigos, cerca de 1,3 MB; acima disso, aviso `SAMPLE_TRUNCATED`.
- Tom em uma requisição com 3 aliases (até 3 páginas extras por rótulo dentro do mesmo teto).
- Cobertura anterior em 1 chamada.
- Típico: 3–4 requisições em 1,5–2,5 s; pior caso cerca de 10 requisições.
- Sem `content` (pesado). `found == 0` retorna cedo com dica.

**Algoritmo** (funções puras em `src/gobus_mcp/analysis/coherence.py` e `analysis/framing.py`, com `today` injetável):
- **Emissores:** agências não republicadoras com pelo menos 2 artigos. Com menos de 2 emissores, `status: insufficient` ("voz única: X") e sem índice. Republicadoras ficam numa seção à parte (volume, participação, atraso da 1ª republicação).
- **E, entidades** (peso 0,35):
  - `w(a,e) = Σ salience / n_a × log(1 + N/df(e))`, só com `canonicalId`, excluindo a própria entidade e as `dgb_<agência>`;
  - E = média dos cossenos entre pares de agências, ponderada por `min(n_a, n_b)`;
  - agência com menos de 3 entidades fica fora de E;
  - saídas: âncoras compartilhadas (em ≥ 50% dos emissores) e âncoras exclusivas por agência; o rótulo é o `text` mais frequente.
- **T, timing em BRT** (0,25):
  - `publishedAt` → `ZoneInfo("America/Sao_Paulo")` (nunca `publicationHour`);
  - agência índice = primeiro artigo; atraso em horas por agência;
  - T = 0,5 × (fração com 1º artigo em até 48 h) + 0,5 × (Jaccard médio dos conjuntos de dias);
  - aviso de "início truncado" se `CoherencePrior` tiver artigos.
- **F, enquadramento lexical** (0,25):
  - texto = título + subtitle + editorialLead + summary + tags, normalizado sem acento;
  - léxico de prefixos → `anuncio | resultado | desafio | servico | agenda | outro`;
  - F = 1 − JSD médio (base 2) entre as distribuições das agências;
  - com menos de 40% dos artigos classificados, F fica indisponível.
- **S, tom** (0,15): só artigos com rótulo; 1 − JSD médio. Com cobertura abaixo de 50%, o tom fica indisponível (sempre depois de 26/09).
- **Índice:** `score = Σ w·D / Σ w das dimensões disponíveis` (pesos renormalizados). Índice 1–5 por cortes `[0,2; 0,4; 0,6; 0,8]`, **provisórios até a calibração**. Calibrar pelo caminho de tema em jun/2026 contra o UC-03 (Defesa 4/5, Minorias 3/5, Justiça 2/5) e por 2 entidades (Q575545 em ago–set, `dgb_pe-de-meia`). Registrar em `_experiments/coherence-calibration-2026-10/`.
- **Contexto (fora do índice):** HHI de volume entre emissores.

**Saída Markdown** (≤ ~5 KB):
- `## Coerência de Mensagem — <rótulo> (<tipo> · <id>)`, com janela BRT, emissores e republicadoras.
- `### Índice: N/5 (score)`.
- Tabela de dimensões (valor, peso efetivo, leitura, "indisponível" com motivo).
- `### Por agência` (≤ 12 linhas: artigos, 1ª publicação BRT, atraso, enquadramento dominante, âncoras exclusivas).
- `### Âncoras compartilhadas` (≤ 8).
- `### Divergências` (≤ 5 pares).
- `### Republicadoras`.
- `### Avisos de dados`.

O builder devolve um `CoherenceReport` Pydantic (`payloads/coherence.py`, `schemaVersion 1`), que já serve de payload para um app futuro.

**Testes:**
- `tests/test_analysis/test_coherence.py`:
  - cosseno idêntico dá 1 e disjunto dá 0; idf derruba a entidade onipresente;
  - propriedades da JSD;
  - léxico com exemplos pt-BR ("anuncia" → anuncio, "deflagra operação contra fraude" → desafio);
  - virada de dia: `2026-09-26T01:30Z` → 25/09 em BRT;
  - separação de republicadoras;
  - renormalização sem tom; caso `insufficient`; cortes do índice.
- `tests/test_tools/test_get_message_coherence.py`:
  - `set_responses` na ordem [página 1, páginas 2–n, tom, prior], com o catálogo injetado;
  - erro sem `entity_id` nem `theme`; aviso de tema depois de 25/09; `found 0`; paginação com `found=600`.
- Smoke ao vivo manual (marker `live`, fora do CI).
- Docs: `docs/tools/get-message-coherence.md` e nav.

**App `ui://coherence-matrix`: adiar** para depois da Fase 2.5. Motivos:
- os cortes precisam de calibração;
- a matriz depende das dimensões estabilizarem;
- já são 4 apps;
- 2 das 4 dimensões estão degradadas hoje.

Como o payload já existe, o app futuro só precisa do binding e do JS.

## 8. Sequência, commits e riscos

**Dependências:**
- F1 mergeado antes: `fastmcp>=3.4.2,<3.5`, `output_schema=None`, helpers de null e clamp, `agency_catalog`, health, teste de contrato, CI, Dockerfile pelo lock.
- `anomaly-radar` e `forecast-radar` dependem de F3 (builders e `payloads/anomalies.py` / `forecast.py`).
- readability e scorecard dependem só de F1.
- F5 reaproveita `timeutil` e `blackout` de F3 (módulos compartilhados que proponho: `src/gobus_mcp/timeutil.py` e `src/gobus_mcp/blackout.py`).

**PR único depois de F1:** `feature/fase2.5-analytics-apps`, a partir de `origin/main`, título `feat: Fase 2.5 — radares, MCP Apps e coerência` (F3 + F4 + F5). Commits com TDD em pares, em português, sem Co-Authored-By:
1. infra `ui/` (wire e `render_app`);
2. migração do readability;
3. scorecard;
4. contratos F3;
5. anomaly-radar;
6. forecast-radar;
7. mini-host Playwright e fixtures;
8. CI `ui`, conformance e `package`;
9. CORS dev e tools de preview dev;
10. F5 puro;
11. tool F5;
12. docs: `docs/apps/{index,readability-dashboard,article-scorecard,anomaly-radar,forecast-radar,contratos}.md`, nav do `mkdocs.yml`, contagens em `docs/index.md`, `docs/arquitetura.md` e `CLAUDE.md`, mais a correção do `.mcp.json` para `/mcp`.

Alternativa, se a revisão ficar pesada: separar F5 num segundo PR.

**Riscos:**
- **Hosts rígidos com o formato do bridge:** mitigado seguindo `spec.types.ts` v2 e validando no basic-host (`AppBridge` com zod). O MCPJam não cobre o handshake; o mini-host cobre.
- **Cache do HTML no host entre deploys:** checagem de `schemaVersion`/`kind` e URI nova só em quebra.
- **A maior parte dos dados está indisponível agora (F0):** os estados `ok` ao vivo só saem para scorecard e readability com dados de mar–jun; o resto usa as tools de preview.
- **Radar não pode ir ao ar com o 8571×:** depende de F2 ou da supressão no F3 (aviso `BASELINE_ZERO_SUPPRESSED`).
- **Endpoint público sem auth:** limitar a custo e abuso nesta fase.
- **`zoneinfo` na imagem slim:** a imagem oficial do Python inclui `tzdata`, mas não verifiquei; o seguro é adicionar `tzdata` ao pyproject (custo desprezível).

### Arquivos críticos para a implementação
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/server.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/ui/__init__.py (novo; com `assets/_bridge.js` e `assets/_base.html`)
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/payloads/anomalies.py e forecast.py (novos; contrato compartilhado com F3)
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/tools/score_article.py e get_readability_recommendations.py (refatorar para payload + Markdown; `resources/readability_dashboard.py` é removido)
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/tools/get_message_coherence.py e /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/analysis/coherence.py (novos, F5)
