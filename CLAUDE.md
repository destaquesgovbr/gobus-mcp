# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Gobus MCP

Servidor MCP (Model Context Protocol) que expõe o acervo do Destaques Gov.BR — ~300k artigos, grafo de entidades NER canonicalizadas, analytics por agência — como tools/resources/prompts para LLMs. Toda leitura de dados passa pela `graphql-api`; não há acesso direto a Postgres, Typesense ou Neo4j.

**Capacidades:** 13 tools (`gobus_*`, todas somente leitura; 2 delas abrem MCP Apps), 8 resources (6 `gobus://` e 2 `ui://`) e 4 prompts (`prompt_*`).

**Deploy:** Cloud Run (`destaquesgovbr-gobus-mcp`). Push em `main` com mudanças em `src/`, `Dockerfile`, `pyproject.toml`, `poetry.lock` ou nos workflows dispara o CI (`test.yaml`: lock, ruff, pytest, mkdocs) e, se verde, o build da imagem a partir do lock e o deploy. Env vars do serviço são geridas pelo Terraform (repo `infra/`).

**Produção:** `https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app` — `/mcp` (HTTP stateless, primário) e `/sse` + `/messages/` (compatibilidade).

## MCP no Claude Code

O Claude Code CLI tem problemas com os endpoints HTTP remotos em chamadas de subagente (`/sse` perde a sessão entre chamadas → `-32602`; `/mcp` falhou na conexão). **Use o servidor local por stdio**, que não tem sessão a perder.

O repositório traz um `.mcp.json` com a entrada `gobus-local` (stdio, código deste clone):

```json
{
  "mcpServers": {
    "gobus-local": {
      "command": ".venv/bin/python3.12",
      "args": ["-m", "gobus_mcp"],
      "env": {
        "GOBUS_GRAPHQL_URL": "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"
      }
    }
  }
}
```

- O `command` é relativo: abra o Claude Code na raiz do clone, com a `.venv` instalada (ver Comandos).
- O workspace `/Users/nitai/dev/destaquesgovbr` tem o seu próprio `.mcp.json` (entrada `gobus`, caminho absoluto da venv). Os nomes diferentes evitam colisão.
- Para validar um worktree (ex.: G2/G3), crie uma entrada stdio separada (ex.: `gobus-g2`) com `PYTHONPATH=<worktree>/src`.
- O `~/.claude.json` do usuário pode ainda apontar o "gobus" para `/sse`: ajuste manual, nunca editado por agentes.

**Claude Desktop / claude.ai:** conector remoto em `https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp`. O `/sse` fica só por compatibilidade.

## Comandos

```bash
# Venv + deps (Poetry 2.0.1; cria/usa a .venv do projeto)
python3.12 -m venv .venv
poetry install --with dev
# sem Poetry: .venv/bin/pip install -e . pytest pytest-asyncio ruff graphql-core mkdocs-material
# (não existe extra "[dev]": as deps de dev são um grupo do Poetry)

# Testes (os marcadores live e ui ficam fora por padrão)
pytest                                          # todos (sem live e ui)
pytest tests/test_tools/test_search_news.py     # um arquivo
pytest -k test_retorna_artigos                  # um teste por nome
pytest -m live                                  # contra a graphql-api de produção (só leitura)
python -m playwright install chromium           # 1x: browser do mini-host dos MCP Apps
pytest -m ui                                    # MCP Apps no mini-host headless (Playwright)

# Em worktree: a venv principal tem install editável apontando para o checkout principal
PYTHONPATH=$PWD/src .venv/bin/python3.12 -m pytest

# Lint e docs
ruff check src/ tests/
ruff format src/ tests/
mkdocs build --strict

# Atalhos (Makefile; PY=<python da venv> e PYTHONPATH=src já embutido)
make test lint ui            # suíte, ruff, mini-host
make ui-fixtures             # regera tests/fixtures/ui/*.json (depois de mudar builder/payload)
make conformance             # MCPJam apps conformance contra o servidor local (PORT=8000)

# Snapshot do SDL da graphql-api (introspecção, só leitura; o teste de contrato usa)
python tests/fixtures/refresh_schema.py

# Rodar localmente (stdio)
GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql python -m gobus_mcp

# Rodar localmente em HTTP (/mcp, /sse, /messages/)
PORT=8000 GOBUS_GRAPHQL_URL=... python -m gobus_mcp
```

## Configuração

`Settings` em `config.py` usa `pydantic-settings` com prefixo `GOBUS_`. Variáveis lidas no import (não lazy):

| Var | Default | Descrição |
|-----|---------|-----------|
| `GOBUS_GRAPHQL_URL` | `http://localhost:8000/graphql` | Endpoint da graphql-api |
| `GOBUS_GRAPHQL_API_KEY` | `""` | API key (opcional, enviada como `X-API-Key`) |
| `GOBUS_REQUEST_TIMEOUT` | `10.0` | Timeout httpx em segundos |
| `GOBUS_LOG_LEVEL` | `INFO` | Nível de log |

Copie `.env.example` → `.env` para desenvolvimento local.

## Arquitetura

```
server.py            # entrypoint FastMCP — registra tools/resources/prompts; contêiner Deps + get_deps()
                     #   (client, catalog, activity = AgencyActivityService, cache = TTLCache do G2)
config.py            # Settings (pydantic-settings, prefixo GOBUS_)
client.py            # GobusGraphQLClient — wrapper httpx; lança GobusGraphQLError em errors[]
cache.py             # TTLCache assíncrono, single-flight, relógio injetável
agency_catalog.py    # AgencyCatalog: nomes, republicadoras, validate (aliases curados + difflib), active()
agency_activity.py   # snapshot agencyAnalytics DAY de todas as agências (cache 6 h): silenciadas, retomadas, platform_daily
domains.py           # 7 domínios de policies.domain + OTHER, aliases PT, mapas curados de tema e agência
calendario.py        # BRT, defeso 2026 (04/07–25/10), recuperação até 29/11, feriados, janelas fechadas
readability.py       # Flesch: escala (textstat-en), clamp 0–100, faixas 0/25/50/75, médias null-aware, janela efetiva
readability_data.py  # legibilidade por agência via agencyAnalytics (janela pedida/efetiva, agregação)
theme_data.py        # ThemeRangeCounts (topThemes + analyticsKpis por range móvel), cache 5 min
data_status.py       # saúde das fontes (ok|degraded|unavailable), detecção dinâmica → Notice;
                     #   indexing_lag_status, worst_status, failed_status
payloads/            # pydantic: common (ReportBase, DataStatus, Notice, MAX_PAYLOAD_BYTES…),
                     #   readability, scorecard, anomalies (AnomalyReport), forecast (ForecastReport)
ui/                  # MCP Apps (SEP-1865): render_app (HTML único, estático, guards de CSP/XSS,
                     #   ≤ 60 KB), APPS, app_tool_kwargs, register_ui_resources, app_result;
                     #   assets/: _base.html, _tokens.css, _bridge.js (JSON-RPC raw 2026-01-26),
                     #   _dom.js, _svg.js e <app>.{js,css}
analytics/           # funções puras: ratios (Laplace, share-of-voice, severidade/faixa), weekday
                     #   (perfil de dia útil, feriados, nível por fase), themes, entities, forecast,
                     #   render (Markdown a partir dos modelos, ≤ 6 KB)
tools/               # 13 tools (funções async puras, recebem client/catalog como arg);
                     #   detect_anomalies/forecast_trends: build_*_report (I/O → modelo) + render
resources/           # 6 resources: agencies, themes, platform-stats, taxonomy-queries,
                     #   readability-report (JSON), health/pipelines (JSON: + indexing_lag e
                     #   agency_activity); os 2 ui:// (readability-dashboard, article-scorecard)
                     #   vêm de ui.register_ui_resources
prompts/             # 4 prompts: monitor_agency, trace_entity, weekly_digest, draft_press_release
```

**Padrão de separação:** cada tool é uma função async pura em `tools/<nome>.py` que recebe `GobusGraphQLClient` (e `catalog=` quando precisa de nomes/validação). O `server.py` lê `get_deps()` a cada chamada e repassa `deps.client`/`deps.catalog` (e, nas tools do G2 e no health, `deps.activity`/`deps.cache`); os testes trocam `server._deps` (o `Deps` sem `activity` cria o serviço a partir de `client` e `catalog`). Tools de MCP App separam o builder (I/O → modelo pydantic: `build_*_payload`, `build_anomaly_report`, `build_forecast_report`) do render (puro); o Markdown vai em `summary`.

**Registro:** toda tool sem app usa `@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})` — sem isso o fastmcp 3.4 embrulha o retorno `-> str` em `{"result": "…"}`. Resources JSON declaram `mime_type="application/json"`.

**MCP Apps** (`gobus_get_readability_recommendations` → `ui://readability-dashboard`, `gobus_score_article` → `ui://article-scorecard`): `@mcp.tool(**app_tool_kwargs(<app>))` (`app=AppConfig(resource_uri)`, `meta={"ui/resourceUri": …}`, `readOnlyHint`) e `-> ToolResult` via `app_result(report)`: `content` = `summary` (≤ 6 KB) e `structuredContent` = payload camelCase com `summary` como **primeiro** campo (≤ 20 KB). O resource é `render_app(<app>)`: HTML estático, sem dado e sem I/O (`resources/read` não chama a GraphQL); `prefersBorder`. Campo opcional novo no payload mantém `schemaVersion=1`; a URI `ui://` só muda em quebra. O Claude Code não renderiza apps (mostra o `structuredContent`). Detalhes em `docs/apps.md`.

**Transport:** determinado em runtime pelo env var `PORT`:
- `PORT` ausente → `stdio`
- `PORT` presente (Cloud Run injeta 8080) → HTTP stateless em `0.0.0.0:PORT`; endpoints `/mcp` (primário) e `/sse` + `/messages/` (compat; API privada do fastmcp — por isso `fastmcp>=3.4.2,<3.5`)

## Queries GraphQL

As queries ficam embutidas como constantes `*_QUERY` nos módulos. Toda query é **nomeada e só de leitura**; `tests/test_graphql_contract.py` valida todas contra o snapshot do SDL (`tests/fixtures/schema.graphql`). **Nunca enviar mutation** (nem como sonda).

Gotchas conhecidos do schema atual:
- Enum de tipo de entidade: `EntityKind` (não `EntityType`)
- `relatedEntities` e `entityNetwork` usam argumento `id:` (não `entityId:`)
- `RelatedEntity` retorna `canonicalId` (não `entityId`)
- Agências: `agencies { code label isRepublisher }` — `label == code` (156/156); o nome humano vem de `agencyAnalytics.agencyName` (use o `AgencyCatalog`)
- `agencyAnalytics`: datas devem ser `datetime.date` no lado da graphql-api (strings ISO são rejeitadas pelo asyncpg); `metrics:` é ignorado pelo resolver. **`dateTo` depende da granularidade:** `DAY` é inclusivo (`published_at::date BETWEEN`); `MONTH`/`WEEK` é exclusivo na prática (`published_at BETWEEN …::timestamptz`, e o asyncpg converte a data em 00:00). Monte as datas com `calendario.agency_analytics_bounds(r, granularity)`
- `search()`: **não tem `limit`** e rejeita `query:""`; filtro de agência via `filter: {agencies: [...]}`. Para listar, use `articles(page, limit ≤ 250, filter, sort)`
- `articles.filter.startDate/endDate` aceitam offset (`-03:00`); `endDate` exclusivo. Dias da API em UTC
- `trendingThemes`: `TrendingThemeResult { themeLabel themeCode windowCount baselineDailyAvg growthScore topArticles }` — **`baselineDailyAvg`** (não `baseDailyAvg`, nem `baselineCount`); `themeCode` sempre `null`; o baseline **inclui a janela**: converta o limiar do usuário com `analytics.ratios.overlap_growth_threshold` e nunca envie `growthThreshold: 0` (dispara N+1 de `topArticles`)
- `trendingEntities`: `{ entityId canonicalName type trendingScore volumeRatio windowCount windowAgencies computedAt baselineCount baselineAgencies isNew }` (os três últimos vieram com o GA-1 e são nulos em linha gravada antes da migração 029); o resolver limita a 50 e, desde o GA-1, devolve só a última execução, que ainda pode trazer linhas no piso antigo (ver `data_status.entity_ranking_status`)
- `features { trendingScore viewCount }` estão nulos em quase todo o acervo; não use como sinal

## Dados (estado e convenções)

- **Null ≠ 0:** métrica sem dado vira "indisponível"/`null`, nunca 0.0 nem nota neutra. Médias ignoram nulos (`readability.weighted_metric`).
- **Flesch:** fórmula inglesa do `textstat` (`FLESCH_SCALE_ID = "flesch_en_textstat"`), limitado a 0–100 com o bruto exibido quando houve clamp; faixas únicas 0/25/50/75.
- **Detecção dinâmica:** o estado das fontes é medido na resposta (`data_status`); datas de incidente (`SINCE_HINTS`) só redigem "desde dd/mm".
- **Janelas:** "últimos N dias" = dias fechados em BRT `[D−N, D−1]` (`calendario.closed_window`); `today`/`now` sempre injetáveis.
- **Anomalias e forecast (G2):** temas por share-of-voice de `topThemes` + `analyticsKpis` em janelas **móveis** (UTC), com gate de cobertura de classificação na janela e no baseline; entidades por `entityCoverage(DAY)` em janela **fechada** `[D−7, D−1]` (contagens em dias UTC), sem republicadoras, com precedência burst → new_entity → calendar_explained → coordinated_silence → concentrated_coverage → normal. O `volumeRatio` do upstream nunca aparece no Markdown; linhas do piso antigo (`vr/wc ≥ 100`) e de execuções antigas não viram candidatas. Concentrada e silêncio exigem o `min_count` da sensibilidade; abaixo dele a severidade é proporcional ao volume; `calendar_explained` e entidade sem menções próprias têm severidade 0; `burst`, `new_entity` e concentrada/normal com baseline < `min_count` (flag `thin_baseline`) ficam no máximo em `watch` (`SEVERITY_WATCH_MAX`). Linhas do `entityCoverage` da mesma (dia, agência) somam (o resolver agrupa também por nome); o dedup `(period, agencyKey)` é só do `agencyAnalytics` DAY. Na recuperação, só `resumed_after_blackout` (calada no último dia do defeso e de volta depois) explica sinal e conta em `resumed_agencies`; o `resumed` genérico é só informativo no health. No forecast, a razão de uma janela só conta com ≥ 5 artigos do tema (`w + b_prev`). Detalhes em `docs/tools/detect-anomalies.md` e `forecast-trends.md`.
- **Health:** `indexing_lag` compara o Typesense (`articles{found}`) com o Postgres (`agencyAnalytics` DAY) no dia D em **UTC** (D−1..D com menos de 20 artigos em D); `agency_activity` reaproveita o snapshot do `Deps.activity`; `entity_ranking` pede `isNew` (GA-1) e reporta `isNewShare` só entre as linhas com valor.
- Estado em 05/10/2026: Flesch/wordCount parados desde 30/06; temas/resumo/sentimento desde 26/09; ranking de entidades com linhas legadas. Ver `gobus://health/pipelines` e `_plan/PLANO_FASE2_5.md`.

## Testes

`pytest-asyncio` com `asyncio_mode = "auto"` — não precisa de `@pytest.mark.asyncio` explícito.

`FakeGraphQLClient` (`tests/conftest.py`): em teste novo, use `route(nome_da_operacao, resposta)` — a resposta pode ser dict, exceção ou callable (sync/async) de `variables` — e `calls(nome)` para conferir as variáveis. `route_catalog(client)` registra as 3 operações do catálogo de agências. `set_response`/`set_responses` continuam para testes antigos.

```python
async def test_exemplo(fake_client):
    route_catalog(fake_client)
    fake_client.route("AgencySummaryAnalytics", {"agencyAnalytics": [...]})
    result = await get_agency_summary("saude", fake_client, today=date(2026, 10, 5))
    assert fake_client.calls("AgencySummaryAnalytics")[0]["agencies"] == ["saude"]
```

**MCP Apps (marker `ui`):** `tests/browser/` sobe um mini-host Playwright (`minihost.html`: iframe `sandbox="allow-scripts"` + CSP padrão da spec) e roda cada fixture de `tests/fixtures/ui/<app>/<estado>.json` em claro/escuro × 320/760 px, falhando com erro de console, violação de CSP, `alert()` ou altura fora de 100–2000 px. As fixtures saem dos builders reais (`tests/fixtures/ui/build.py`); `tests/test_ui/test_fixtures_contract.py` exige que estejam em dia (`make ui-fixtures`). O formato no fio fica em `tests/test_server/test_apps_wire.py`.

## Convenções

- **Idioma:** português em docstrings, comentários e mensagens; inglês em identificadores Python e nos enums dos payloads (rótulos PT só em texto).
- **Commits:** português, prefixos `fix:` / `feature:` / `refactor:` / `chore:` / `test:` / `docs:`; TDD com `test: … (red)` antes de `fix:`/`feature: … (green)`.
- **Sem Co-Authored-By** nos commits deste repo.
- Tools retornam Markdown formatado (não JSON) — são consumidas diretamente por LLMs. **Exceção:** as tools de MCP App devolvem `summary` (= o Markdown) + payload estruturado no `structuredContent`; no Claude Code isso custa até ~20 KB (~7k tokens) por chamada, por isso o `summary` vem primeiro e é limitado a 6 KB.
- **JS dos apps:** só `createElement`/`textContent` (o `render_app` recusa `innerHTML`, `eval`, storage do navegador, URL externa e template literal); limiares e cores vêm do payload, nunca codificados no JS.
- O repositório é público: nunca versionar IPs, ids de conta ou segredos (redigir como `<IP-CLOUD-SQL>`, `<AWS-ACCOUNT-ID>`).
