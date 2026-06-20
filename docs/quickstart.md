# Início Rápido

Há duas formas de usar o Gobus MCP: conectando ao servidor já hospedado em **produção** (Cloud Run, via HTTP) ou rodando-o **localmente** (stdio). Para a maioria dos casos, produção é o caminho mais rápido.

## 1. Conectar ao servidor em produção

Adicione o servidor ao `.mcp.json` do seu cliente MCP. O endpoint de produção usa transport HTTP (streamable-http):

```json
{
  "mcpServers": {
    "gobus": {
      "transport": "http",
      "url": "https://destaquesgovbr-gobus-mcp-klvx64dufq-rj.a.run.app/mcp/"
    }
  }
}
```

!!! note "Localização do `.mcp.json`"
    No Claude Code, coloque o arquivo na raiz do projeto. No Claude Desktop, use o arquivo de configuração do app (`claude_desktop_config.json`). Reinicie o cliente após editar.

Não é necessária chave de API para o servidor de produção em uso público — a autenticação é gerida na fronteira da `graphql-api`.

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

## 3. Rodar localmente

Útil para desenvolvimento ou para apontar contra uma `graphql-api` local.

**Pré-requisitos:** Python 3.12+ e o pacote instalado em um virtualenv.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Executa em modo stdio (PORT ausente → stdio)
GOBUS_GRAPHQL_URL=http://localhost:8000/graphql python -m gobus_mcp
```

Para usar a instância local com Claude Desktop/Code, configure o `.mcp.json` em modo stdio — o cliente sobe o processo:

```json
{
  "mcpServers": {
    "gobus": {
      "command": "python",
      "args": ["-m", "gobus_mcp"],
      "env": {
        "GOBUS_GRAPHQL_URL": "http://localhost:8000/graphql"
      }
    }
  }
}
```

!!! tip "Apontar para a graphql-api de produção"
    Para testar localmente contra dados reais, troque `GOBUS_GRAPHQL_URL` por `https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql`.

Veja todas as variáveis de configuração em **[Deploy & Config](deploy.md)**.
