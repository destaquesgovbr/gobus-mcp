# Início Rápido

Há duas formas de usar o Gobus MCP: **stdio local** (recomendado para Claude Code) ou conectando ao servidor já hospedado em **produção** via HTTP (para Claude Desktop e uso web).

## 0. Claude Code — stdio local (recomendado)

O Claude Code CLI tem bugs em ambos os transports HTTP (`/sse` e `/mcp`), que causam erro `-32602` em todas as chamadas de subagente. A solução é rodar o servidor localmente em **stdio**.

**Pré-requisitos:**
```bash
# Clone o repositório e instale as dependências
cd /caminho/para/gobus-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Configuração do `.mcp.json`** — coloque na raiz do seu **workspace** (não dentro do repo gobus-mcp):

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

Para o workspace `/Users/nitai/dev/destaquesgovbr`, o arquivo já está configurado em `/Users/nitai/dev/destaquesgovbr/.mcp.json`.

!!! warning "cwd e GOBUS_GRAPHQL_URL são obrigatórios"
    `cwd` deve ser o path absoluto do clone local do repositório gobus-mcp. `GOBUS_GRAPHQL_URL` deve apontar para a graphql-api (o default `http://localhost:8000` não funciona sem instância local).

---

## 1. Conectar ao servidor em produção (Claude Desktop / uso web)

O endpoint de produção usa transport **SSE** (`/sse`). Funciona bem para clientes que mantêm sessão persistente.

**Claude Desktop** — adicione ao arquivo de configuração do app (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gobus": {
      "url": "https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/sse"
    }
  }
}
```

!!! warning "Claude Code CLI — não use o endpoint HTTP"
    O Claude Code CLI envia GET em vez de POST para o endpoint `/mcp`, e a sessão SSE expira entre chamadas independentes. Use stdio local (seção 0 acima) para Claude Code.

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

**Pré-requisitos:** Python 3.12+ e o pacote instalado em um virtualenv.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Executa em modo stdio (PORT ausente → stdio)
GOBUS_GRAPHQL_URL=http://localhost:8000/graphql python -m gobus_mcp
```

Para usar a instância local com Claude Code, configure o `.mcp.json` do workspace em modo stdio:

```json
{
  "mcpServers": {
    "gobus": {
      "command": "python",
      "args": ["-m", "gobus_mcp"],
      "cwd": "/caminho/para/gobus-mcp",
      "env": {
        "GOBUS_GRAPHQL_URL": "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"
      }
    }
  }
}
```

!!! warning "GOBUS_GRAPHQL_URL é obrigatório no modo stdio"
    O default (`http://localhost:8000/graphql`) aponta para uma graphql-api local. Sem sobrescrever essa variável, os tools retornam erro de conexão. Use sempre o endpoint de produção acima, ou substitua por sua instância local da graphql-api.

Veja todas as variáveis de configuração em **[Deploy & Config](deploy.md)**.
