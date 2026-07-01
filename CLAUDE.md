# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Gobus MCP

Servidor MCP (Model Context Protocol) que expõe o acervo do Destaques Gov.BR — ~300k artigos, grafo de entidades NER canonicalizadas, analytics por agência — como tools/resources/prompts para LLMs. Toda leitura de dados passa pela `graphql-api`; não há acesso direto a Postgres, Typesense ou Neo4j.

**Deploy:** Cloud Run (`destaquesgovbr-gobus-mcp`). Push em `main` com mudanças em `src/`, `Dockerfile` ou `pyproject.toml` dispara CI que builda imagem Docker e faz deploy.

**Produção:** `https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app`

## MCP no Claude Code

> **Atenção: Claude Code CLI não consegue usar os endpoints HTTP do servidor remoto em chamadas de subagente.**
>
> Dois bugs conhecidos impedem o uso HTTP:
> - `/sse` (spec 2024-11-05): sessão SSE expira entre chamadas independentes de subagente → erro `-32602 Invalid request parameters` em 100% das chamadas.
> - `/mcp` (spec 2025-03-26 Streamable HTTP): o Claude Code CLI envia GET em vez de POST → falha de conexão.
>
> **Solução: executar o servidor localmente (stdio transport).** O stdio não tem estado de sessão e funciona perfeitamente.

### Configuração para Claude Code (stdio local)

Crie ou edite o `.mcp.json` na raiz do **workspace** (não do repositório gobus-mcp):

```json
{
  "mcpServers": {
    "gobus": {
      "command": "python",
      "args": ["-m", "gobus_mcp"],
      "cwd": "/caminho/absoluto/para/gobus-mcp",
      "env": {
        "GOBUS_GRAPHQL_URL": "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"
      }
    }
  }
}
```

Substitua `cwd` pelo path absoluto do clone local deste repositório. Pré-requisitos: Python 3.12+ com `pip install -e ".[dev]"` dentro do venv.

Para o workspace `/Users/nitai/dev/destaquesgovbr`, o arquivo correto é `/Users/nitai/dev/destaquesgovbr/.mcp.json` (já configurado).

### Configuração para Claude Desktop / uso web

O endpoint remoto `/sse` funciona bem para clientes que mantêm sessão persistente (Claude Desktop, claude.ai):

```json
{
  "mcpServers": {
    "gobus": {
      "url": "https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/sse"
    }
  }
}
```

### Endpoints disponíveis no servidor remoto

- `/sse` + `/messages` — SSE (spec 2024-11-05). Para Claude Desktop e clientes com sessão persistente.
- `/mcp` — Streamable HTTP stateless (spec 2025-03-26). Para clientes que suportam a spec atual (Claude Code CLI tem bug: envia GET em vez de POST — não usar).

## Comandos

```bash
# Venv + deps
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # ou: poetry install

# Testes
pytest                           # todos
pytest tests/test_tools/test_search_news.py   # um arquivo
pytest -k test_retorna_artigos   # um teste por nome

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Rodar localmente (stdio — para uso com Claude Desktop)
python -m gobus_mcp

# Rodar localmente apontando para a graphql-api de produção
GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql python -m gobus_mcp
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
server.py          # entrypoint FastMCP — registra tools/resources/prompts
config.py          # Settings (pydantic-settings, prefixo GOBUS_)
client.py          # GobusGraphQLClient — wrapper httpx; lança GobusGraphQLError em errors[]
tools/             # lógica de cada tool (funções async puras, recebem client como arg)
resources/         # 3 resources estáticos: agencies, themes, platform-stats
prompts/           # 4 prompts compostos: monitor_agency, trace_entity, weekly_digest, draft_press_release
```

**Padrão de separação:** cada tool é uma função async pura em `tools/<nome>.py` que recebe `GobusGraphQLClient` como argumento. O `server.py` cria um `_client` singleton e o passa nas chamadas. Isso permite testar as funções isoladamente com `FakeGraphQLClient`.

**Transport:** determinado em runtime pelo env var `PORT`:
- `PORT` ausente → `stdio` (Claude Desktop local)
- `PORT` presente (Cloud Run injeta 8080) → HTTP stateless em `0.0.0.0:PORT`; endpoints `/mcp` (primário) e `/sse` + `/messages` (backward-compat)

Com `/mcp` stateless, o `max_instance_count=1` no Terraform pode ser relaxado — não há mais sessão em memória para perder entre instâncias.

## Queries GraphQL

As queries ficam embutidas como strings nas funções de tool (`_SEARCH_QUERY`, `_ANALYTICS_QUERY`, etc.). **Schema drift é o principal risco:** se a `graphql-api` mudar um nome de campo/argumento/tipo, as queries quebram em runtime.

Gotchas conhecidos do schema atual:
- Enum de tipo de entidade: `EntityKind` (não `EntityType`)
- `relatedEntities` e `entityNetwork` usam argumento `id:` (não `entityId:`)
- `RelatedEntity` retorna `canonicalId` (não `entityId`)
- Agências: `agencies { code label }` (não `key name`)
- `agencyAnalytics`: datas devem ser `datetime.date` no lado da graphql-api (strings ISO são rejeitadas pelo asyncpg)
- `search()`: filtro de agência via `filter: {agencies: [...]}` (não argumento direto); `trendingScore` fica em `features { trendingScore }`, não no root do Article
- `trendingThemes`: retorna `TrendingThemeResult { themeLabel themeCode growthScore windowCount baseDailyAvg topArticles }` — **não** `label` nem `baselineCount` (blueprint desatualizado); usar `themeLabel` e `baseDailyAvg`
- `trendingEntities`: retorna `{ entityId canonicalName type trendingScore volumeRatio windowCount windowAgencies computedAt }` — bate 100% com o blueprint

## Testes

`pytest-asyncio` com `asyncio_mode = "auto"` — não precisa de `@pytest.mark.asyncio` explícito.

`FakeGraphQLClient` em `tests/conftest.py` tem `execute = AsyncMock`. Configure a resposta com `client.set_response({"nomeDaQuery": {...}})` antes de chamar a função de tool.

```python
async def test_exemplo(fake_client):
    fake_client.set_response({"search": {"articles": [...], "found": 1, "page": 1}})
    result = await search_news("tema", fake_client)
    assert "título" in result
```

## Convenções

- **Idioma:** português em docstrings, comentários e mensagens; inglês em identificadores Python.
- **Commits:** português, prefixos `fix:` / `feature:` / `refactor:` / `chore:`.
- **Sem Co-Authored-By** nos commits deste repo.
- Tools retornam Markdown formatado (não JSON) — são consumidas diretamente por LLMs.
