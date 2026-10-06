# Desenvolvimento e validação dos MCP Apps

Como ver os apps renderizados fora dos testes automáticos: tools de preview com dados fictícios, CORS para o basic-host, MCPJam e o roteiro de validação nos hosts. Nada disto existe em produção: as variáveis abaixo **nunca** são definidas no Cloud Run (o Terraform não as conhece).

| Variável | Default | Efeito |
|----------|---------|--------|
| `GOBUS_DEV_PREVIEW` | `false` | `1` registra as tools `gobus_dev_preview_<app>` |
| `GOBUS_DEV_FIXTURES` | `""` | diretório das fixtures (padrão: `tests/fixtures/ui` do clone) |
| `GOBUS_CORS_ORIGINS` | `""` | origens liberadas por CORS no servidor HTTP, separadas por vírgula |

## Tools de preview (`gobus_dev_preview_*`)

!!! warning "DEV — dados fictícios"
    As previews devolvem as fixtures de teste (`tests/fixtures/ui/<app>/<estado>.json`). O texto e o `summary` começam com "**DEV — dados fictícios**" para o modelo não tratar a fixture como dado real. Não use para análise.

Com `GOBUS_DEV_PREVIEW=1`, o servidor registra uma tool por app, ligada ao **mesmo** resource `ui://` da tool de verdade:

| Tool | App | Estados (`state`) |
|------|-----|-------------------|
| `gobus_dev_preview_readability_dashboard` | `ui://readability-dashboard` | `ok` (padrão), `agency_detail`, `shifted`, `unavailable`, `error`, `xss` |
| `gobus_dev_preview_article_scorecard` | `ui://article-scorecard` | `scored` (padrão), `compare`, `partial`, `refused`, `xss` |
| `gobus_dev_preview_anomaly_radar` | `ui://anomaly-radar` | `ok` (padrão), `partial`, `unavailable`, `quiet`, `empty`, `recovery`, `xss`, `max` |
| `gobus_dev_preview_forecast_radar` | `ui://forecast-radar` | `ok` (padrão), `partial`, `unavailable`, `empty`, `recovery`, `xss` |

- `state` vazio usa a fixture principal; estado inexistente devolve as opções.
- Sem o diretório de fixtures (por exemplo, na imagem Docker, que só copia `src/`), nada é registrado.
- As interações dentro do app (`tools/call` de sensibilidade, horizonte, comparação…) chamam a tool **real**, que consulta a graphql-api configurada: só o render inicial é fictício.
- As previews ficam fora da contagem de 13 tools e não têm página em `docs/tools/`.

## basic-host (ext-apps)

O basic-host oficial conecta **do navegador** no `/mcp` local, então o gobus precisa de CORS. Ele usa iframe duplo (8080 → 8081) e valida as mensagens com zod: é o teste de fidelidade do bridge JSON-RPC raw.

```bash
# terminal 1: gobus em HTTP com previews e CORS para o host
PORT=8000 GOBUS_DEV_PREVIEW=1 GOBUS_CORS_ORIGINS=http://localhost:8080 \
  GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql \
  PYTHONPATH=src .venv/bin/python3.12 -m gobus_mcp

# terminal 2: basic-host (clone fora do repositório)
git clone --depth 1 https://github.com/modelcontextprotocol/ext-apps.git
cd ext-apps && npm ci                      # o prepare builda o SDK (usa o bun das devDependencies)
cd examples/basic-host && NODE_ENV=development npm run build
SERVERS='["http://localhost:8000/mcp"]' ../../node_modules/.bin/bun serve.ts   # http://localhost:8080
```

Atalho para abrir uma tool já chamada: `http://localhost:8080/index.html?server=Gobus&tool=gobus_dev_preview_anomaly_radar&call=true`.

O que conferir em cada app: render inline sem scroll interno, **Expandir** (fullscreen), tema claro e escuro (botão do host), os `tools/call` (sensibilidade, domínio, horizonte, comparação, agência), o painel "Model Context" depois de selecionar um item e console sem erro do app.

!!! note "Diferenças do basic-host"
    - Ele não anuncia `message` nas `hostCapabilities`: os botões de pedido ao chat ("Investigar", "Explicar", "Pedir reescrita") não aparecem ali, como manda a spec. No Claude Desktop e no claude.ai eles aparecem.
    - O cliente MCP do host tenta um `GET /mcp` (stream de notificações) e o servidor stateless responde 405. O erro aparece no console da página do host, não do app.

Validado em 06/10/2026 (ext-apps 2.0.3, Playwright headless, claro e escuro): os 4 apps pelas previews, os radares com a graphql-api de produção (inclusive sensibilidade alta e horizonte de 7 dias pelo host) e a legibilidade com `date_to=2026-06-30`.

## MCPJam apps conformance

```bash
make conformance                                   # servidor local em PORT=8000, 7 checagens
make -s conformance MCPJAM_ARGS="--reporter junit-xml" > apps-conformance.xml
```

O alvo sobe o servidor em background com a GraphQL num endereço morto (os resources `ui://` são estáticos e a checagem não chama tools), espera o `/mcp` responder, roda o `@mcpjam/cli` e derruba o servidor no `trap`. No CI, o job `apps-conformance` do `test.yaml` faz o mesmo e guarda o relatório JUnit como artifact. Depois do deploy, o mesmo comando com `--url https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp` confere a produção.

## Claude Desktop e claude.ai

- **Desktop (stdio):** entrada em `claude_desktop_config.json` com `.venv/bin/python3.12 -m gobus_mcp`, `PYTHONPATH=<clone>/src`, `GOBUS_GRAPHQL_URL` e, para as previews, `GOBUS_DEV_PREVIEW=1`. Developer Mode e `Cmd+Opt+I` para o console do iframe.
- **claude.ai:** antes do merge, conector temporário por túnel (`cloudflared tunnel --url http://localhost:8000` → `https://<x>.trycloudflare.com/mcp`); depois do deploy, o conector "Gobus (prod)" em `/mcp`.
- O Claude Code não renderiza apps: nele, confira só que o `summary` chega primeiro no `structuredContent`.
