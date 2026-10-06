# Plano — Gobus MCP: Fase 1 + Policy Canonicalization
> Criado: 2026-07-01 | Baseado em: EXPERIMENTO_V3 BLUEPRINT.md
> Implementação: workflow + subagentes paralelos, TDD obrigatório

## Contexto

O EXPERIMENTO_V3 (concluído 2026-06-30) mapeou 9 padrões analíticos que os tools atuais conseguem responder via GraphQL direta, mas não via MCP (100% de falha de transport `-32602` em todos os UCs). O BLUEPRINT.md consolidou as prioridades de implementação em 3 fases.

Esta sessão implementa a **Fase 1 Quick Wins** completa + inicia a **Fase de Policy Canonicalization** (estratégica) com foco em TDD e qualidade. A implementação usa workflow com subagentes paralelos para maximizar throughput.

### Decisões de design confirmadas
- **MCP transport**: `/mcp` (spec 2025-03-26) TAMBÉM não é suportado pelo Claude Code CLI (bug: envia GET em vez de POST). A solução real é execução local via **stdio**. Fix = documentação atualizada + `.mcp.json` de exemplo para modo local.
- **MCP Apps (ui://)**: Claude Code CLI não renderiza; VS Code Insiders renderiza parcialmente (bug #671). Vamos implementar com testes por snapshot HTML + MCP Inspector local. Validação visual via migração para VS Code plugin.
- **Streamlit**: Sem mudanças de código. Converter itens do BLUEPRINT em GitHub Issues em `destaquesgovbr/streamlit-panorama-dgb`.
- **Policy canonicalization**: Escopo completo — ontologia + pipeline NER + graphql-api schema + gobus-mcp tools.

### Repos em escopo
| Repo | Mudanças |
|------|---------|
| `gobus-mcp/` | Docs, 1 tool novo, 1 MCP App, 1 prompt novo |
| `graphql-api/` | Schema: campos de Policy lifecycle |
| `data-platform/` | Migração de schema: `entity_registry` + canonicalization config |
| `data-science/` | Gazetteer + LLM prompt para POLICY canonicalization |
| GitHub Issues | `streamlit-panorama-dgb`: 4 issues novas |

### Invariantes
- **TDD**: testes escritos primeiro em todos os componentes Python
- **Commits**: português, prefixos `fix:/feature:/refactor:/chore:`, **sem Co-Authored-By** em gobus-mcp, graphql-api, data-platform, data-science
- **Terraform**: nunca local — somente via CI/PR
- **Python**: sempre venv ativado

---

## Parte 1 — Local MCP Execution + Docs

### Problema
Claude Code CLI tem dois bugs de transport:
1. `.mcp.json` com URL `/sse` (spec 2024-11-05): sessão SSE não persiste entre chamadas de subagente → `-32602`
2. `.mcp.json` com URL `/mcp` (spec 2025-03-26 Streamable HTTP): Claude Code CLI envia GET em vez de POST → falha de conexão

**Solução única viável hoje:** executar o servidor gobus-mcp **localmente** (stdio transport), que não tem estado de sessão e funciona perfeitamente com Claude Code.

### Arquivos a modificar
- `gobus-mcp/CLAUDE.md` — seção "MCP no Claude Code": reescrever para documentar o modo local como **método principal**; o endpoint remoto como opção para uso manual (Claude Desktop/web)
- `gobus-mcp/docs/quickstart.md` — guia atualizado para agentes e utilizadores humanos
- `gobus-mcp/.mcp.json` (na raiz do repo gobus-mcp, não do workspace) — exemplo de configuração local com `command: python -m gobus_mcp` e env vars
- `gobus-mcp/README.md` — nota no top sobre setup MCP local

### Conteúdo da configuração local
```json
{
  "mcpServers": {
    "gobus": {
      "command": "python",
      "args": ["-m", "gobus_mcp"],
      "cwd": "/path/to/gobus-mcp",
      "env": {
        "GOBUS_GRAPHQL_URL": "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"
      }
    }
  }
}
```

Para agentes (Claude Code), o `.mcp.json` deve estar na raiz do workspace (`/Users/nitai/dev/destaquesgovbr/.mcp.json`). Para utilizadores humanos, no diretório do projeto.

### Issues a fechar/comentar
- `destaquesgovbr/gobus-mcp#4` (Migrar SSE → streamable-http): comentar com a descoberta de que `/mcp` também não funciona no CLI por bug do cliente; fechar como "won't fix agora — solução: stdio local" e linkar a documentação atualizada.

---

## Parte 2 — Tool: gobus_get_readability_recommendations

### O que faz
Dado um `agency_key` opcional, retorna:
1. Ranking das agências por Flesch × volume (ou só a agência pedida)
2. Flesch atual vs. faixa-alvo (≥50 para serviço, ≥30 para institucional)
3. Artigo mais ilegível e mais legível da agência (exemplos concretos)
4. 3 recomendações de estilo priorizadas pelo tema dominante

### Arquivos novos
```
src/gobus_mcp/tools/get_readability_recommendations.py   ← implementação
tests/test_tools/test_get_readability_recommendations.py  ← testes TDD
```

### GraphQL subjacente
Reusa duas queries já existentes no codebase:
- `agencyAnalytics(agencies, dateFrom, dateTo, granularity: MONTH)` → Flesch + volume
- `articles(filter: {agency}, sort: DATE, limit: 5)` com `features { readabilityFlesch wordCount }` → exemplos extremos

### Assinatura do tool
```python
async def gobus_get_readability_recommendations(
    agency_key: str = "",
    days: int = 90,
    limit: int = 10,
) -> str:
```

### Testes TDD (escrever primeiro)
```python
# test_get_readability_recommendations.py
async def test_ranking_geral_sem_agency_key(fake_client):
    """Sem agency_key, retorna ranking de N agências por Flesch"""

async def test_agency_especifica_retorna_gap_e_exemplos(fake_client):
    """Com agency_key, retorna gap vs meta e exemplos de artigos"""

async def test_flesch_negativo_eh_marcado_como_abaixo_do_piso(fake_client):
    """Valores Flesch < 0 recebem label 'abaixo do piso'"""

async def test_flesch_alto_acima_de_50_label_correto(fake_client):
    """Flesch >= 50 label 'medio / facil de ler'"""

async def test_recomendacoes_por_tema_dominante(fake_client):
    """Recomendações variam por tema dominante detectado"""

async def test_agency_key_invalida_graceful(fake_client):
    """agency_key inválida retorna mensagem de erro útil"""
```

### Registrar em server.py
```python
from gobus_mcp.tools.get_readability_recommendations import get_readability_recommendations

@mcp.tool()
async def gobus_get_readability_recommendations(
    agency_key: str = "",
    days: int = 90,
    limit: int = 10,
) -> str:
    """..."""
    return await get_readability_recommendations(agency_key or None, _client, days, limit)
```

---

## Parte 3 — MCP App: ui://readability-dashboard

### O que é
Um resource MCP que retorna HTML/JS auto-contido representando um dashboard interativo de legibilidade. Renderizado em iframe pelo cliente MCP.

### Stack técnica
- Python: gera HTML + inline JavaScript + dados embutidos como JSON literal
- Chart.js 4.x: inlinado como string base64 no `<script>` (sem CDN — CSP estrita)
- CSS: inline no `<style>` do HTML
- FastMCP 3.0: registrar com `@mcp.resource("ui://readability-dashboard")`

### Arquivo novo
```
src/gobus_mcp/resources/readability_dashboard.py
tests/test_resources/test_readability_dashboard.py
```

### Testes TDD para ui:// (estratégia otimizada)

A estratégia combina 3 níveis, sem depender de renderização visual no CLI:

**Nível 1 — Unit tests (pytest, snapshot HTML)**
```python
# test_readability_dashboard.py
async def test_retorna_html_valido(fake_client):
    html = await fetch_readability_dashboard(fake_client)
    assert html.startswith("<!DOCTYPE html>") or "<html" in html
    assert "<canvas" in html  # Chart.js canvas
    assert "readability-data" in html  # JSON data island

async def test_dados_de_agencias_embutidos_no_html(fake_client):
    """JSON com dados das agências está presente no script"""
    html = await fetch_readability_dashboard(fake_client)
    assert '"secom"' in html
    assert '"avgReadabilityFlesch"' in html

async def test_snapshot_html(fake_client, snapshot):
    """Regressão de HTML — usa syrupy para snapshot"""
    html = await fetch_readability_dashboard(fake_client)
    assert html == snapshot  # falha se HTML mudar inesperadamente

async def test_css_inline_sem_cdn(fake_client):
    """Sem referências externas (bloqueadas por CSP)"""
    html = await fetch_readability_dashboard(fake_client)
    assert "https://" not in html  # nenhuma URL externa
    assert "http://" not in html
```

**Nível 2 — Integration test com MCP Inspector**
- Pré-requisito: `npx @modelcontextprotocol/inspector` instalado
- Subagente executa `python -m gobus_mcp` em stdio e aponta o Inspector para o processo
- Inspector valida que o resource `ui://readability-dashboard` é anunciado e retorna HTML válido
- Instruções documentadas em `docs/testing-mcp-apps.md`

**Nível 3 — Validação visual manual (VS Code)**
- Migrar para Claude Code VS Code plugin (compartilha settings.json com CLI)
- Configurar `.mcp.json` local com stdio
- Abrir o resource `ui://readability-dashboard` no painel de resources do plugin
- Validação visual subjetiva: agências ranqueadas, Flesch visível, exemplos acessíveis

**Dependência de dados para o dashboard:**
```python
_DASHBOARD_QUERY = """
query ReadabilityDashboard($dateFrom: String!, $dateTo: String!) {
  agencyAnalytics(agencies: $agencies, dateFrom: $dateFrom, dateTo: $dateTo, granularity: MONTH) {
    agency  periodStart  articleCount  avgReadabilityFlesch
  }
}
"""
```
Usa as N agências mais ativas (top 20) para o ranking geral; exemplos de artigos via segunda query.

### Registrar em server.py
```python
from gobus_mcp.resources.readability_dashboard import fetch_readability_dashboard

@mcp.resource("ui://readability-dashboard")
async def readability_dashboard_resource() -> str:
    """Dashboard interativo de legibilidade por agência (HTML/JS)."""
    return await fetch_readability_dashboard(_client)
```

---

## Parte 4 — GitHub Issues para Streamlit

Repo: `destaquesgovbr/streamlit-panorama-dgb`  
Comando base: `gh issue create --repo destaquesgovbr/streamlit-panorama-dgb`

| Issue | Título | Conteúdo resumido |
|-------|--------|-------------------|
| 1 | feat: Radar de Proto-Crises — anomalias e silêncios coordenados | Gauge por domínio; cross `trendingEntities x agencyAnalytics`; detectar silêncio coordenado (ex: PF 11 vs MJ 125 em crime). Depende de `gobus_detect_anomalies`. |
| 2 | feat: Mapa de Equidade — cobertura NER por região | Toggle menção full-text vs entidade LOC canônica; revela 1.11x → 4.25x disparidade. Amazônia Legal = 117 art/Q2. Depende de `gobus://equity-audit`. |
| 3 | feat: Benchmark de Legibilidade — ranking + gap vs meta | Barchart horizontal com faixa-alvo Flesch>=50. Hover: artigo mais/menos legível da agência. Nenhuma agência atinge hoje. |
| 4 | feat: Timeline de Ciclo de Vida de Política Pública | Swimlane por fase (anúncio→regulamentação→implementação→rotina). Pivô retórico detectado. Depende de `gobus_get_policy_lifecycle` + schema novo. |

---

## Parte 5 — Policy Canonicalization (Escopo Completo)

### Contexto estratégico
O UC-09 confirmou: `dgb_taxa-selic` tem 0 artigos NER apesar de ser o conceito económico mais central. O UC-02 mostrou que o Pé-de-Meia (247 artigos) tem um arco narrativo rico mas nenhum campo de "fase de ciclo de vida". A intenção é evoluir POLICYs para objetos de primeira classe com ontologias de domínio.

### 5.1 — Ontologia de Políticas Públicas (Design Doc)

**Arquivo novo:** `gobus-mcp/_plan/POLICY_ONTOLOGY.md`

A ontologia cobre:
```
Policy (POLICY entity)
  ├── domain: enum {SOCIAL, ECONOMIC, HEALTH, EDUCATION, SECURITY, ENVIRONMENT, GOVERNANCE}
  ├── lifecycle_phase: enum {ANNOUNCED, REGULATION, IMPLEMENTATION, EVALUATION, ROUTINE}
  ├── wikidata_qid: string (Q-number se existir)
  ├── instance_of: string (ex: "Q327254" = cash_transfer_program)
  ├── enabling_law: [LAW entity_id] — legislação habilitante
  ├── responsible_agencies: [agency_key]
  ├── target_population: [string] — ex: ["estudantes", "idosos"]
  └── first_mentioned_date: date — data da primeira cobertura
```

Mapeado para o campo `extra: JSONB` da tabela `entity_registry` (já existe — sem migração de schema necessária para a ontologia).

### 5.2 — Schema da graphql-api: campos de Policy

**Arquivo a modificar:** `graphql-api/src/graphql_api/schema/types/entities.py`

Novos campos no `EntitySearchResult` (ou novo tipo `PolicyDetails`):
```python
@strawberry.type
class PolicyDetails:
    domain: str | None  # SOCIAL | ECONOMIC | HEALTH | ...
    lifecycle_phase: str | None  # ANNOUNCED | REGULATION | IMPLEMENTATION | ...
    enabling_laws: list[str]  # entity_ids de LAW relacionadas
    responsible_agencies: list[str]  # agency keys
    target_population: list[str]
    first_mentioned_date: date | None
```

Resolver: lê de `entity_registry.extra` quando `type == "POLICY"`.

**Arquivo a modificar:** `graphql-api/src/graphql_api/datasources/postgres.py`
Adicionar query `get_policy_details(entity_id)` que lê `extra` da entity_registry.

**TDD:** testes em `graphql-api/tests/` para o novo resolver.

### 5.3 — data-platform: migração de canonicalization

**Contexto:** A canonicalization pipeline já usa Claude Sonnet 4.6. O que falta é um **gazetteer de POLICYs** (lista curada de políticas públicas importantes) e um **prompt de LLM** que detecte e anote campos da ontologia.

**Arquivo novo:** `data-platform/scripts/seeds/policy_gazetteer.csv`
```csv
entity_id,canonical_name,aliases,domain,lifecycle_phase,wikidata_id,instance_of
dgb_pe-de-meia,Pé-de-Meia,"Pe-de-Meia,Poupança do Jovem",SOCIAL,ROUTINE,,Q327254
dgb_novo-pac,Novo PAC,"PAC 2,Programa de Aceleração do Crescimento 2",ECONOMIC,IMPLEMENTATION,,,
dgb_minha-casa-minha-vida,Minha Casa Minha Vida,"MCMV,programa habitacional",SOCIAL,IMPLEMENTATION,Q2376464,
```
~50 políticas prioritárias curadas manualmente.

**Arquivo a modificar:** `data-science/src/news_enrichment/canonicalization.py`
- Adicionar step de enriquecimento pós-resolução: quando `entity_type == "POLICY"`, ler `extra` da entity_registry e preencher campos de ontologia se ainda null
- O LLM prompt para resolução de POLICYs deve incluir pedido de classificação de domínio e fase

**Migração de dados:**
```sql
-- data-platform/scripts/migrations/024_policy_ontology_seed.sql
-- Popula extra->>'domain' e extra->>'lifecycle_phase' para todas as políticas existentes
-- via JOIN com o novo CSV de gazetteer
UPDATE entity_registry
SET extra = extra || jsonb_build_object('domain', seed.domain, 'lifecycle_phase', seed.lifecycle_phase)
FROM policy_gazetteer_temp seed
WHERE entity_registry.entity_id = seed.entity_id
AND entity_registry.type = 'POLICY';
```

### 5.4 — gobus-mcp: tool gobus_get_policy_lifecycle

**Arquivo novo:** `src/gobus_mcp/tools/get_policy_lifecycle.py`

```python
async def get_policy_lifecycle(
    policy_name: str,
    client: GobusGraphQLClient,
    date_from: str = "2024-01-01",
) -> str:
    """
    Retorna o ciclo de vida comunicacional de uma política pública:
    - fases detectadas (Anúncio → Regulamentação → Implementação → Rotina)
    - entidades âncora por fase (ORG/PER)
    - pivô retórico (mudança de linguagem entre fases)
    - fase atual e perspectiva
    """
```

Queries internas:
1. `entitySearch(query=policy_name, entityType=POLICY)` → resolver entityId
2. `entityCoverage(entityId, granularity=MONTH)` → série temporal de menções
3. `articles(filter: {entities: [entityId]})` por janelas de fase → textos para análise retórica
4. `policyDetails(entityId)` (nova query da graphql-api) → metadados de ontologia

**TDD:**
```python
async def test_retorna_fases_com_datas(fake_client): ...
async def test_fase_atual_identificada(fake_client): ...
async def test_pivo_retorico_detectado_quando_ha_dados(fake_client): ...
async def test_policy_nao_encontrada_graceful(fake_client): ...
async def test_policy_com_dados_insuficientes_avisa(fake_client): ...
```

---

## Workflow de Implementação (Claude Code Workflow Script)

### Estrutura do workflow

```
Phase 1 — Parallel (sem dependências):
  Agent A: Docs MCP local execution (CLAUDE.md + quickstart.md + .mcp.json exemplo)
  Agent B: GitHub Issues para Streamlit (4 issues + comentar issue #4 gobus-mcp)
  Agent C: POLICY_ONTOLOGY.md design doc + policy_gazetteer.csv

Phase 2 — TDD Red (testes falhando primeiro):
  Agent D: Escrever tests/test_tools/test_get_readability_recommendations.py (FAILING)
  Agent E: Escrever tests/test_resources/test_readability_dashboard.py (FAILING)
  Agent F: Escrever tests graphql-api para PolicyDetails resolver (FAILING)

Phase 3 — TDD Green (implementação):
  Agent G: Implementar get_readability_recommendations.py + passar nos testes do D
  Agent H: Implementar readability_dashboard.py (ui://) + passar nos testes do E
  Agent I: Implementar graphql-api PolicyDetails resolver + passar nos testes do F

Phase 4 — Parallel (dependem de Phase 3):
  Agent J: Implementar get_policy_lifecycle.py (gobus-mcp) + testes TDD
  Agent K: data-platform migração 024_policy_ontology_seed.sql + atualizar canonicalization config

Phase 5 — Integration + PRs:
  Agent L: Rodar pytest completo gobus-mcp, criar PR gobus-mcp
  Agent M: Rodar testes graphql-api, criar PR graphql-api
  Agent N: Criar PR data-platform + data-science
```

### Contexto por agente (autocontido)

Cada agente recebe no prompt:
- **Repositório alvo e path absoluto**
- **Invariantes**: TDD, sem Co-Authored-By, commits em português, venv
- **Padrão de tool**: `async def f(arg, client: GobusGraphQLClient) -> str`
- **Padrão de test**: `FakeGraphQLClient + AsyncMock + pytest-asyncio auto`
- **GraphQL gotchas**: lista completa de nomes de campos/enums (do CLAUDE.md)
- **O que implementar**: spec completa do componente

---

## Fase Portal — Listagem de Políticas Públicas

> Status: Planejada | Dependências: Fase 1 (migração 026 aplicada, `policyDetails` mergeado)

### Objetivo

Criar uma página pública `/politicas` no portal Next.js que lista todas as entidades POLICY do `entity_registry`, com filtros por domínio e fase do ciclo de vida.

### Contexto de design

O portal já tem `/entidades/[slug]` para detalhe de entidades canônicas. A página `/politicas` é uma vitrine específica para o subconjunto POLICY — navegação por domínio (SOCIAL/ECONOMIC/...) e lifecycle_phase (ANNOUNCED/ROUTINE/...), não disponível na busca de entidades genérica.

O `entitySearch` existente já pode listar POLICYs (entityType=POLICY), mas não retorna `domain` nem `lifecycle_phase` — precisamos de uma nova query GraphQL que leia o campo `extra: JSONB`.

### Repos em escopo

| Repo | Mudanças |
|------|---------|
| `graphql-api/` | Nova query `policies(domain, lifecyclePhase, limit, offset)` + tipo `PolicyListItem` |
| `portal/` | Schema snapshot atualizado + rota `/politicas` (page.tsx + componentes) |

### Parte A — graphql-api: query `policies`

**Novo tipo** em `src/graphql_api/schema/types/entities.py`:

```python
@strawberry.type
class PolicyListItem:
    entity_id: str
    canonical_name: str
    domain: Optional[str]           # SOCIAL | ECONOMIC | HEALTH | ...
    lifecycle_phase: Optional[str]  # ANNOUNCED | IMPLEMENTATION | ROUTINE | ...
    wikidata_id: Optional[str]
    aliases: list[str]
    article_count: int              # total de menções no corpus
```

**Nova query** em `src/graphql_api/schema/resolvers/entities.py`:

```python
@strawberry.field(description="Lista entidades POLICY com metadados de ontologia.")
async def policies(
    self,
    info: Info,
    domain: Optional[str] = None,
    lifecycle_phase: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[PolicyListItem]:
    ds = info.context.postgres_ds
    rows = await ds.list_policies(domain, lifecycle_phase, limit, offset)
    return [PolicyListItem(...) for row in rows]
```

**Novo método datasource** em `src/graphql_api/datasources/postgres.py`:

```sql
SELECT
    er.entity_id,
    er.canonical_name,
    er.extra->>'domain' AS domain,
    er.extra->>'lifecycle_phase' AS lifecycle_phase,
    er.extra->>'wikidata_id' AS wikidata_id,
    COALESCE(er.aliases::text, '[]') AS aliases,
    COALESCE(ne.article_count, 0) AS article_count
FROM entity_registry er
LEFT JOIN (
    SELECT entity_id, COUNT(DISTINCT unique_id) AS article_count
    FROM news_entities
    GROUP BY entity_id
) ne ON ne.entity_id = er.entity_id
WHERE er.type = 'POLICY'
AND ($1::text IS NULL OR er.extra->>'domain' = $1)
AND ($2::text IS NULL OR er.extra->>'lifecycle_phase' = $2)
ORDER BY er.canonical_name ASC
LIMIT $3 OFFSET $4
```

TDD: testes em `graphql-api/tests/` para o novo resolver.

**PR graphql-api**: branch `feature/portal-policies-query`

### Parte B — portal: página /politicas

**Rota**: `src/app/(public)/politicas/page.tsx` (nova)

**Estrutura da página** (Server Component, SSR):

```tsx
// politicas/page.tsx
import { fetchPolicies } from './actions'
import PoliciesGrid from './PoliciesGrid'
import PolicyFilters from './PolicyFilters'

export default async function PoliciesPage({ searchParams }) {
  const domain = searchParams?.domain ?? null
  const lifecyclePhase = searchParams?.lifecycle ?? null
  const policies = await fetchPolicies({ domain, lifecyclePhase, limit: 50 })
  return (
    <main>
      <h1>Políticas Públicas Federais</h1>
      <PolicyFilters currentDomain={domain} currentPhase={lifecyclePhase} />
      <PoliciesGrid policies={policies} />
    </main>
  )
}
```

**Query GraphQL** (nova operação a adicionar ao schema snapshot do portal):

```graphql
query PoliciesPage($domain: String, $lifecyclePhase: String, $limit: Int!) {
  policies(domain: $domain, lifecyclePhase: $lifecyclePhase, limit: $limit) {
    entityId
    canonicalName
    domain
    lifecyclePhase
    wikidataId
    articleCount
  }
}
```

**PolicyCard** — componente de card com:
- Nome canônico (link para `/entidades/{entityId}`)
- Badge de domínio (cores por categoria: SOCIAL=azul, ECONOMIC=verde, HEALTH=vermelho, etc.)
- Badge de fase (ANNOUNCED=cinza, IMPLEMENTATION=laranja, ROUTINE=verde)
- Contagem de artigos

**PolicyFilters** — barra de filtros com dropdowns:
- Domínio: todos / SOCIAL / ECONOMIC / HEALTH / EDUCATION / SECURITY / ENVIRONMENT / GOVERNANCE
- Fase: todas / ANNOUNCED / REGULATION / IMPLEMENTATION / EVALUATION / ROUTINE
- Filtros mudam URL params (client-side navigation)

**Schema snapshot do portal** — após deploy da graphql-api com a nova query, rodar:
```bash
cd portal
pnpm graphql:codegen  # regenera types + atualiza schema.graphql snapshot
```
e commitar o snapshot atualizado.

**CI gate**: o portal tem validação de operações GraphQL × SDL. A nova query `PoliciesPage` deve ser validada pelo gate antes do merge.

**PR portal**: branch `feature/portal-politicas-page`

### Ordem de execução

1. Merge graphql-api PR `feature/portal-policies-query` → CI deploya nova query
2. Executar `pnpm graphql:codegen` no portal para capturar nova query no snapshot
3. Merge portal PR `feature/portal-politicas-page`

### Dependências de dados

A página só mostra conteúdo útil após a migração 026 ser aplicada (gazetteer com 45 políticas e seus metadados de ontologia). Com a migração aplicada, todas as 45 políticas têm `domain` e `lifecycle_phase` preenchidos e aparecem nos filtros.

Políticas criadas apenas por NER (antes do gazetteer) aparecem com `domain=null` e são listadas no bucket "Sem categorização" no filtro.

### Próximo passo natural

Após a página de listagem, a evolução óbvia é uma **página de detalhe por política** — `/politicas/[slug]` — que reutiliza `gobus_get_policy_lifecycle` para mostrar o arco narrativo, combinado com o componente `ui://policy-timeline` (Fase 3 do BLUEPRINT).

---

## Verificação End-to-End

1. **Unit tests**: `cd gobus-mcp && source .venv/bin/activate && pytest` — deve passar 100%
2. **Local MCP**: Configurar `.mcp.json` local com stdio, abrir Claude Code na raiz do workspace, verificar que `gobus_get_readability_recommendations` aparece na lista de tools e responde
3. **MCP Inspector visual**: `npx @modelcontextprotocol/inspector python -m gobus_mcp` (no diretório gobus-mcp com venv ativo e GOBUS_GRAPHQL_URL configurado) → verificar que `ui://readability-dashboard` aparece e renderiza HTML
4. **VS Code visual**: Migrar sessão para VS Code plugin, abrir resource `ui://readability-dashboard` no painel
5. **graphql-api**: Testar query `policyDetails(entityId: "dgb_pe-de-meia")` via GraphQL playground ou `pytest`
6. **Issues Streamlit**: Verificar 4 issues abertas em `github.com/destaquesgovbr/streamlit-panorama-dgb`
