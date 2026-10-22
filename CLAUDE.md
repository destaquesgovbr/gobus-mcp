# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Gobus MCP

Servidor MCP (Model Context Protocol) que expõe o acervo do Destaques Gov.BR — ~300k artigos, grafo de entidades NER canonicalizadas, analytics por agência — como tools/resources/prompts para LLMs. Toda leitura de dados passa pela `graphql-api`; não há acesso direto a Postgres, Typesense ou Neo4j.

**Capacidades:** 14 tools (`gobus_*`, todas somente leitura; 4 delas abrem MCP Apps), 10 resources (6 `gobus://` e 4 `ui://`) e 4 prompts (`prompt_*`). Em desenvolvimento (`GOBUS_DEV_PREVIEW=1`), mais 4 tools `gobus_dev_preview_*`.

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
pytest -m live tests/test_live_coherence.py -s  # F5: Q575545 em ago–set (≤ 3 s, ≤ 5 KB)
pytest -m live tests/test_live_search_news.py    # MEC no último dia útil: date_from == date_to > 0
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
make -s conformance MCPJAM_ARGS="--reporter junit-xml" > apps-conformance.xml   # como no CI

# MCP Apps num host real (basic-host do ext-apps, Desktop): previews com fixtures e CORS de dev
PORT=8000 GOBUS_DEV_PREVIEW=1 GOBUS_CORS_ORIGINS=http://localhost:8080 GOBUS_GRAPHQL_URL=... python -m gobus_mcp
# roteiro do basic-host em docs/apps/desenvolvimento.md

# Snapshot do SDL da graphql-api (introspecção, só leitura; o teste de contrato usa)
python tests/fixtures/refresh_schema.py
# Snapshot à frente da produção (PR da graphql-api ainda sem deploy): introspecção local do schema
# Strawberry do branch (graphql_sync + build_client_schema + print_schema) e o tipo novo em
# PENDING_UPSTREAM (tests/test_graphql_contract.py), que pula o teste live do snapshot até o deploy

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
| `GOBUS_TAXONOMY_CHANGE_DATE` | `""` | **Não está no Terraform** (só para simular localmente). Virada da taxonomia (tema 26), `AAAA-MM-DD`; `off` desliga o `TAXONOMY_CHANGED`. Vazio = `calendario.TAXONOMY_CHANGE_2026_DEFAULT` (provisória) |
| `GOBUS_DEV_PREVIEW` | `false` | **Só dev:** `1` registra `gobus_dev_preview_<app>` (fixtures "DEV — dados fictícios") |
| `GOBUS_DEV_FIXTURES` | `""` | **Só dev:** diretório das fixtures das previews (padrão: `tests/fixtures/ui` do clone) |
| `GOBUS_CORS_ORIGINS` | `""` | **Só dev:** origens CORS do HTTP, separadas por vírgula (basic-host conecta do navegador) |

As três variáveis de dev nunca vão para o Cloud Run (o Terraform não as define); sem elas, nada é registrado e não há header `access-control-*`.

Copie `.env.example` → `.env` para desenvolvimento local.

## Arquitetura

```
server.py            # entrypoint FastMCP — registra tools/resources/prompts; contêiner Deps + get_deps()
                     #   (client, catalog, activity = AgencyActivityService, cache = TTLCache do G2)
config.py            # Settings (pydantic-settings, prefixo GOBUS_)
client.py            # GobusGraphQLClient — wrapper httpx; lança GobusGraphQLError em errors[]
cache.py             # TTLCache assíncrono, single-flight, relógio injetável
agency_catalog.py    # AgencyCatalog: nomes, republicadoras, validate (aliases curados + difflib), active();
                     #   catalog_info() → CatalogInfo (republicadoras + códigos, nunca levanta)
agency_activity.py   # snapshot agencyAnalytics DAY de todas as agências (cache 6 h): silenciadas, retomadas, platform_daily
entity_lookup.py     # looks_like_id, entity(id), fetch_neighbors: relatedEntities por associação (w·log2 lift,
                     #   w ≥ 3; pools WEIGHT ∪ LIFT), peso bruto de reserva (cache 30 min)
schema_compat.py     # execute_compatible: query nova → em "Cannot query field" etc., *_LEGACY_QUERY por 1 h
                     #   (features article_summary_url, related_lift, flesch_ptbr; COMPAT do processo)
domains.py           # 7 domínios de policies.domain + OTHER, aliases PT, mapas curados de tema e agência
                     #   (tema 26 "Defesa Civil e Gestão de Desastres" → SECURITY, como o 19)
calendario.py        # BRT, defeso 2026 (04/07–25/10), recuperação até 29/11, feriados, janelas fechadas,
                     #   limites do dia em BRT (brt_day_start/brt_day_end), troca de classificador
                     #   (25/09), virada da taxonomia (TAXONOMY_CHANGE_2026, temas afetados) e
                     #   janelas alternativas sem o defeso (blackout_alternatives)
instructions.py      # SERVER_INSTRUCTIONS (≤ 1,5 KB, pt-BR) → FastMCP(instructions=…) no initialize
formatting.py        # Markdown compartilhado: md_link (só http(s)), article_ref, agency_label, fmt_int/fmt_decimal
                     #   (pt-BR), brt_day, plural, fmt_date (DD/MM/AAAA), error_text (notas de falha) e o
                     #   rodapé "Para explorar" (tool_call, follow_ups ≤ 3 chamadas/400 B, with_follow_ups)
readability.py       # Flesch: PTBR_SCALE (Martins, padrão) e EN_SCALE (textstat, reserva), choose_scale, clamp 0–100,
                     #   faixas de Martins 0/25/50/75, médias null-aware pela contagem, janela efetiva
readability_data.py  # legibilidade por agência via agencyAnalytics (janela pedida/efetiva, agregação)
theme_data.py        # ThemeRangeCounts (topThemes + analyticsKpis por range móvel), cache 5 min
data_status.py       # saúde das fontes (ok|degraded|unavailable), detecção dinâmica → Notice;
                     #   indexing_lag_status, worst_status, failed_status
payloads/            # pydantic: common (ReportBase, DataStatus, Notice, MAX_PAYLOAD_BYTES…),
                     #   readability, scorecard, anomalies (AnomalyReport), forecast (ForecastReport),
                     #   coherence (CoherenceReport, sem app nesta fase)
ui/                  # MCP Apps (SEP-1865): render_app (HTML único, estático, guards de CSP/XSS,
                     #   ≤ 60 KB), APPS (4 apps), app_tool_kwargs, register_ui_resources,
                     #   app_result(report, content=); preview.py: gobus_dev_preview_* (só dev);
                     #   assets/: _base.html, _tokens.css, _bridge.js (JSON-RPC raw 2026-01-26),
                     #   _dom.js, _svg.js e <app>.{js,css} (gauge, sparkline e radar ficam no
                     #   JS do app que os usa)
analytics/           # funções puras: ratios (Laplace, share-of-voice, severidade/faixa), weekday
                     #   (perfil de dia útil, feriados, nível por fase), themes, entities, forecast,
                     #   coherence (E/T/F/S e índice 1–5), framing (léxico pt-BR de enquadramento),
                     #   generic_entities (lista curada de genéricas), profile (série
                     #   mensal do perfil: próprias × republicações, zeros, parcial, anos agregados),
                     #   render (Markdown a partir dos modelos; max_bytes=None = completo)
tools/               # 14 tools (funções async puras, recebem client/catalog como arg);
                     #   detect_anomalies/forecast_trends: build_*_output → (payload compacto,
                     #   Markdown completo); build_*_report = só o payload;
                     #   get_message_coherence: build_coherence_output → (CoherenceReport,
                     #   Markdown); a tool é -> str (sem app nesta fase)
resources/           # 6 resources: agencies, themes, platform-stats, taxonomy-queries,
                     #   readability-report (JSON), health/pipelines (JSON: + indexing_lag e
                     #   agency_activity); os 4 ui:// (readability-dashboard, article-scorecard,
                     #   anomaly-radar, forecast-radar) vêm de ui.register_ui_resources
prompts/             # 4 prompts: monitor_agency, trace_entity, weekly_digest, draft_press_release
                     #   (__init__: _int_arg, _calendar_note, CITE_AS_LINKS)
```

**Padrão de separação:** cada tool é uma função async pura em `tools/<nome>.py` que recebe `GobusGraphQLClient` (e `catalog=` quando precisa de nomes/validação). O `server.py` lê `get_deps()` a cada chamada e repassa `deps.client`/`deps.catalog` (e, nas tools do G2 e no health, `deps.activity`/`deps.cache`); os testes trocam `server._deps` (o `Deps` sem `activity` cria o serviço a partir de `client` e `catalog`). Tools de MCP App separam o builder (I/O → modelo pydantic: `build_*_payload`, `build_anomaly_report`, `build_forecast_report`) do render (puro); o Markdown vai em `summary`.

**Registro:** toda tool sem app usa `@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})` — sem isso o fastmcp 3.4 embrulha o retorno `-> str` em `{"result": "…"}`. Resources JSON declaram `mime_type="application/json"`.

**MCP Apps** (`gobus_get_readability_recommendations` → `ui://readability-dashboard`, `gobus_score_article` → `ui://article-scorecard`, `gobus_detect_anomalies` → `ui://anomaly-radar`, `gobus_forecast_trends` → `ui://forecast-radar`): `@mcp.tool(**app_tool_kwargs(<app>))` (`app=AppConfig(resource_uri)`, `meta={"ui/resourceUri": …}`, `readOnlyHint`) e `-> ToolResult` via `app_result(report, content=markdown)`: `content` = o Markdown **completo** e `structuredContent` = payload camelCase com `summary` (o mesmo Markdown cortado em 6 KB; idênticos quando cabe) como **primeiro** campo (≤ 20 KB). Os radares compactam o payload (`compact_anomaly_payload`: séries só nos 6 sinais anômalos exibidos, ≤ 3 normais sem série, resto contado em `entities.omitted`; `compact_forecast_payload`: série da projeção só no top-3). O resource é `render_app(<app>)`: HTML estático, sem dado e sem I/O (`resources/read` não chama a GraphQL); `prefersBorder`. Campo opcional novo no payload mantém `schemaVersion=1`; a URI `ui://` só muda em quebra. O Claude Code não renderiza apps (mostra o `structuredContent`). Parâmetro inválido de tool de app devolve só texto (sem `structuredContent`; o app mostra a mensagem). Detalhes em `docs/apps/`.

**Prompts:** devolvem `str` (uma mensagem de usuário). **Nunca `list[dict]`:** no fastmcp 3.4 isso quebra o `prompts/get` ("messages[0] must be Message or str, got dict"; o `Message(dict)` sugerido pelo erro serializa o dict como JSON). Argumentos numéricos são `str` no wrapper (o host manda texto, `""` nos opcionais em branco) e passam por `_int_arg`; datas concretas da janela vêm do `calendario` com `today` injetável. Teste renderizando pelo `Client` em memória (`get_prompt`), não só chamando a função.

**Instruções do servidor:** `instructions.py` → `FastMCP(name="Gobus", instructions=SERVER_INSTRUCTIONS)`. Mantenha ≤ 1,5 KB e só com tools registradas (`tests/test_instructions.py`).

**Transport:** determinado em runtime pelo env var `PORT`:
- `PORT` ausente → `stdio`
- `PORT` presente (Cloud Run injeta 8080) → HTTP stateless em `0.0.0.0:PORT`; endpoints `/mcp` (primário) e `/sse` + `/messages/` (compat; API privada do fastmcp — por isso `fastmcp>=3.4.2,<3.5`)

## Queries GraphQL

As queries ficam embutidas como constantes `*_QUERY` nos módulos. Campo novo da graphql-api entra com a query nova **e** a antiga (`*_LEGACY_QUERY`, operação com sufixo `Legacy`) via `schema_compat.execute_compatible`, que cai na antiga por 1 h em erro de schema; nos testes, rotear `<Op>Legacy` simula a API antiga. Toda query é **nomeada e só de leitura**; `tests/test_graphql_contract.py` valida todas contra o snapshot do SDL (`tests/fixtures/schema.graphql`). **Nunca enviar mutation** (nem como sonda). A única query gerada em runtime é a de aliases de contagem da coerência (`counts_query(n)` → `CoherenceCounts`); a forma dela entra no teste de contrato por `_COUNTS_SAMPLE_QUERY`.

Gotchas conhecidos do schema atual:
- Enum de tipo de entidade: `EntityKind` (não `EntityType`)
- `relatedEntities` e `entityNetwork` usam argumento `id:` (não `entityId:`)
- `relatedEntities(id, limit)` é **centrado no foco**: só as arestas que tocam `id`; `weight` = artigos em co-menção em **todo o acervo**, sem deduplicar republicações. A rede e o perfil usam só ele (`entity_lookup.fetch_neighbors`). Com o GQL-1: `orderBy: WEIGHT | UNIQUE_CONTENT | LIFT`, `minWeight` (padrão 1) e `articleCount`/`uniqueContentCount`/`uniqueContentWeight`/`lift` (nulos sem `entity_stats`). **Não use só `orderBy: LIFT`**: ele perde os vizinhos fortes (o MEC é o 65º vizinho do Pé-de-Meia por lift); o gobus une os pools `WEIGHT`/`minWeight: 2` e `LIFT`/`minWeight: 3`
- `ArticleSummary` (`trendingThemes.topArticles`): `url` e `agencyKey` vieram com o GQL-1; `agencyName` traz a key, não o nome
- Flesch: `ArticleFeatures.readabilityFleschPtbr`, `AgencyPeriodMetrics.avgReadabilityFleschPtbr` + `readabilityFleschPtbrCount` (GQL-1; nulo até o artigo ser recalculado — backfill na migração 033); `readabilityFlesch`/`avgReadabilityFlesch` = fórmula inglesa (legado)
- `entityNetwork` **não é usado**: devolve todos os nós alcançáveis sem ordem (sem LIMIT) e o `limit` corta as arestas entre **quaisquer** pares por peso, então pares de hubs (Brasil ↔ Brasília) expulsam as arestas do foco
- `entityCoverage`: `dateTo` exclusivo na prática (`published_at <= dateTo::timestamptz`, data vira 00:00 UTC): mande o último dia + 1 (`calendario.utc_day_bounds`)
- `RelatedEntity` retorna `canonicalId` (não `entityId`)
- Agências: `agencies { code label isRepublisher }` — `label == code` (156/156); o nome humano vem de `agencyAnalytics.agencyName` (use o `AgencyCatalog`)
- `agencyAnalytics`: datas devem ser `datetime.date` no lado da graphql-api (strings ISO são rejeitadas pelo asyncpg); `metrics:` é ignorado pelo resolver. **`dateTo` depende da granularidade:** `DAY` é inclusivo (`published_at::date BETWEEN`); `MONTH`/`WEEK` é exclusivo na prática (`published_at BETWEEN …::timestamptz`, e o asyncpg converte a data em 00:00). Monte as datas com `calendario.agency_analytics_bounds(r, granularity)`
- `search()`: **não tem `limit`** (20 por página) e rejeita `query:""` (`"*"` lista tudo); filtro de agência via `filter: {agencies: [...]}`. Para listar, use `articles(page, limit ≤ 250, filter, sort)`
- `search`/`articles.filter.startDate/endDate` aceitam offset (`-03:00`) e comparam `published_at >= startDate` / `<= endDate` (segundos). Data pura vira 00:00 UTC e perde o dia do `endDate`: para incluir o dia D inteiro em BRT, mande `calendario.brt_day_end(D)` (`T23:59:59-03:00`; o `search_news` já faz). O `brt_bounds` (fim = 00:00 de D+1) inclui o instante 00:00:00 de D+1. Dias da API em UTC
- `trendingThemes`: `TrendingThemeResult { themeLabel themeCode windowCount baselineDailyAvg growthScore topArticles }` — **`baselineDailyAvg`** (não `baseDailyAvg`, nem `baselineCount`); `themeCode` sempre `null`; o baseline **inclui a janela**: converta o limiar do usuário com `analytics.ratios.overlap_growth_threshold` e nunca envie `growthThreshold: 0` (dispara N+1 de `topArticles`)
- `trendingEntities`: `{ entityId canonicalName type trendingScore volumeRatio windowCount windowAgencies computedAt baselineCount baselineAgencies isNew }` (os três últimos vieram com o GA-1 e são nulos em linha gravada antes da migração 029); o resolver limita a 50 e, desde o GA-1, devolve só a última execução, que ainda pode trazer linhas no piso antigo (ver `data_status.entity_ranking_status`)
- `features { trendingScore viewCount }` estão nulos em quase todo o acervo; não use como sinal
- `Article.agencyName` vem `null` (graphql-api#34) e `ArticleSummary.agencyName` carrega a **key** (use `ArticleSummary.agencyKey`, do GQL-1): nome de agência só pelo `AgencyCatalog`. Para muitas linhas, resolva `catalog_display_names(catalog)` uma vez e monte o rótulo com `formatting.article_agency(art, names)` + `agency_label` (`search_news`, `detect_trends`; gobus-mcp#17)
- `articles.filter.entityCanonical` (Typesense) não tem a marcação antes de ~20/05/2026 (histórico não reindexado; o Postgres/`entityCoverage` tem). Confira contra o `entityCoverage` antes de afirmar "nenhum artigo"
- `articles.filter.themes` com as 25 labels L1 estoura o limite de 4000 caracteres da query do Typesense; para contar artigos classificados, some aliases `articles(limit:1, filter:{themeLabel})`

## Dados (estado e convenções)

- **Entidades genéricas** (`analytics/generic_entities.py`): só Brasil (`Q155`), Brasília (`Q2844`), Governo Federal (`Q5440531`), Portal Gov.br (`dgb_portal-gov-br`, em revisão) e Diário Oficial da União (`Q3712237`, lift < 1 com Bolsa Família, INSS e MEC em 21/10/2026) ficam ocultas por padrão na rede (`include_generic=true` traz de volta) e nas relacionadas do perfil, sempre listadas numa linha "Ocultas como genéricas". As entidades das agências (`dgb_{code}`: Secretaria-Geral, Fazenda, Casa Civil…) são vizinhos com sentido e ficam visíveis; a exclusão delas é só da coerência (`coherence.excluded_entities`). UFs (inclusive `Q119158`), capitais, QIDs de ministérios e pessoas também continuam. Detalhes em `docs/tools/get-entity-network.md`.
- **Cópias idênticas:** só o Typesense deduplica (`articles.filter.dedup` agrupa por `content_hash`); o perfil compara `found` com e sem `dedup` desde `data_status.ENTITY_CANONICAL_INDEX_SINCE` (20/05/2026) e só mostra uma linha quando há cópia (conteúdo idêntico é raro: Pé-de-Meia 189 → 189, INSS 371 → 370 em 21/10/2026).
- **Null ≠ 0:** métrica sem dado vira "indisponível"/`null`, nunca 0.0 nem nota neutra. Médias ignoram nulos (`readability.weighted_metric`).
- **Flesch:** pt-BR de Martins et al. (1996) (`FLESCH_SCALE_ID = "flesch_ptbr_martins1996"`), limitado a 0–100 com o bruto exibido quando houve clamp; faixas de Martins 0–25 muito difícil · 25–50 difícil · 50–75 fácil · 75–100 muito fácil (chaves `very_hard`/`hard`/`easy`/`very_easy`); meta de serviço 50; mediana real do acervo 25,2 (`PTBR_CORPUS_MEDIAN`, 033 de 22/10/2026), cerca de +5 sobre o inglês (não os +42 da constante de Martins), 2,5% negativos (mín −339) e 3 acima de 100 — por isso clamp na exibição e nas médias exibidas; o rodapé do diagnóstico cita "mediana do acervo ≈ 25". O bruto só aparece quando difere do exibido em uma casa. Médias pela `readabilityFleschPtbrCount`. Sem o pt-BR (API sem o campo, ou pt-BR em < 10% dos artigos com o inglês presente), `choose_scale` usa a fórmula inglesa do `textstat` com o aviso `READABILITY_LEGACY_SCALE`; as escalas nunca se misturam numa média.
- **Ranking de vizinhos:** `w · max(0, log2 lift)` com `w ≥ 3` (rede e relacionadas do perfil), cabeçalho "**Ranking:**"/"**Ordem:**" dizendo qual valeu; peso bruto quando não há lift. A lista curada de genéricas continua.
- **Detecção dinâmica:** o estado das fontes é medido na resposta (`data_status`); datas de incidente (`SINCE_HINTS`) só redigem "desde dd/mm".
- **Virada da taxonomia (tema 26):** na D0 do TH-1/DP-2 (migração 034) nasce o L1 26 "Defesa Civil e Gestão de Desastres" (19.03 → 26.01, 19.04 → 26.02), com reclassificação só de parte do histórico. `calendario.TAXONOMY_CHANGE_2026` é a data (**provisória: 23/10/2026**; ajustar `TAXONOMY_CHANGE_2026_DEFAULT` para a D0 real antes do merge do PR-D, junto do pin em `test_virada_da_taxonomia_provisoria_e_configuravel`; o resto da suíte injeta a data ou lê a constante). Em produção, a data vem só da constante: o Terraform não declara `GOBUS_TAXONOMY_CHANGE_DATE`, e a env var no Cloud Run é gerida só por ele. Ajustar a D0 ou desligar o aviso (`TAXONOMY_CHANGE_2026_DEFAULT = None`) é um PR no código com deploy automático; o rollback é o revert do squash. A env var só simula a virada localmente. `TAXONOMY_CHANGED_THEMES` lista os temas cuja série muda (04, 05, 15, 19 e 26). Comparação de tema cujo baseline (ou a janela, na coerência) cruza a data e que mostra tema afetado ganha o aviso `TAXONOMY_CHANGED`, no padrão do `CLASSIFIER_CHANGED`: anomalias e forecast (flag `taxonomy_changed` e confiança −1 só nos temas afetados), coerência por tema e `detect_trends` (nota no cabeçalho e marca na linha). Builders aceitam `taxonomy_change=` (injetável nos testes; `None` desliga); as fixtures de UI fixam 27/10 (`TAXONOMY_CHANGE_FIXTURE`) para não depender da constante. O 26 fica em `SECURITY`; depois da virada, `"defesa"` vira tema ambíguo na coerência.
- **Janelas:** "últimos N dias" = dias fechados em BRT `[D−N, D−1]` (`calendario.closed_window`); `today`/`now` sempre injetáveis.
- **Anomalias e forecast (G2):** temas por share-of-voice de `topThemes` + `analyticsKpis` em janelas **móveis** (UTC), com gate de cobertura de classificação na janela e no baseline; entidades por `entityCoverage(DAY)` em janela **fechada** `[D−7, D−1]` (contagens em dias UTC), sem republicadoras, com precedência burst → new_entity → calendar_explained → coordinated_silence → concentrated_coverage → normal. O `volumeRatio` do upstream nunca aparece no Markdown; linhas do piso antigo (`vr/wc ≥ 100`) e de execuções antigas não viram candidatas. Concentrada e silêncio exigem o `min_count` da sensibilidade; abaixo dele a severidade é proporcional ao volume; `calendar_explained` e entidade sem menções próprias têm severidade 0; `burst`, `new_entity` e concentrada/normal com baseline < `min_count` (flag `thin_baseline`) ficam no máximo em `watch` (`SEVERITY_WATCH_MAX`). Linhas do `entityCoverage` da mesma (dia, agência) somam (o resolver agrupa também por nome); o dedup `(period, agencyKey)` é só do `agencyAnalytics` DAY. Na recuperação, só `resumed_after_blackout` (calada no último dia do defeso e de volta depois) explica sinal e conta em `resumed_agencies`; o `resumed` genérico é só informativo no health. No forecast, a razão de uma janela só conta com ≥ 5 artigos do tema (`w + b_prev`). Detalhes em `docs/tools/detect-anomalies.md` e `forecast-trends.md`.
- **Health:** `indexing_lag` compara o Typesense (`articles{found}`) com o Postgres (`agencyAnalytics` DAY) no dia D em **UTC** (D−1..D com menos de 20 artigos em D); `agency_activity` reaproveita o snapshot do `Deps.activity`; `entity_ranking` pede `isNew` (GA-1) e reporta `isNewShare` só entre as linhas com valor.
- **Coerência (F5):** emissores = agências não republicadoras com ≥ 2 artigos; republicadoras sempre em seção à parte; tom com pré-checagem de cobertura (4 aliases em paralelo com a página 1; abaixo de 50% não consulta por agência) e, se passar, aliases de contagem (agência × rótulo, 8 maiores emissores); aviso do defeso com as janelas alternativas concretas (`calendario.blackout_alternatives`; por entidade, desde `ENTITY_CANONICAL_INDEX_SINCE`); tempos por fase no log (INFO); no caminho por entidade, um `entityCoverage(DAY)` cobre os 30 dias antes (início truncado) e a janela (confere o Typesense: `INDEXING_LAG`; 0 contra N ou menos de 50% vira indisponível, degradado tira o timing), filtrado pelas `agencies` pedidas; amostra truncada (sort só decrescente) ou com página em falha também tira o timing; no caminho por tema, a cobertura de classificação da janela é medida (`THEMES_UNCLASSIFIED` dinâmico). Índice 1–5 provisório; calibração em `_experiments/coherence-calibration-2026-10/`. Detalhes em `docs/tools/get-message-coherence.md`.
- Estado em 05/10/2026: Flesch/wordCount parados desde 30/06; temas/resumo/sentimento desde 26/09; ranking de entidades com linhas legadas. Ver `gobus://health/pipelines` e `_plan/PLANO_FASE2_5.md`.

## Testes

`pytest-asyncio` com `asyncio_mode = "auto"` — não precisa de `@pytest.mark.asyncio` explícito.

`FakeGraphQLClient` (`tests/conftest.py`): em teste novo, use `route(nome_da_operacao, resposta)` — a resposta pode ser dict, exceção ou callable (sync/async) de `variables` — e `calls(nome)` para conferir as variáveis. `route_catalog(client)` registra as 3 operações do catálogo de agências. `set_response`/`set_responses` continuam para testes antigos. O `schema_compat.COMPAT` é limpo a cada teste (fixture autouse): para simular a API antiga, roteie a operação nova para um `GobusGraphQLError("Cannot query field …")` e a `<Op>Legacy` para a resposta.

```python
async def test_exemplo(fake_client):
    route_catalog(fake_client)
    fake_client.route("AgencySummaryAnalytics", {"agencyAnalytics": [...]})
    result = await get_agency_summary("saude", fake_client, today=date(2026, 10, 5))
    assert fake_client.calls("AgencySummaryAnalytics")[0]["agencies"] == ["saude"]
```

**MCP Apps (marker `ui`):** `tests/browser/` sobe um mini-host Playwright (`minihost.html`: iframe `sandbox="allow-scripts"` + CSP padrão da spec) e roda cada fixture de `tests/fixtures/ui/<app>/<estado>.json` em claro/escuro × 320/760 px, falhando com erro de console, violação de CSP, `alert()` ou altura fora de 100–2000 px. As fixtures saem dos builders reais (`tests/fixtures/ui/build.py`); `tests/test_ui/test_fixtures_contract.py` exige que estejam em dia (`make ui-fixtures`). O formato no fio fica em `tests/test_server/test_apps_wire.py` (com o relógio dos radares fixo em `NOW_0510`); previews e CORS de dev em `test_dev_preview.py` e `test_cors_dev.py` (o teste de "não aparece por padrão" sobe um subprocesso sem as variáveis `GOBUS_*`).

## Convenções

- **Idioma:** português em docstrings, comentários e mensagens; inglês em identificadores Python e nos enums dos payloads (rótulos PT só em texto).
- **Commits:** português, prefixos `fix:` / `feature:` / `refactor:` / `chore:` / `test:` / `docs:`; TDD com `test: … (red)` antes de `fix:`/`feature: … (green)`.
- **Sem Co-Authored-By** nos commits deste repo.
- Tools retornam Markdown formatado (não JSON) — são consumidas diretamente por LLMs. Artigo citado = título como link `formatting.md_link(título, url)` (`[título](url)`) e o `unique_id` na linha seguinte (em listas compactas, `formatting.article_ref`: `` [título](url) · `id` ``). As tools de texto terminam com o rodapé "Para explorar" (`formatting.with_follow_ups`: ≤ 3 chamadas concretas tiradas do resultado, ≤ 400 B; na coerência, depois do `fit_summary`); **nunca** nas 4 tools de MCP App. **Exceção — tools de app = summary + payload:** as 4 tools de MCP App devolvem o Markdown completo no `content` e, no `structuredContent`, o payload estruturado com o mesmo Markdown em `summary` (primeiro campo, até 6 KB). No Claude Code, que mostra o `structuredContent`, isso custa até ~20 KB (~7k tokens) por chamada; por isso o `summary` vem primeiro e o payload leva só o que o app desenha. As `gobus_dev_preview_*` (só dev) ficam fora da regra e da contagem de tools: devolvem fixtures marcadas "DEV — dados fictícios".
- **JS dos apps:** só `createElement`/`textContent` (o `render_app` recusa `innerHTML`, `eval`, storage do navegador, URL externa e template literal); limiares e cores vêm do payload, nunca codificados no JS.
- O repositório é público: nunca versionar IPs, ids de conta ou segredos (redigir como `<IP-CLOUD-SQL>`, `<AWS-ACCOUNT-ID>`).
