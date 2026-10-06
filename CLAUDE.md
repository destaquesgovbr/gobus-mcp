# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Gobus MCP

Servidor MCP (Model Context Protocol) que expõe o acervo do Destaques Gov.BR — ~300k artigos, grafo de entidades NER canonicalizadas, analytics por agência — como tools/resources/prompts para LLMs. Toda leitura de dados passa pela `graphql-api`; não há acesso direto a Postgres, Typesense ou Neo4j.

**Capacidades:** 13 tools (`gobus_*`, todas somente leitura), 7 resources e 4 prompts (`prompt_*`).

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
pytest                                          # todos
pytest tests/test_tools/test_search_news.py     # um arquivo
pytest -k test_retorna_artigos                  # um teste por nome
pytest -m live                                  # contra a graphql-api de produção (só leitura)

# Em worktree: a venv principal tem install editável apontando para o checkout principal
PYTHONPATH=$PWD/src .venv/bin/python3.12 -m pytest

# Lint e docs
ruff check src/ tests/
ruff format src/ tests/
mkdocs build --strict

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
config.py            # Settings (pydantic-settings, prefixo GOBUS_)
client.py            # GobusGraphQLClient — wrapper httpx; lança GobusGraphQLError em errors[]
cache.py             # TTLCache assíncrono, single-flight, relógio injetável
agency_catalog.py    # AgencyCatalog: nomes, republicadoras, validate (aliases curados + difflib), active()
calendario.py        # BRT, defeso 2026 (04/07–25/10), recuperação até 29/11, feriados, janelas fechadas
readability.py       # Flesch: escala (textstat-en), clamp 0–100, faixas 0/25/50/75, médias null-aware, janela efetiva
readability_data.py  # legibilidade por agência via agencyAnalytics (janela pedida/efetiva, agregação)
data_status.py       # saúde das fontes (ok|degraded|unavailable), detecção dinâmica → Notice
payloads/            # pydantic: common (ReportBase, DataStatus, Notice…), readability, scorecard
analytics/ratios.py  # limiar convertido do trendingThemes e razão sem sobreposição
tools/               # 13 tools (funções async puras, recebem client/catalog como arg)
resources/           # 7 resources: agencies, themes, platform-stats, taxonomy-queries,
                     #   readability-report (JSON), health/pipelines (JSON), ui://readability-dashboard (HTML)
prompts/             # 4 prompts: monitor_agency, trace_entity, weekly_digest, draft_press_release
```

**Padrão de separação:** cada tool é uma função async pura em `tools/<nome>.py` que recebe `GobusGraphQLClient` (e `catalog=` quando precisa de nomes/validação). O `server.py` lê `get_deps()` a cada chamada e repassa `deps.client`/`deps.catalog`; os testes trocam `server._deps`. Tools que viram MCP App no G3 separam `build_*_payload` (I/O → modelo pydantic) de `render_*_markdown` (puro); o Markdown vai em `summary`.

**Registro:** toda tool usa `@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})` — sem isso o fastmcp 3.4 embrulha o retorno `-> str` em `{"result": "…"}`. Resources JSON declaram `mime_type="application/json"`.

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
- `agencyAnalytics`: datas devem ser `datetime.date` no lado da graphql-api (strings ISO são rejeitadas pelo asyncpg); `dateTo` inclusivo; `metrics:` é ignorado pelo resolver
- `search()`: **não tem `limit`** e rejeita `query:""`; filtro de agência via `filter: {agencies: [...]}`. Para listar, use `articles(page, limit ≤ 250, filter, sort)`
- `articles.filter.startDate/endDate` aceitam offset (`-03:00`); `endDate` exclusivo. Dias da API em UTC
- `trendingThemes`: `TrendingThemeResult { themeLabel themeCode windowCount baselineDailyAvg growthScore topArticles }` — **`baselineDailyAvg`** (não `baseDailyAvg`, nem `baselineCount`); `themeCode` sempre `null`; o baseline **inclui a janela**: converta o limiar do usuário com `analytics.ratios.overlap_growth_threshold` e nunca envie `growthThreshold: 0` (dispara N+1 de `topArticles`)
- `trendingEntities`: `{ entityId canonicalName type trendingScore volumeRatio windowCount windowAgencies computedAt }`; o resolver limita a 50 e hoje mistura execuções antigas (ver `data_status.entity_ranking_status`)
- `features { trendingScore viewCount }` estão nulos em quase todo o acervo; não use como sinal

## Dados (estado e convenções)

- **Null ≠ 0:** métrica sem dado vira "indisponível"/`null`, nunca 0.0 nem nota neutra. Médias ignoram nulos (`readability.weighted_metric`).
- **Flesch:** fórmula inglesa do `textstat` (`FLESCH_SCALE_ID = "flesch_en_textstat"`), limitado a 0–100 com o bruto exibido quando houve clamp; faixas únicas 0/25/50/75.
- **Detecção dinâmica:** o estado das fontes é medido na resposta (`data_status`); datas de incidente (`SINCE_HINTS`) só redigem "desde dd/mm".
- **Janelas:** "últimos N dias" = dias fechados em BRT `[D−N, D−1]` (`calendario.closed_window`); `today`/`now` sempre injetáveis.
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

## Convenções

- **Idioma:** português em docstrings, comentários e mensagens; inglês em identificadores Python e nos enums dos payloads (rótulos PT só em texto).
- **Commits:** português, prefixos `fix:` / `feature:` / `refactor:` / `chore:` / `test:` / `docs:`; TDD com `test: … (red)` antes de `fix:`/`feature: … (green)`.
- **Sem Co-Authored-By** nos commits deste repo.
- Tools retornam Markdown formatado (não JSON) — são consumidas diretamente por LLMs. Exceção futura (G3): as tools de MCP App devolvem `summary` (= Markdown) + payload estruturado.
- O repositório é público: nunca versionar IPs, ids de conta ou segredos (redigir como `<IP-CLOUD-SQL>`, `<AWS-ACCOUNT-ID>`).
