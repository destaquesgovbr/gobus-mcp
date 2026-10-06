> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — relatório de investigação, gerado em 2026-10-05 por agente read-only (wf_98f5ad51-e18). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Mapeamento gobus-mcp para o plano da Fase 2.5

Repo: `/Users/nitai/dev/destaquesgovbr/gobus-mcp`. Branch `feature/fase2-analytics` (7021868). A árvore é igual a `origin/main` (94a6359, squash do PR #7), com um único diff em `CLAUDE.md` (+2 linhas). Nada foi editado. Os testes rodaram com `-p no:cacheprovider` para não escrever `.pytest_cache`.

## 0. Achados críticos (verificados em produção hoje)

Mudam o escopo do plano:

1. **`gobus_get_readability_recommendations(agency_key=...)` falha sempre em produção.**
   - Erro: `GraphQL errors: Unknown argument 'limit' on field 'Query.search'`.
   - Origem: `tools/get_readability_recommendations.py:34-51`, onde `search(query:, filter:, limit:)` usa um `limit` que não existe no schema. Os argumentos de `search` são `query, filter, page, semantic, alpha, dedup, sort`.
   - Validei as 29 constantes `_QUERY` de `src/` contra o schema vivo (graphql-core da venv da graphql-api). Esta é a única inválida. Os testes passam porque o client é mockado.
2. **O pipeline de Flesch/wordCount está morto desde 2026-07-01.**
   - `avgReadabilityFlesch` e `avgWordCount` são `null` em todos os meses de 2026-07 a 2026-10 (amostrei agencia_brasil, saude, secom, defesa, cgu). Também são `null` em jan e fev/2026. Só há cobertura de 2026-03 a 2026-06.
   - Por artigo: 80/100 com Flesch em 28–30/06 contra 0/100 em 01–02/07.
   - Efeito: `gobus://readability-report`, `ui://readability-dashboard` e o ranking de recomendações mostram Flesch 0.0 / gap −50 para todas as agências. Todo o código faz `or 0.0`.
   - `gobus://health/pipelines` reporta `flesch: OK` (falso), porque `null→0` não é negativo (`health_pipelines.py:94` + `:50-57`).
   - `score_article` em artigo de 2025-12 deu "Flesch N/A, 0 palavras (benchmark 0), densidade 8/10 (12 entidades em 0 palavras)", que é uma nota sem sentido.
3. **A classificação de temas está parada desde ~2026-09-26.**
   - Artigos com tema: 98/100 em 24–25/09, 3/51 em 26–27/09, 0/50 em 04–05/10.
   - `trendingThemes` com janela ≤9d devolve 0 temas mesmo com `growthThreshold:0, minArticles:1`. Com janela de 10d devolve 7 temas e 15 artigos.
   - Hoje `detect_anomalies` responde sempre "Nenhum pico sustentado" (janelas de 3d e 7d vazias).
   - `forecast_trends` só tem a janela de 21d, então todos os temas saem `estavel / baixa` com composite = 0.2×growth21 (máximo 0.22).
4. **`trendingEntities` está obsoleto e capado.**
   - SQL em `graphql-api/src/graphql_api/datasources/postgres.py:479-486`: `SELECT ... FROM entity_trending_scores ORDER BY trending_score DESC LIMIT $1`, sem filtro de `computed_at`.
   - O servidor capa em 50: pedi 500 e vieram 50. Essas 50 linhas têm 32 datas distintas de `computedAt` (2026-06-25 a 2026-10-05).
   - Nas 20 primeiras, todo `volumeRatio` é ≥1000 (máximo 8571.4, "Censo Escolar 2025", computado em 2026-07-03, cuja cobertura real acabou em junho).
   - `detect_anomalies(medium)` ao vivo marcou 15 de 20 como "cobertura concentrada".
5. **`health_pipelines._check_sentiment` usa a escala errada.**
   - `pctPositive` é fração 0..1 (`AVG(CASE ... THEN 1.0 ELSE 0.0)`, `graphql-api/.../postgres.py:333`).
   - O limiar é `mean < 5.0 → DEGRADED` (`health_pipelines.py:45`), então 100% positivo daria DEGRADED.
   - Os testes usam `pctPositive: 10.0` (`test_health_pipelines.py:39`), escala errada. Hoje `pctPositive` = 0.0 e `avgSentimentScore` = null em todas as agências.

## 1. server.py: registro, transporte e erros

- **Tools (`server.py:70-346`):** `@mcp.tool()` sem argumentos, todas `async def gobus_<nome>(...) -> str`.
  - O nome vem do nome da função. O prefixo `gobus_` é escrito à mão.
  - A docstring é a description, com parâmetros em texto livre ("Parâmetros:/Retorna:/Dica:"). Não há `Annotated`/`Field`, então o inputSchema não tem descrição por parâmetro.
  - Opcionais usam default `""`, convertido em `None` na chamada (`agency_key or None`).
  - Cada wrapper só delega para `tools/<nome>.py` passando `_client`, um singleton criado em `:61-65`.
- **Resources (`:351-390`):** `@mcp.resource("<uri>")` com `async def ... -> str`.
  - Nenhum declara `mime_type`.
  - O FastMCP 3.4.2 aplica `text/html;profile=mcp-app` a `ui://*` automaticamente (`fastmcp/utilities/mime.py:7`).
  - Os resources JSON (`readability-report`, `health/pipelines`) saem como `text/plain`.
- **Prompts (`:395-416`):** `@mcp.prompt()` síncronos, `-> list[dict]`, nomes `prompt_*`.
  - Os textos dos prompts referenciam tools **sem** prefixo (`search_news`, `get_agency_analytics`, `get_article`): `prompts/monitor_agency.py:17,20,23`, `weekly_digest.py:13,16,19`, `draft_press_release.py:17`, `trace_entity.py:33`. São nomes que não existem no servidor.
- **Introspecção real (in-memory `fastmcp.Client`):** 13 tools, todas com `meta={'fastmcp':{'tags':[]}}` e outputSchema gerado automaticamente. Nenhuma tem `meta.ui.resourceUri`. 7 resources, 4 prompts.
- **Erros:** não há try/except nas tools, exceto `get_policy_lifecycle.py:153-157,168-175`.
  - `httpx` e `GobusGraphQLError` sobem até o FastMCP, que devolve `isError=true` com o texto `"Error calling tool 'gobus_get_article': All connection attempts failed"` (testado). `mask_error_details` usa o default (False).
  - Mensagens de "não encontrado" são retornadas como Markdown normal.
- **Transporte (`main()`, `:419-444`):**
  - Sem `PORT`: `mcp.run()` em stdio.
  - Com `PORT`: `mcp.run(transport="http", host="0.0.0.0", port=port, stateless_http=True)` em `/mcp`.
  - Compatibilidade SSE: `SseServerTransport("/messages/")` (`:44`), `custom_route("/sse")` (`:47-54`) e `mcp._additional_http_routes.append(Mount("/messages", ...))` (`:57`). Usa API privada (`_mcp_server`, `_additional_http_routes`).

## 2. client.py e config.py

- `GobusGraphQLClient(url, api_key="", timeout=10.0)` (`client.py:14-17`). O header `X-API-Key` só é enviado se houver chave.
- `execute(query, variables=None) -> dict` (`:19-30`):
  - cria um `httpx.AsyncClient` novo por chamada (sem pool);
  - chama `raise_for_status()`;
  - lança `GobusGraphQLError(errors)` se houver `errors[]`;
  - devolve `body["data"]`.
  - **Sem retry, sem cache, sem métricas.**
- `config.py:4-18`: `Settings` do pydantic-settings, prefixo `GOBUS_`, lido de `.env`. Campos `graphql_url` (default `http://localhost:8000/graphql`), `graphql_api_key`, `request_timeout=10.0`, `log_level`. Avaliado no import.
- Paralelismo: `asyncio.gather` só em `detect_anomalies.py:56`, `forecast_trends.py:43` e `health_pipelines.py:76`.
  - Ficam sequenciais: `detect_anomalies.py:64` (entities depois do gather), `score_article.py:101,125`, `get_agency_summary.py:39,45`, `get_readability_recommendations.py:175,183`.

## 3. Padrão das tools

Cada tool é uma função async em `tools/x.py(client, ...) -> str` (Markdown), com queries como constantes de módulo. Helpers puros (`_x`) existem só em score_article, readability e policy_lifecycle.

### detect_anomalies.py (126 linhas)

- **Queries:**
  - `_THEMES_QUERY` (`:5-15`): `trendingThemes(windowDays, baselineDays, growthThreshold, limit){ themeLabel themeCode growthScore windowCount baselineDailyAvg }`.
  - `_ENTITIES_QUERY` (`:17-29`): `trendingEntities(limit){ entityId canonicalName type trendingScore volumeRatio windowCount windowAgencies }`, sem `computedAt`.
- **Chamadas:** temas 3d/21d e 7d/28d, ambas com `growthThreshold:0.5, limit:15`, em gather (`:56-63`). Depois `trendingEntities(limit:20)` (`:64`).
- **"Pico sustentado" (`:70-72`):** um tema é pico sustentado se a chave (`themeCode or themeLabel`) aparece nas duas listas. Não há limiar próprio.
  - O filtro real é o do servidor: growth ≥ 0.5 e windowCount ≥ 3 (default de `minArticles`). Portanto um tema que **caiu pela metade** conta como "pico".
  - `sensitivity` não afeta temas.
  - `themeCode` é sempre `None` no resolver (`graphql-api/src/graphql_api/schema/resolvers/analytics.py:233`), então a chave é o label.
- **"Cobertura concentrada" (`:74-83`):** `volumeRatio > vr_thr AND windowAgencies < wa_thr`, com limiares em `_SENSITIVITY` (`:32-36`):

  | sensitivity | volume_ratio | window_agencies |
  |---|---|---|
  | high | 2.0 | 8 |
  | medium | 3.0 | 5 |
  | low | 5.0 | 3 |

  `windowAgencies` null vira 999 e cai em "normal". Todo o resto vai para "Tendências Normais".
- **O que falta frente ao BLUEPRINT (`_experiments/uc-2026-06-30-v3/BLUEPRINT.md:59`):**
  - `domainFilter`;
  - o cruzamento com `agencyAnalytics(DAY)` da agência-dona;
  - o score de silêncio `volumeRatio ÷ atividadeAgênciaDona`.
- **Dado para desenhar o "dono":** `entity.agencyKey` / `entitySearch.agencyKey` existe mas é quase sempre null.
  - Só `dgb_saude→saude` tem valor. MEC `Q4294522`, PF e Anvisa estão null. 0 das 15 entidades trending top têm.
  - `entityCoverage(entityId, granularity:WEEK)` funciona como fonte de dono: Mais Médicos Especialistas → saude 55/57; Censo Escolar 2025 → inep 30, mec 29.
  - `policyDetails.responsibleAgencies` só se aplica a POLICY.
  - Para `domainFilter` existem `policyDetails.domain` e `policies(domain:)`.
- **Funções puras:** nenhuma; o algoritmo está inline.
- **Saída:** `## Detector...` seguido de `### Picos Sustentados`, `### Cobertura Concentrada`, `### Tendências Normais`. Os testes fatiam por `### `.

### forecast_trends.py (113 linhas)

- **Query:** a mesma `trendingThemes` (`:5-15`). Janelas em gather (`:43-53`), todas com `limit:20`:
  - 3d/14d com g=0.3;
  - 7d/28d com g=0.3;
  - 21d/84d com g=0.2.
- **Pesos `_WEIGHTS = {"3":0.5, "7":0.3, "21":0.2}` (`:18`):** `composite = Σ w·growth` (`:74`). Uma janela ausente conta como 0 e não há renormalização, então temas fora das janelas curtas são penalizados.
- **Momentum (`:75-82`):** `s3 > s7` dá acelerando, `<` dá desacelerando, igual dá estável. Os baselines são diferentes (14 contra 28), então os valores não são comparáveis. Com as duas janelas ausentes (0 = 0) o resultado é "estável".
- **Confiança (`:83`):** número de janelas em que o tema aparece; 3 = alta, 2 = média, 1 = baixa.
- **`horizon_days`:** usado **apenas** no título (`:95`).
- **Fim de semana:** só uma nota textual (`:107-111`).
- **Teto matemático do growth no resolver:** o baseline inclui a janela, porque os dois filtros são `published_at >= now-N` (`analytics.py:195-210`). Logo growth ≤ baselineDays/windowDays: 3/14 → 4.67, 3/21 → 7, 7/28 → 4, 21/84 → 4.
- **Outros detalhes do resolver:** baseline zero vira 0.001/dia (`analytics.py:228`); `window >= baseline` gera ValueError (`:190`); as janelas são rolantes em UTC a partir de "agora", não alinhadas ao dia.
- **Saída:** tabela `| Tema | Score Composto | Momentum | Confiança |` com `composite:.2f`.

### score_article.py (160 linhas)

- **Queries:** `article(uniqueId){ uniqueId title agency agencyName publishedAt features{ readabilityFlesch wordCount entities{type} } }` (`:5-20`) e `agencyAnalytics(... MONTH){ articleCount avgReadabilityFlesch avgWordCount }` (`:22-30`), esta com benchmark de 90 dias (`:122-130`).
- **Funções puras:**
  - `_readability_score` (`:33-45`): ≥50 → 10, ≥30 → 7, ≥10 → 5, ≥0 → 3, <0 → 1; None → None.
  - `_conciseness_score` (`:48-61`): razão vs benchmark ≤0.8 → 10, ≤1.0 → 8, ≤1.3 → 6, ≤1.6 → 4, senão 2; sem base → 5.
  - `_entity_density_score` (`:64-74`): entidades por 100 palavras ≥2 → 8, ≥1 → 6, ≥0.5 → 4, senão 2. O denominador é `max(wc/100, 1)`, então com wc null a densidade vira o número bruto de entidades (inflado).
  - `_weighted_benchmark` (`:77-84`): `null→0`, ponderado por articleCount, que inclui artigos sem features.
- **Nota final (`:138-139`):** 0.5·R + 0.3·C + 0.2·D; R None vira 5.0.
- **Saída:** Markdown com "Nota Geral X/10", "Notas por Dimensão" e "Benchmark da Agência".
- **Para o scorecard ui://:** a Agência Brasil como padrão-ouro e a mediana da agência ainda não existem.

### get_readability_recommendations.py (233 linhas)

- **Funções puras:**
  - `_flesch_label` (`:54-65`): <0 "abaixo do piso", <25 muito difícil, <50 difícil, <75 médio, senão fácil.
  - `_recommendations` (`:68-93`): 4 blocos fixos de 3 dicas.
- **Modo ranking (`:117-171`):** `agencyAnalytics` sobre `_ACTIVE_AGENCIES` (`:5-9`), média ponderada com `or 0.0` (`:141`), ordenada desc, `[:limit]`. O texto "Benchmark interno: Agência Brasil (~33.5)" está hardcoded (`:170`, também na docstring `server.py:267-269`).
- **Modo agência (`:173-233`):** analytics, depois `_SEARCH_QUERY` inválida (quebra, ver 0.1). Média ponderada (`:197-209`).

### get_agency_summary.py (85 linhas)

- **Chamadas sequenciais:** `agencyAnalytics(MONTH)` dos últimos N dias (`:39-44`), depois `trendingThemes(7, 28, g=1.0, agencyKey, limit 5){ themeLabel growthScore windowCount topArticles{...} }` (`:45-51`).
- **Flesch:** pega a primeira linha "truthy" (`:69-72`), sem ponderação; 0 e None são pulados.
- **Rótulo próprio:** >70 fácil, >50 médio, senão difícil (`:74`), diferente do de readability.
- **Ao vivo (saude):** "116 artigos", sem linha de legibilidade e sem temas.

### Escalas de Flesch inconsistentes

Há 4 tabelas de faixas diferentes:
- `get_article.py:76` e `get_agency_analytics.py:83`: 70/50;
- `get_agency_summary.py:74`: 70/50;
- `get_readability_recommendations.py:54-65`: 0/25/50/75;
- `readability_dashboard.py:36-47`: 0/25/50/75, em cores;
- `score_article.py:33-45`: 50/30/10/0.

## 4. Testes

- **Layout:** `tests/conftest.py` mais `tests/test_tools/` (13 arquivos, 70 testes) e `tests/test_resources/` (5 arquivos, 20 testes). Total: **90**.
- **Mock:** `FakeGraphQLClient` (`conftest.py:6-16`) com `execute = AsyncMock`.
  - `set_response(dict)` devolve sempre a mesma resposta.
  - `set_responses([..])` usa `side_effect` em ordem. A ordem precisa bater com a ordem das chamadas, inclusive dentro do `gather`.
  - Fixture `fake_client`. Sem respx, sem monkeypatch, sem tempo congelado (as tools chamam `date.today()` direto).
- **Configuração:** `asyncio_mode="auto"` (`pyproject.toml:30-31`). Alguns arquivos antigos ainda usam `@pytest.mark.asyncio` e `class Test*`.
- **Exemplos:**
  - tool: `test_detect_anomalies.py` (helpers `_theme`/`_entity`, `_section(md, header)`);
  - ui://: `test_readability_dashboard.py:18-60`.
- **Lacunas:** nenhum teste de `server.py` (registro, nomes, mime), `client.py` ou contrato de schema.
- **Comando e resultado:**
  ```
  cd /Users/nitai/dev/destaquesgovbr/gobus-mcp && .venv/bin/python3.12 -m pytest -q
  ```
  **90 passed in 0.16s.** Python 3.12.8, pytest 9.1.0, pytest-asyncio 1.4.0.

## 5. MCP App existente: `resources/readability_dashboard.py` (261 linhas)

- **Geração:** HTML montado numa f-string inline (`:196-259`). O SVG de barras é gerado no servidor por `_render_bar_chart_svg` (`:50-86`). O CSS é inline.
- **Dados:** JSON island `<script type="application/json" id="readability-data">` (`:221-223`) com `json.dumps(agencies_data)`.
- **JS:** não há biblioteca de gráfico. Existe uma classe **falsa** `Chart` com `render()` que só faz `console.info` (`:158-194`) e um `<canvas>` com `display:none`. Isso é um artefato para satisfazer o teste `test_html_contem_canvas_chartjs` (`test_readability_dashboard.py:24-29`, que exige `<canvas` e `"Chart"`).
- **Escaping:** nomes de agência entram no HTML sem `html.escape` (`:246`), e `</` dentro do JSON não é escapado.
- **Mime:** não declarado em `server.py:375`. Sai como `text/html;profile=mcp-app` por causa do default do fastmcp 3.4.2. Com o fastmcp 2.1.2 do `poetry.lock` isso não aconteceria.
- **Ligação tool→UI:** nenhuma tool referencia o `ui://` (`meta` vazio).
- **O que o fastmcp 3.4.2 oferece:**
  - `@mcp.tool(app=AppConfig(resource_uri="ui://...", visibility=[...]))`;
  - `@mcp.resource("ui://...", app=AppConfig(csp=..., prefers_border=...))`. Em resource, `resource_uri` é proibido (`fastmcp/server/server.py:1893`).
  - `fastmcp.apps` exporta `AppConfig, ResourceCSP, ResourcePermissions, UI_MIME_TYPE, UI_EXTENSION_ID="io.modelcontextprotocol/ui"`.
  - `fastmcp.tools.tool.ToolResult(content, structured_content, meta)` permite devolver o texto mais o JSON que a App consome.
- **Testes do dashboard (6):** doctype, canvas/Chart, nomes no HTML, ausência de `src|href="https?://`, `avgReadabilityFlesch` no HTML, string não vazia.

## 6. Agency keys hardcoded e catálogo

`agencies` ao vivo: **156** agências. `isRepublisher=true`: `agencia_brasil`, `tvbrasil`, `ebc`.

| Local | Lista | Chaves inválidas |
|---|---|---|
| `tools/get_readability_recommendations.py:5-9` `_ACTIVE_AGENCIES` | 20 | `trabalho` (o certo é `trabalho-e-emprego`), `cgcom`, `tcu`, `ibge`, `caixa` |
| `resources/readability_dashboard.py:6-10` `_ACTIVE_AGENCIES` (cópia) | 20 | as mesmas 5 |
| `resources/readability_report.py:7-11` `_AGENCIES` | 20 | `trabalho`, `ipea`, `sus`, `ibge`, `senado`, `camara` |
| `resources/health_pipelines.py:7` `_HEALTH_AGENCIES` | secom, agencia_brasil, saude | nenhuma, mas `secom` tem 0 artigos desde 07/2026 (defeso; 11 em julho) |
| docstring `tools/get_agency_analytics.py:40` | `["mec","ms"]` | `ms` |

- Exemplos válidos: `server.py:83,192,242,263` (saude, mec, cgu, defesa) e `prompts/monitor_agency.py:5` (mec).
- Válidas mas sem linhas nos últimos 90 dias: `agu`, `secom`.
- As listas omitem os maiores volumes de 90 dias: `pf` 1154, `tvbrasil` 1031, `mdr` 274, `antt` 189.
- `resources/agencies.py:3-23`: query `{ agencies { code label } }`, devolve Markdown ordenado por label. Não pede `isRepublisher`, não tem cache e não expõe função de validação.
- **Fonte dinâmica de "agências ativas":** `topAgencies(range:{days:90}, limit:20){ name count }`, onde `name` é o código. Ao vivo: agencia_brasil 3560, pf 1154, tvbrasil 1031, saude 540, mec 501…

## 7. Consumo de Flesch e clamp

Não há clamp em lugar nenhum.
- `tools/get_article.py:20,68,75-77`: `if flesch:` esconde 0; negativo aparece como "difícil (-12)".
- `tools/get_agency_analytics.py:23,73,82-84`.
- `tools/get_agency_summary.py:11,69-75`.
- `tools/score_article.py:14,26,33-45,82,114,134,142,156`.
- `tools/get_readability_recommendations.py:28,54-65,141-148,199-212`.
- `resources/readability_report.py:22,63-76`: gap = avg − 50.
- `resources/readability_dashboard.py:29,36-47,58-64` (usa `abs()` na largura da barra), `:125-140,247`.
- `resources/health_pipelines.py:15,50-57,94-97`.

Os valores negativos são reais: em 2026-03..06 defesa ficou entre −18 e −27 e cgu entre −0.1 e −1.9. Os testes fixam −22.9/−1.2 e o rótulo "abaixo do piso" (`test_get_readability_recommendations.py:54-59`). Um clamp para [0,100] precisa ajustar esses testes e as cores do dashboard.

O problema maior é `null → 0.0` combinado com ponderação por `articleCount` que inclui artigos sem features. Isso dilui ou zera as médias, e é o que acontece hoje.

## 8. readability_report.py e health_pipelines.py

- **`readability_report.py` (86 linhas):**
  - 90 dias, granularidade MONTH, 20 chaves fixas, `_TARGET_FLESCH=50` (`:13`).
  - Média ponderada com `null→0`, `gapToTarget = avg − 50`, ordenação desc.
  - JSON `{generatedAt, targetFlesch, agencies[]}`, mime `text/plain`. 3 testes.
- **`health_pipelines.py` (108 linhas):**
  - Amostra 3 agências em 30 dias (MONTH) e `trendingEntities(limit:5)` em gather.
  - **trendingScore:** DEAD se todos < 1.0; DEGRADED se algum None; senão OK.
  - **sentiment:** média de `pctPositive` ≤ 0 dá DEAD; < 5.0 dá DEGRADED (bug de escala); senão OK.
  - **flesch:** DEAD se todas negativas; DEGRADED se alguma negativa; senão OK. Não detecta null.
  - Agências com count 0 são descartadas.
  - Não há checagem de: `computedAt` obsoleto, atraso de temas, cobertura de features, volume por agência (defeso).
  - Resultado ao vivo: `trendingScore OK`, `sentiment DEAD`, `flesch OK` (falso).
  - 3 testes.

## 9. Infra, dependências e convenções

- **Dockerfile:** `python:3.12-slim`, `pip install .`. **Não usa o lock**: o fastmcp `^3.0` resolve para o 3.x mais recente no momento do build, o que não é reproduzível. `CMD python -m gobus_mcp`, `EXPOSE 8080`.
- **`.github/workflows/deploy.yaml`:**
  - só deploy, via `destaquesgovbr/reusable-workflows/.github/workflows/cloud-run-deploy.yml@v2` (docker build/push e deploy; sem testes);
  - gatilhos: push em `main` com mudança em `src/gobus_mcp/**`, `Dockerfile`, `pyproject.toml` ou no próprio workflow, mais `workflow_dispatch`;
  - **não há CI de testes nem de lint**;
  - último deploy: 2026-07-01 20:55, sucesso.
- **Makefile:** só `docs-serve` e `docs-build` (`mkdocs build --strict`).
- **pyproject vs poetry.lock vs .venv:**

  | Pacote | pyproject | poetry.lock | .venv |
  |---|---|---|---|
  | fastmcp | `^3.0` | **2.1.2** | **3.4.2** |
  | mcp | — | 1.28.0 | 1.28.0 |
  | httpx | `>=0.28.1` | 0.27.2 | 0.28.1 |
  | pytest | `^8.0` | 8.4.2 | 9.1.0 |
  | pytest-asyncio | `^0.23` | 0.23.8 | 1.4.0 |
  | ruff | `^0.3` | 0.3.7 | não instalado |
  | mkdocs-material | `>=9.5` | — | não está na venv (só em `~/Library/Python/3.9/bin/mkdocs`) |
  | starlette / uvicorn | — | 1.3.1 / 0.49.0 | 1.3.1 / 0.49.0 |

  `poetry check --lock`: `Error: pyproject.toml changed significantly since poetry.lock was last generated`. As dependências de dev estão num grupo do poetry, então o `pip install -e ".[dev]"` recomendado no `CLAUDE.md:42,70` não instala nada de dev.
- **CLAUDE.md:**
  - Idioma: português em docs, comentários e mensagens; inglês em identificadores (`:149`).
  - Commits em português com prefixos `fix:/feature:/refactor:/chore:` (`:150`). Na prática o histórico também usa `feat:`, `test:`, `docs:`.
  - **"Sem Co-Authored-By nos commits deste repo"** (`:151`). Prevalece sobre a atribuição padrão.
  - Tools retornam Markdown, não JSON (`:152`).
  - Fluxo TDD visível no histórico: `test: ... (red)` e depois `feature: ... (TDD green)`.
  - Branches `feature/faseN-<tema>`; PR squash em main com título `feat: Fase N — ...`.
  - Erros no próprio CLAUDE.md:
    - `:131` diz `baseDailyAvg`, mas o schema vivo e o código usam `baselineDailyAvg`, e `themeCode` vem sempre null;
    - `:108` "3 resources estáticos" (são 7);
    - `:15-21` contradiz o `.mcp.json` do repo.
- **README.md:** 1 linha (`# gobus-mcp`).
- **Docs (mkdocs):**
  - `docs/tools/` tem 7 páginas, uma por tool antiga. Faltam 6: agency_summary, readability_recommendations, policy_lifecycle, detect_anomalies, forecast_trends, score_article.
  - `docs/resources/` tem 3 de 7.
  - `mkdocs.yml` nav precisa ser atualizado a cada tool nova (convenção de uma página por tool).
  - Contagens obsoletas: `docs/index.md:31` ("Tools 7") e `docs/arquitetura.md:5` ("7 tools, 3 resources").
  - gh-pages publicado manualmente (último build 2026-06-24, da 4368d43). O site está obsoleto.

## 10. Higiene

- **`git status`:**
  - Deletado sem stage: `_plan/PLANO.md`. É um rename: o untracked `_plan/PLANO_V1.md` é byte a byte idêntico.
  - Modificados: `mkdocs.yml` (+12, nav "Experimentos" apontando para `docs/experimentos/2026-06-24/*`, que está untracked) e `docs/deploy.md`.
  - A mudança em `docs/deploy.md` **está errada**: troca "transport HTTP" por "transport SSE, expondo /sse". Não deve ser commitada.
  - Untracked: `.claude/handoffs/`, `_experiments/` (inclui o BLUEPRINT), `_plan/{EXPERIMENTO_10_UCS, EXPERIMENTO_V3, HANDOFF_TO_DESIGN, PLANO_BUGS_FEATURES, PLANO_FASE1_POLICY, PLANO_V1, PLANO_V2, STATUS_NER_BACKFILL}.md`, `docs/experimentos/`. `site/` está no `.gitignore`.
- **Branches (após `git fetch --prune`):**
  - `main` local está ahead 3 / behind 2 de `origin/main`. Os 3 commits (2f90535, 4519c20, ede3e5c) são pré-squash e já estão incorporados em 9772e7f/94a6359; a diferença se resume a docs/POLICY_ONTOLOGY.
  - `docs/mkdocs` local tem upstream `gone`.
  - `origin/feature/fase1-docs-mcp-local` e `origin/feature/fase2-analytics` continuam no remoto, já mergeadas.
- **`gobus-mcp/.mcp.json`:** `{"gobus":{"url":".../sse"}}`.
- **`/Users/nitai/dev/destaquesgovbr/.mcp.json`:** stdio, `command: .../gobus-mcp/.venv/bin/python3.12`, `args ["-m","gobus_mcp"]`, `cwd` no repo, `GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql`. O workspace não é repositório git.
- **Issue #3 (aberta, 2026-06-26), "Limpar artigos MOCK em produção":**
  - Pede um `DELETE FROM news WHERE summary LIKE '[MOCK]%'` direto no Cloud SQL (<IP-CLOUD-SQL>, `govbrnews`), revisando o SELECT antes e confirmando o trigger do Typesense. P2.
  - Ao vivo, existe pelo menos um: `suica-amplia-contribuicao-ao-fundo-amazonia-com-nova-doacao-de-r-33-milhoes_dedae7` (secom, 2025-11-10), com summary "[MOCK] Resumo gerado para teste local". O título é limpo, então o marcador está só no summary.
  - É uma operação de dados, não código do gobus-mcp.
- **Fechadas:** #4 (SSE → streamable-http, fechada em 2026-07-01 pela dupla /mcp+/sse) e #2 (desempenho do agente, 2026-06-30).
- **PRs mergeados:** #1 (docs), #5 (dual transport), #6 (Fase 1), #7 (Fase 2).

## Implicações para o plano

**Front 1 (PR de limpeza)**
- Incluir o fix de `get_readability_recommendations.py:35` (remover `limit:` e fatiar no cliente).
- Adicionar um teste de contrato que valide todas as constantes `*_QUERY` de `src/` contra um snapshot do schema (graphql-core ou introspecção). O schema drift é o risco declarado no `CLAUDE.md:122`.
- Commitar `_plan/` (registrar `PLANO.md → PLANO_V1.md` como rename), `_experiments/`, `docs/experimentos/` e o nav do `mkdocs.yml`.
- **Não** commitar `docs/deploy.md` como está; reverter para o texto anterior.
- Corrigir o `CLAUDE.md`:
  - `:131` → `baselineDailyAvg` e `themeCode` sempre null;
  - `:108` → contagem de resources;
  - `:42,:70` → instrução de instalação de dev.
- Regenerar `poetry.lock` (`poetry lock`) e travar o fastmcp em `~3.4`, porque as MCP Apps dependem de `app=`/`AppConfig` e do mime automático.
- Fazer o Dockerfile instalar a partir do lock.
- Adicionar CI de testes (`pytest` + `ruff`) antes ou junto do deploy.
- `gobus-mcp/.mcp.json`: alinhar com o stdio do workspace, ou remover/documentar.
- Mime explícito `application/json` em `gobus://readability-report` e `gobus://health/pipelines`.
- Prompts: renomear as referências para `gobus_*`.
- Flesch:
  - criar um módulo comum `readability.py` com `clamp`, um rótulo único e média ponderada que **ignora null**, com contagem de cobertura;
  - quando não houver dado, devolver "sem dado (pipeline parado desde 2026-07-01)" em vez de 0.0;
  - ajustar os testes que fixam −22.9 e "abaixo do piso".
- Agency keys:
  - criar `agency_catalog.py` com `agencies{code label isRepublisher}` e `topAgencies(range:{days:N},limit:K){name count}`, com cache TTL;
  - substituir as 3 listas e validar `agency_key` nas tools, sugerindo correções (`difflib`; ex.: `trabalho → trabalho-e-emprego`);
  - corrigir `ms` em `get_agency_analytics.py:40`.
- `health_pipelines`:
  - escala de `pctPositive` em fração (limiar 0.05) e corrigir os testes;
  - tratar Flesch null ou com cobertura baixa como DEAD/DEGRADED;
  - novos checks: `computedAt` máximo de trendingEntities, atraso de classificação de temas (`trendingThemes(windowDays≤9)` vazio) e agências zeradas.
- Issue #3: tratar como tarefa de dados separada (precisa de acesso de escrita ao Cloud SQL e aprovação). No código, no máximo um filtro defensivo `summary.startswith("[MOCK]")` em `search_news`.

**Front 2 (upstream `trendingEntities`)**
- O fix é na graphql-api (`postgres.py:479-486`): `WHERE computed_at = (SELECT max(computed_at) ...)`, ou `DISTINCT ON` com janela.
- Avaliar também um piso de baseline no DAG, porque `volumeRatio` explode quando o baseline é ~0.
- No gobus-mcp: pedir `computedAt` em `detect_anomalies._ENTITIES_QUERY` e descartar no cliente linhas com mais de N dias, como defesa enquanto o upstream não sai.

**Front 3 (anomalias e forecast)**
- Bloqueador: com a classificação de temas parada desde ~26/09, as janelas de 3d e 7d ficam vazias.
  - Ou o pipeline de temas é consertado antes;
  - ou as tools detectam "janela sem dados classificados" e avisam, em vez de dizer "nenhum pico".
- Extrair funções puras testáveis, todas recebendo `today: date` injetável:
  - `classify_sustained(themes_a, themes_b, min_growth)`, com limiar real ≥1.5 (hoje vale 0.5 implícito);
  - `silence_score(entity, owner_activity)`;
  - `composite(scores, weights)`, renormalizando pelas janelas presentes;
  - `momentum(...)`, usando a razão normalizada pelo teto `baseline/window`;
  - `election_blackout(date)`, para o período 2026-07-04..2026-10-25.
- **Silêncio coordenado:**
  - dono = agência dominante em `entityCoverage(WEEK)` no baseline (`entity.agencyKey` não serve);
  - atividade do dono via `agencyAnalytics(DAY)` na janela;
  - `domainFilter` via `policyDetails.domain`/`policies(domain:)` ou via label de tema.
- **Defeso:**
  - marcar a saída e baixar a confiança dentro do período;
  - aplicar supressão ou normalização por agência nas 3–4 semanas após 25/10, porque a retomada vai gerar picos falsos;
  - excluir dos baselines os dias de defeso para as 15 agências zeradas.
- **forecast:**
  - usar `horizon_days` de fato (por exemplo, escolher as janelas ou extrapolar momentum);
  - correção de fim de semana: alinhar as janelas a dias úteis ou normalizar por dia útil;
  - ou adicionar o parâmetro `weekendCorrection=True` do BLUEPRINT `:60`.

**Front 4 (MCP Apps)**
- Seguir o padrão do dashboard: HTML gerado no servidor, JSON island, SVG server-side, testes de "sem refs externas".
- Eliminar o `Chart` falso e o teste que o exige.
- Registrar com `@mcp.resource("ui://anomaly-radar")` etc.
- Ligar cada tool com `@mcp.tool(app=AppConfig(resource_uri="ui://..."))` e devolver `ToolResult(content=markdown, structured_content=payload)`. Isso mantém o Markdown que o `CLAUDE.md` exige para os LLMs.
- Adicionar teste de servidor via `fastmcp.Client(mcp)` em memória: `list_resources` → mime `text/html;profile=mcp-app`; `list_tools` → `meta.ui.resourceUri`.
- Usar `html.escape` nos nomes e escapar `</` no JSON.
- O scorecard depende de Flesch e wordCount, mortos desde 07/2026: limitar a artigos de 2026-03..06 ou exibir "sem dado".

**Front 5 (`gobus_get_message_coherence`)**
- `ArticleFeatures.entities: [EntityType!]!` com `{text type count canonicalId salience}` e `Agency.isRepublisher` existem no schema vivo.
- `ArticleFilter` aceita `themeLabel`, `agencies`, `startDate`/`endDate`, `entityCanonical`, `dedup`.
- O componente de dispersão de Flesch do BLUEPRINT (`:63`) fica inviável no período pós-07/2026. Basear em entidades, timing e enquadramento, e excluir republishers via `isRepublisher`.

**Processo**
- TDD red→green em commits separados, sem Co-Authored-By, prefixos em português.
- Cada tool nova precisa de:
  - wrapper em `server.py` com docstring no formato atual;
  - `tools/<nome>.py` mais `tests/test_tools/test_<nome>.py`;
  - `docs/tools/<nome>.md` e entrada no nav do `mkdocs.yml`;
  - atualização das contagens em `docs/index.md:31`, `docs/arquitetura.md:5` e `CLAUDE.md`.
- O deploy só acontece no push em main que toque `src/`.
