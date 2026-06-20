# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Gobus MCP

Servidor MCP (Model Context Protocol) que expõe o acervo do Destaques Gov.BR — ~300k artigos, grafo de entidades NER canonicalizadas, analytics por agência — como tools/resources/prompts para LLMs. Toda leitura de dados passa pela `graphql-api`; não há acesso direto a Postgres, Typesense ou Neo4j.

**Deploy:** Cloud Run (`destaquesgovbr-gobus-mcp`). Push em `main` com mudanças em `src/`, `Dockerfile` ou `pyproject.toml` dispara CI que builda imagem Docker e faz deploy.

**Produção:** `https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app`

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

# Rodar localmente (stdio — para uso com Claude Desktop/Code)
python -m gobus_mcp
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
- `PORT` ausente → `stdio` (Claude Desktop/Code local)
- `PORT` presente (Cloud Run injeta 8080) → `http` (streamable-http stateless em `0.0.0.0:PORT`)

SSE **não** é usado em Cloud Run — causa race condition de inicialização com múltiplas instâncias.

## Queries GraphQL

As queries ficam embutidas como strings nas funções de tool (`_SEARCH_QUERY`, `_ANALYTICS_QUERY`, etc.). **Schema drift é o principal risco:** se a `graphql-api` mudar um nome de campo/argumento/tipo, as queries quebram em runtime.

Gotchas conhecidos do schema atual:
- Enum de tipo de entidade: `EntityKind` (não `EntityType`)
- `relatedEntities` e `entityNetwork` usam argumento `id:` (não `entityId:`)
- `RelatedEntity` retorna `canonicalId` (não `entityId`)
- Agências: `agencies { code label }` (não `key name`)
- `agencyAnalytics`: datas devem ser `datetime.date` no lado da graphql-api (strings ISO são rejeitadas pelo asyncpg)
- `search()`: filtro de agência via `filter: {agencies: [...]}` (não argumento direto); `trendingScore` fica em `features { trendingScore }`, não no root do Article

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
