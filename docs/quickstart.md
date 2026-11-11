# Início Rápido

Há duas formas de usar o Gobus MCP: o servidor hospedado em **produção** via HTTP (`/mcp`), para Claude Code, Claude Desktop e claude.ai, ou **stdio local**, para quem desenvolve o servidor.

## 0. Claude Code

### Servidor de produção (recomendado)

```bash
claude mcp add --transport http gobus https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp -s user
```

O comando grava a entrada no `~/.claude.json`:

```json
{
  "mcpServers": {
    "gobus": {
      "type": "http",
      "url": "https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp"
    }
  }
}
```

A URL vai **sem barra final**: `/mcp/` responde 307 para `http://…/mcp`. O `/mcp` é stateless: não há sessão a perder entre chamadas de subagente. Confira com `claude mcp get gobus`, que deve mostrar "Connected".

!!! warning "Migrando do `/sse`"
    O endpoint `/sse` (spec 2024-11-05) foi removido do servidor em novembro de 2026. Se a sua config tem `"type": "sse"` apontando para `.../sse`, remova a entrada (`claude mcp remove gobus -s <escopo>`) e rode o `claude mcp add` acima.

### Stdio local (desenvolvimento)

Para rodar o código de um clone (desenvolver o servidor, validar um branch), suba o servidor localmente em **stdio**.

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

O caminho do `command` é relativo à raiz do repositório. Para usar o gobus a partir de outro diretório (por exemplo, a raiz de um workspace com vários repos), crie um `.mcp.json` lá com o caminho **absoluto** do Python da venv e um nome próprio (ex: `gobus-dev`), para não colidir com o `gobus-local` do repositório nem com o `gobus` remoto (entre escopos, o Claude Code usa local > projeto > user).

!!! warning "GOBUS_GRAPHQL_URL é obrigatório"
    O default (`http://localhost:8000/graphql`) aponta para uma graphql-api local. Sem sobrescrever essa variável, as tools retornam erro de conexão.

---

## 1. Conectar ao servidor em produção (Claude Desktop / claude.ai)

O endpoint primário de produção é **HTTP stateless em `/mcp`** (Streamable HTTP, spec 2025-03-26). Adicione como conector remoto (custom connector) no Claude Desktop ou no claude.ai:

```
https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp
```

Para o Claude Code, use o `claude mcp add --transport http` da seção 0.

Não é necessária chave de API para o servidor de produção — a autenticação é gerida na fronteira da `graphql-api`.

## 2. Primeira chamada

Com o servidor conectado, peça algo em linguagem natural. O cliente escolhe a _tool_ apropriada automaticamente.

**Prompt:**

> Quais foram as notícias mais recentes do Ministério da Saúde sobre vacinação?

O cliente chama `gobus_search_news` e recebe Markdown formatado, mais ou menos assim:

```markdown
# Resultados: vacinação

**3 artigos encontrados** (página 1)

## [Campanha Nacional de Vacinação alcança 80% do público-alvo](https://www.gov.br/saude/...)
**[saude] Ministério da Saúde** · 2026-06-18
A campanha nacional ultrapassou a meta intermediária...
ID: `ms-2026-06-18-campanha-vacinacao-80`

## [Novas doses chegam aos estados do Norte](https://www.gov.br/saude/...)
**[saude] Ministério da Saúde** · 2026-06-15
...
```

A partir daí você pode aprofundar — por exemplo, pedir o conteúdo completo de um artigo pelo `ID` (`gobus_get_article`) ou traçar o histórico de uma entidade (`gobus_resolve_entity` + `gobus_get_entity_profile`).

## 3. Rodar localmente (desenvolvimento)

Útil para desenvolvimento ou para apontar contra uma `graphql-api` local.

```bash
# Executa em modo stdio (PORT ausente → stdio)
GOBUS_GRAPHQL_URL=http://localhost:8000/graphql .venv/bin/python3.12 -m gobus_mcp

# HTTP local (a mesma rota de produção: /mcp)
PORT=8000 GOBUS_GRAPHQL_URL=https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql \
  .venv/bin/python3.12 -m gobus_mcp
```

Veja todas as variáveis de configuração em **[Deploy & Config](deploy.md)**.
