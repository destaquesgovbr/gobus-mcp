# Início Rápido

Há duas formas de usar o Gobus MCP: **stdio local** (recomendado para Claude Code e para quem desenvolve o servidor) ou o servidor hospedado em **produção** via HTTP (`/mcp`), para Claude Desktop e claude.ai.

## 0. Claude Code — stdio local (recomendado)

O Claude Code CLI tem problemas com os transports HTTP remotos em chamadas de subagente (`/sse` expira a sessão entre chamadas; `/mcp` falhou na conexão nos testes). Rodar o servidor localmente em **stdio** evita os dois: não há sessão a perder.

**Pré-requisitos:** Python 3.12 e as dependências instaladas na venv do repositório.

```bash
cd /caminho/para/gobus-mcp
python3.12 -m venv .venv
poetry install --with dev        # usa a .venv do projeto (Poetry 2.0.1)
# sem Poetry: .venv/bin/pip install -e . pytest pytest-asyncio ruff graphql-core mkdocs-material
```

O repositório já traz um **`.mcp.json`** com a entrada `gobus-local`; abra o Claude Code na raiz do clone:

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

O caminho do `command` é relativo à raiz do repositório. Para usar o gobus a partir de outro diretório (por exemplo, a raiz de um workspace com vários repos), crie um `.mcp.json` lá com o caminho **absoluto** do Python da venv e um nome próprio (ex: `gobus`), para não colidir com o `gobus-local` do repositório.

!!! warning "GOBUS_GRAPHQL_URL é obrigatório"
    O default (`http://localhost:8000/graphql`) aponta para uma graphql-api local. Sem sobrescrever essa variável, as tools retornam erro de conexão.

---

## 1. Conectar ao servidor em produção (Claude Desktop / claude.ai)

O endpoint primário de produção é **HTTP stateless em `/mcp`** (Streamable HTTP, spec 2025-03-26). Adicione como conector remoto (custom connector) no Claude Desktop ou no claude.ai:

```
https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp
```

O endpoint **`/sse`** (spec 2024-11-05) continua no ar só por compatibilidade com clientes antigos.

!!! warning "Claude Code CLI — prefira stdio local"
    Use a seção 0 acima para o Claude Code.

Não é necessária chave de API para o servidor de produção — a autenticação é gerida na fronteira da `graphql-api`.

## 2. Primeira chamada

Com o servidor conectado, peça algo em linguagem natural. O cliente escolhe a _tool_ apropriada automaticamente.

**Prompt:**

> Quais foram as notícias mais recentes do Ministério da Saúde sobre vacinação?

O cliente chama `gobus_search_news` e recebe Markdown formatado, mais ou menos assim:

```markdown
## Resultados para "vacinação" (Ministério da Saúde)

**3 artigos encontrados** (página 1)

### Campanha Nacional de Vacinação alcança 80% do público-alvo
- **Agência:** Ministério da Saúde
- **Data:** 2026-06-18
- **ID:** ms-2026-06-18-campanha-vacinacao-80
- Resumo: A campanha nacional ultrapassou a meta intermediária...

### Novas doses chegam aos estados do Norte
- **Agência:** Ministério da Saúde
- **Data:** 2026-06-15
- **ID:** ms-2026-06-15-doses-norte
...
```

A partir daí você pode aprofundar — por exemplo, pedir o conteúdo completo de um artigo pelo `ID` (`gobus_get_article`) ou traçar o histórico de uma entidade (`gobus_resolve_entity` + `gobus_get_entity_profile`).

## 3. Rodar localmente (desenvolvimento)

Útil para desenvolvimento ou para apontar contra uma `graphql-api` local.

```bash
# Executa em modo stdio (PORT ausente → stdio)
GOBUS_GRAPHQL_URL=http://localhost:8000/graphql .venv/bin/python3.12 -m gobus_mcp

# HTTP local (as mesmas rotas de produção: /mcp, /sse, /messages/)
PORT=8000 GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql \
  .venv/bin/python3.12 -m gobus_mcp
```

Veja todas as variáveis de configuração em **[Deploy & Config](deploy.md)**.
