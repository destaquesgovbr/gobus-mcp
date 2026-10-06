# Gobus MCP

O **Gobus MCP** é um servidor [Model Context Protocol](https://modelcontextprotocol.io) que expõe o acervo do **Destaques Gov.BR** — cerca de 300 mil artigos publicados por ~160 portais do gov.br, um grafo de entidades NER canonicalizadas e analytics de comunicação por agência — como _tools_, _resources_ e _prompts_ consumíveis diretamente por LLMs (Claude Desktop, Claude Code e qualquer cliente MCP).

Toda leitura de dados passa pela `graphql-api`: o servidor não abre conexões diretas a Postgres, Typesense ou Neo4j. Isso centraliza rate-limiting, autenticação, analytics e validação de schema em uma única fronteira.

## Como se encaixa

```mermaid
flowchart LR
    Claude["Claude<br/>(Desktop / Code)"]
    MCP["Gobus MCP<br/>(Cloud Run)"]
    API["graphql-api"]
    PG[("Postgres")]
    TS[("Typesense")]
    NEO[("Neo4j")]

    Claude <-->|MCP| MCP
    MCP <-->|HTTP GraphQL| API
    API --> PG
    API --> TS
    API --> NEO
```

O cliente conversa com o Gobus MCP via protocolo MCP (stdio localmente; em produção, HTTP stateless em `/mcp` mais `/sse` por compatibilidade). O Gobus MCP traduz cada chamada em uma query GraphQL e a `graphql-api` resolve contra os bancos de dados subjacentes.

## Capacidades

| Categoria | Quantidade | Exemplos |
|-----------|:----------:|----------|
| Tools     | 13 | `gobus_search_news`, `gobus_get_article`, `gobus_resolve_entity`, `gobus_get_entity_profile`, `gobus_get_entity_network`, `gobus_get_agency_analytics`, `gobus_get_agency_summary`, `gobus_detect_trends`, `gobus_get_readability_recommendations`, `gobus_score_article`, `gobus_get_policy_lifecycle`, `gobus_detect_anomalies`, `gobus_forecast_trends` |
| Resources | 7 | `gobus://agencies`, `gobus://themes`, `gobus://platform-stats`, `gobus://taxonomy-queries`, `gobus://readability-report`, `gobus://health/pipelines`, `ui://readability-dashboard` |
| Prompts   | 4 | `prompt_monitor_agency`, `prompt_trace_entity`, `prompt_weekly_digest`, `prompt_draft_press_release` |

As _tools_ são somente leitura e retornam Markdown formatado (não JSON), pensado para ser lido diretamente pelo LLM. Métrica sem dado aparece como "indisponível" — nunca 0 —, e o estado das fontes de dados fica em [`gobus://health/pipelines`](resources/health-pipelines.md).

## Por onde começar

- **[Início Rápido](quickstart.md)** — conecte ao servidor em produção ou rode localmente em poucos minutos.
- **[Referência de Tools](tools/index.md)** — argumentos, retornos e exemplos de cada tool.
- **[Arquitetura](arquitetura.md)** — transport, modelo GraphQL-only e padrões internos.
- **[Deploy & Config](deploy.md)** — variáveis de ambiente, Cloud Run e WIF.
