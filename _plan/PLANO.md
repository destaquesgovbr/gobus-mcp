# Gobus MCP — Plano de Implementação

## Contexto

O Destaques Gov.BR tem ~300k artigos, grafo de entidades (Neo4j + Postgres), busca híbrida (Typesense) e features por notícia (sentimento, trending, legibilidade, entidades NER canonicalizadas). A POC (`LAB/govbrnews-mcp/`) validou a arquitetura FastMCP + Typesense, mas não tinha NER, grafo nem analytics.

**Decisão de arquitetura**: O MCP Gobus consultará **apenas a GraphQL API** (sem acesso direto a Postgres/Typesense/Neo4j). Isso centraliza rate-limiting, auth, analytics e caching no GraphQL layer. Para cobrir todos os use cases, 4 novas queries precisam ser adicionadas à graphql-api **antes** de construir o MCP.

**Abordagem**: TDD estrito em ambos os repos + implementação via Workflow + subagentes.

**Referências externas**: UK Parliament MCP, FedMCP (CA), GDELT MCP, AWS MCP Design Guidelines, FastMCP 2.0+.

---

## 10 Use Cases

### UC-01 · Briefing Diário da Agência *(assessora de comunicação)*
"O que o Ministério da Saúde publicou ontem?"
**Algoritmo**: search_news (agência + 24h) → agencyAnalytics (volume 24h vs média 7d) → LLM briefing narrativo.

### UC-02 · Comparativo Inter-Agências no Mesmo Tema *(pesquisador/jornalista)*
"Como Fazenda e Planejamento comunicaram a Reforma Tributária em 2024?"
**Algoritmo**: search_news × 2 agências + agencyAnalytics (volume, sentiment, themes) → LLM compara enquadramento.

### UC-03 · Trajetória de uma Entidade *(assessora / pesquisador)*
"Mostre toda a cobertura do Programa Mais Médicos desde sua criação."
**Algoritmo**: entitySearch("Mais Médicos", POLICY) → entityCoverage (série temporal) → relatedEntities (Neo4j 1-hop) → search_news (âncoras) → LLM linha do tempo.

### UC-04 · Radar de Tendências Emergentes *(assessora estratégica)*
"Quais temas estão acelerando esta semana vs. histórico?"
**Algoritmo**: trendingThemes (window=7d, baseline=28d, threshold=1.5×) → search_news (exemplos) → LLM radar.

### UC-05 · Geração Assistida de Release *(redator da assessoria)*
"Crie um rascunho de release sobre emprego formal usando artigos do Ministério do Trabalho."
**Algoritmo**: search (semântico, agência, limit=10) → article × top-5 (conteúdo completo) → LLM extrai fatos → LLM gera release com tags `[VERIFICAR]`.

### UC-06 · Mapeamento de Rede Institucional *(jornalista investigativo)*
"Quais pessoas, projetos e leis aparecem com o Ministério das Comunicações?"
**Algoritmo**: entitySearch → entityNetwork (depth=2) → search_news (artigos âncora) → LLM narra rede.

### UC-07 · Análise Temporal de Sentimento *(pesquisador acadêmico)*
"Como evoluiu o sentimento sobre saúde pública durante a pandemia?"
**Algoritmo**: agencyAnalytics (sentiment, granularity=month, 2020-2022) → search (extremos) → LLM identifica inflexões.

### UC-08 · Oportunidades de Coordenação Cross-Agency *(equipe SECOM)*
"Quais temas foram cobertos por 3+ agências em paralelo sem coordenação no último mês?"
**Algoritmo**: trendingThemes (group_by=theme, window=30d) + search × agências → LLM mapa de oportunidades.

### UC-09 · Benchmark de Legibilidade *(gestor de conteúdo / cidadão-pesquisador)*
"Quais órgãos publicam conteúdo mais acessível?"
**Algoritmo**: agencyAnalytics (metrics=[readability], all agencies, 90d) → search (extremos Flesch) → LLM ranking.

### UC-10 · Boletim Semanal para o Cidadão *(cidadão comum)*
"O que o governo publicou de mais importante essa semana?"
**Algoritmo**: trendingThemes (window=7d) → search (view_count:desc) → LLM boletim em linguagem acessível (nível EM).

---

## Fase 0 — 4 Novas Queries na graphql-api (TDD)

**Repo**: `/Users/nitai/dev/destaquesgovbr/graphql-api/`
**Padrão existente**: Strawberry + FakeContext + MagicMock (ver `tests/resolvers/test_analytics.py`)
**Datasources no contexto**: `info.context.typesense_ds`, `info.context.postgres_ds`

### Q1 — `agencyAnalytics`

**Dados necessários**: `news` JOIN `news_features` — `DATE_TRUNC + GROUP BY agency_key, period`
**Datasource**: `postgres_ds`
**Localização**:
- `src/graphql_api/schema/types/analytics.py` → adicionar `AgencyPeriodMetrics`, `Granularity` enum, `AgencyAnalyticsInput`
- `src/graphql_api/schema/resolvers/analytics.py` → adicionar field `agency_analytics` na classe `AnalyticsQuery`
- `tests/resolvers/test_analytics.py` → novos testes com mock de `postgres_ds`

**Assinatura GraphQL**:
```graphql
agencyAnalytics(
  agencies: [String!]!
  dateFrom: String!   # ISO date "YYYY-MM-DD"
  dateTo: String!
  granularity: Granularity!  # DAY | WEEK | MONTH
  metrics: [MetricType!]  # VOLUME | SENTIMENT | READABILITY | THEMES
): [AgencyPeriodMetrics!]!

type AgencyPeriodMetrics {
  period: String!        # "2024-01" (MONTH) | "2024-01-07" (WEEK) | "2024-01-01" (DAY)
  agencyKey: String!
  agencyName: String!
  articleCount: Int!
  avgSentimentScore: Float
  pctPositive: Float
  pctNegative: Float
  avgReadabilityFlesch: Float
  avgWordCount: Float
  topThemes: [ThemeStats!]   # apenas quando metrics inclui THEMES
}
```

**SQL núcleo**:
```sql
SELECT
  DATE_TRUNC($granularity, n.published_at) AS period,
  n.agency_key, n.agency_name,
  COUNT(*) AS article_count,
  AVG((nf.features->'sentiment'->>'score')::float) AS avg_sentiment,
  AVG((nf.features->>'readability_flesch')::float) AS avg_readability,
  AVG((nf.features->>'word_count')::int) AS avg_word_count
FROM news n
JOIN news_features nf ON n.unique_id = nf.unique_id
WHERE n.agency_key = ANY($agencies)
  AND n.published_at BETWEEN $date_from AND $date_to
GROUP BY period, n.agency_key, n.agency_name
ORDER BY period, n.agency_key
```

---

### Q2 — `entityCoverage`

**Dados necessários**: `news_entities JOIN news JOIN news_features` — série temporal de menções por agência
**Datasource**: `postgres_ds`
**Localização**:
- `src/graphql_api/schema/types/` → novo arquivo `entities.py` com `EntityCoveragePoint`
- `src/graphql_api/schema/resolvers/` → novo arquivo `entities.py` com `EntityQuery`
- Registrar `EntityQuery` em `schema/__init__.py`
- `tests/resolvers/test_entities.py`

**Assinatura GraphQL**:
```graphql
entityCoverage(
  entityId: String!
  dateFrom: String
  dateTo: String
  granularity: Granularity   # default: MONTH
): [EntityCoveragePoint!]!

type EntityCoveragePoint {
  period: String!
  agencyKey: String!
  agencyName: String!
  articleCount: Int!
  avgSentimentScore: Float
  totalMentions: Int!
}
```

**SQL núcleo**:
```sql
SELECT
  DATE_TRUNC($granularity, ne.published_at) AS period,
  n.agency_key, n.agency_name,
  COUNT(DISTINCT ne.unique_id) AS article_count,
  SUM(ne.count) AS total_mentions,
  AVG((nf.features->'sentiment'->>'score')::float) AS avg_sentiment
FROM news_entities ne
JOIN news n ON ne.unique_id = n.unique_id
LEFT JOIN news_features nf ON ne.unique_id = nf.unique_id
WHERE ne.entity_id = $entity_id
  AND ($date_from IS NULL OR ne.published_at >= $date_from)
  AND ($date_to IS NULL OR ne.published_at <= $date_to)
GROUP BY period, n.agency_key, n.agency_name
ORDER BY period
```

---

### Q3 — `entitySearch`

**Dados necessários**: `entity_alias` (exact) + `entity_registry` (trgm fuzzy) + `news_entities` (article count)
**Datasource**: `postgres_ds`
**Localização**: `schema/types/entities.py` + `schema/resolvers/entities.py` + `tests/resolvers/test_entities.py`

**Assinatura GraphQL**:
```graphql
entitySearch(
  query: String!
  entityType: EntityType  # ORG|PER|LOC|EVENT|POLICY|LAW
  agencyKey: String
  limit: Int   # default 5
): [EntitySearchResult!]!

type EntitySearchResult {
  entityId: String!
  canonicalName: String!
  type: EntityType!
  description: String
  wikidataUrl: String
  agencyKey: String
  aliases: [String!]!
  articleCount: Int!
  confidence: Float!
  matchType: String!   # "alias_exact" | "trgm_fuzzy"
}
```

**SQL núcleo** (UNION alias exact + trgm fuzzy):
```sql
SELECT ea.entity_id, er.canonical_name, er.type, er.description,
       er.wikidata_url, er.agency_key, er.aliases,
       1.0 AS confidence, 'alias_exact' AS match_type,
       COALESCE(counts.article_count, 0) AS article_count
FROM entity_alias ea
JOIN entity_registry er ON ea.entity_id = er.entity_id
LEFT JOIN (SELECT entity_id, COUNT(*) AS article_count FROM news_entities GROUP BY entity_id) counts
  ON er.entity_id = counts.entity_id
WHERE ea.alias_norm = unaccent(lower($query))
  AND ($entity_type IS NULL OR ea.type = $entity_type)
UNION ALL
SELECT er.entity_id, er.canonical_name, er.type, er.description,
       er.wikidata_url, er.agency_key, er.aliases,
       similarity(er.canonical_name, $query) AS confidence, 'trgm_fuzzy',
       COALESCE(counts.article_count, 0)
FROM entity_registry er
LEFT JOIN (SELECT entity_id, COUNT(*) AS article_count FROM news_entities GROUP BY entity_id) counts
  ON er.entity_id = counts.entity_id
WHERE er.canonical_name % $query
  AND ($entity_type IS NULL OR er.type = $entity_type)
ORDER BY confidence DESC LIMIT $limit
```

---

### Q4 — `trendingThemes`

**Dados necessários**: Typesense — dois facets com janelas temporais distintas
**Datasource**: `typesense_ds`
**Localização**: `schema/types/analytics.py` + `schema/resolvers/analytics.py` + `tests/resolvers/test_analytics.py`

**Assinatura GraphQL**:
```graphql
trendingThemes(
  windowDays: Int!        # janela recente (ex: 7)
  baselineDays: Int!      # janela histórica para baseline (ex: 28)
  minArticles: Int        # mínimo na janela recente (default: 3)
  growthThreshold: Float  # score mínimo (default: 1.5)
  agencyKey: String       # filtrar por agência
  limit: Int              # default: 10
): [TrendingThemeResult!]!

type TrendingThemeResult {
  themeLabel: String!
  themeCode: String
  windowCount: Int!
  baselineDailyAvg: Float!
  growthScore: Float!      # windowCount/windowDays ÷ baselineDailyAvg
  topArticles: [ArticleSummary!]!
}

type ArticleSummary {
  uniqueId: String!
  title: String!
  agencyName: String
  publishedAt: String
  trendingScore: Float
}
```

**Lógica**: 2 queries Typesense (facet_by=theme_1_level_1_label para cada janela) + cálculo de growth_score em Python.

---

## MCP Architecture (gobus-mcp)

### Decisão: GraphQL-only

O MCP consulta tudo via HTTP GraphQL (`httpx` async). Zero conexões diretas a Postgres/Typesense/Neo4j. Benefícios: rate-limiting centralizado, auth, analytics, schema validation.

**GraphQL endpoint**: variável `GOBUS_GRAPHQL_URL` (prod: Cloud Run graphql-api)

### 7 Tools

| Tool | Queries GraphQL utilizadas | Use cases |
|------|---------------------------|-----------|
| `search_news` | `search`, `articles` | UC-01,02,04,05,08,10 |
| `get_agency_analytics` | `agencyAnalytics` (nova Q1) | UC-01,02,07,09 |
| `get_entity_profile` | `entitySearch` (Q3), `entityCoverage` (Q2), `relatedEntities`, `articles` | UC-03,06 |
| `detect_trends` | `trendingThemes` (nova Q4) | UC-04,08,10 |
| `get_entity_network` | `entityNetwork` | UC-06,03 |
| `get_article` | `article` | UC-05,03,09 |
| `resolve_entity` | `entitySearch` (nova Q3) | precondição UC-03,06 |

### 3 Resources

| Resource | GraphQL query | TTL |
|----------|--------------|-----|
| `resource://agencies` | `agencies()` | 24h |
| `resource://themes` | `themes()` | 24h |
| `resource://platform_stats` | `analyticsKpis(range: {days: 30})` | 1h |

### 4 Prompts

| Prompt | Use case |
|--------|---------|
| `monitor_agency` | UC-01 — briefing diário |
| `trace_entity` | UC-03 — trajetória de entidade |
| `weekly_digest` | UC-10 — boletim cidadão |
| `draft_press_release` | UC-05 — geração de release |

---

## Implementação

### Repo e Stack

| Item | Decisão |
|------|---------|
| **Repo graphql-api** | `/Users/nitai/dev/destaquesgovbr/graphql-api/` — adicionar Q1-Q4 |
| **Repo gobus-mcp** | `/Users/nitai/dev/destaquesgovbr/gobus-mcp/` — novo repo |
| **Framework MCP** | FastMCP 2.0+ (mesma escolha da POC) |
| **GraphQL client no MCP** | `httpx` async (leve, sem overhead de client pesado) |
| **Python** | 3.12+, venv, `pyproject.toml` |
| **TDD** | pytest-asyncio; mocks via `unittest.mock.MagicMock` |

### Estrutura gobus-mcp

```
gobus-mcp/
├── _plan/
│   └── PLANO.md           # este arquivo
├── src/gobus_mcp/
│   ├── server.py           # FastMCP entrypoint
│   ├── config.py           # pydantic-settings (GOBUS_GRAPHQL_URL, etc.)
│   ├── client.py           # GobusGraphQLClient (httpx async, retries)
│   ├── tools/
│   │   ├── search_news.py
│   │   ├── get_agency_analytics.py
│   │   ├── get_entity_profile.py
│   │   ├── detect_trends.py
│   │   ├── get_entity_network.py
│   │   ├── get_article.py
│   │   └── resolve_entity.py
│   ├── resources/
│   │   ├── agencies.py
│   │   ├── themes.py
│   │   └── platform_stats.py
│   └── prompts/
│       ├── monitor_agency.py
│       ├── trace_entity.py
│       ├── weekly_digest.py
│       └── draft_press_release.py
├── tests/
│   ├── conftest.py         # FakeGraphQLClient mock
│   ├── test_tools/
│   └── test_resources/
├── pyproject.toml
└── .env.example
```

### Fases e PRs

| Fase | Repo | Entrega | TDD |
|------|------|---------|-----|
| **0a** — Q1 agencyAnalytics | graphql-api | Tipos + resolver Postgres + testes | Red→Green |
| **0b** — Q2 entityCoverage | graphql-api | Tipo + resolver Postgres + testes | Red→Green |
| **0c** — Q3 entitySearch | graphql-api | Tipo + resolver Postgres trgm + testes | Red→Green |
| **0d** — Q4 trendingThemes | graphql-api | Tipo + resolver Typesense 2-janelas + testes | Red→Green |
| **1** — Scaffold gobus-mcp | gobus-mcp | pyproject, config, GobusGraphQLClient, conftest | Conexão health |
| **2** — Resources + resolve_entity | gobus-mcp | 3 resources + resolve_entity (usa Q3) | Unit mocks |
| **3** — search_news + get_article | gobus-mcp | 2 tools + prompts monitor_agency + draft_press_release | Unit mocks |
| **4** — Entity tools | gobus-mcp | get_entity_profile + get_entity_network + prompt trace_entity | Unit mocks |
| **5** — Analytics + Trends | gobus-mcp | get_agency_analytics + detect_trends + prompt weekly_digest | Unit mocks |
| **6** — Deploy | infra | Cloud Run + `.mcp.json` + Secret Manager vars | E2E smoke |

### GobusGraphQLClient (client.py)

```python
class GobusGraphQLClient:
    """Thin async httpx wrapper para a GraphQL API."""
    def __init__(self, url: str, api_key: str | None = None):
        self._url = url
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def execute(self, query: str, variables: dict = {}) -> dict:
        """Executa query e retorna data dict. Lança GobusGraphQLError em errors."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._url,
                json={"query": query, "variables": variables},
                headers=self._headers,
            )
            resp.raise_for_status()
            body = resp.json()
            if errors := body.get("errors"):
                raise GobusGraphQLError(errors)
            return body["data"]
```

### Referências de Reaproveitamento

- `LAB/govbrnews-mcp/src/govbrnews_mcp/utils/formatters.py` → formatters Markdown
- `LAB/govbrnews-mcp/src/govbrnews_mcp/typesense_client.py` → padrão de wrapping
- `graphql-api/tests/resolvers/test_analytics.py` → padrão TDD para Q1-Q4

---

## Verificação

**graphql-api (Fase 0)**:
```bash
cd /Users/nitai/dev/destaquesgovbr/graphql-api
.venv/bin/pytest tests/resolvers/test_analytics.py tests/resolvers/test_entities.py -v
```
Indicadores: `agencyAnalytics` retorna dados agrupados por período; `entitySearch("MEC")` → entity_id=`Q4294522` primeiro; `trendingThemes` retorna growth_score calculado.

**gobus-mcp (Fases 1-5)**:
```bash
cd /Users/nitai/dev/destaquesgovbr/gobus-mcp
.venv/bin/pytest tests/ -v
```
Indicadores: 100% mock-based (zero calls reais); cada tool retorna Markdown com estrutura esperada.

**E2E (Fase 6)**:
- Conectar Claude Desktop/Code ao servidor local
- Executar prompts dos 10 use cases contra produção
- Latência < 3s por tool; nenhuma exceção não tratada
- `resolve_entity("MEC")` → `Q4294522` como primeiro resultado
- `detect_trends(window=7d)` → ≥3 temas com growth_score > 1.0
