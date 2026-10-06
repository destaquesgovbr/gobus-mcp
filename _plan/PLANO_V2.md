# PLANO_V2 — Implementar Melhorias do Experimento 2026-06-24

> **Auto-contido.** Um agente em sessão limpa lendo apenas este arquivo consegue executar tudo.
> Fonte dos requisitos: `_experiments/uc-2026-06-24/INDEX.md` (13 itens, P1+P2+P3).

---

## Escopo

### gobus-mcp (este repo) — 1 PR com 13+ mudanças em 11 grupos

| Grupo | Arquivo(s) | P | O que muda |
|-------|-----------|---|-----------|
| A | `tools/search_news.py` + `server.py` | P1+P2 | date_from/date_to, campo agency, limit slicing, hint agency_key inválida |
| B | `tools/get_article.py` | P1 | adicionar campo agency na query e exibição |
| C | `tools/get_agency_analytics.py` | P2 | legibilidade numérica + pctNegative + avgWordCount |
| D | `tools/detect_trends.py` | P2 | top agências por tema |
| E | `tools/get_entity_network.py` + `server.py` | P2 | node_types filter, warning depth=2, cap 50/50, kind nas arestas |
| F | `tools/get_agency_summary.py` *(novo)* + `server.py` | P3 | tool que combina analytics + tendências em 1 chamada |
| G | `resources/taxonomy_queries.py` *(novo)* + `server.py` | P3 | resource gobus://taxonomy-queries |
| H | `server.py` (docstrings dos @mcp.tool) | P2 | audit + reescrita das 8 descriptions contra 6 critérios do paper 2602.14878 (issue #2) |
| I | `.claude/skills/gobus.md` *(novo)* | P2 | skill host-side: mapa UC→tool, regras de orquestração, glossário (issue #2) |
| J | `tools/get_entity_network.py` + `tools/get_entity_profile.py` + `server.py` | P2 | max_nodes em get_entity_network; summary_only em get_entity_profile (issue #2) |
| K | `prompts/monitor_agency.py` + `trace_entity.py` + `weekly_digest.py` | P2 | hints de paralelismo explícito nos 3 prompts MCP (issue #2) |

### Fora do gobus-mcp — tratados separadamente

| Item | Repo | P | Resumo |
|------|------|---|--------|
| Gaps na analytics diária | graphql-api | P3.11 | LEFT JOIN com generate_series (ver seção 8) |
| Artigos MOCK em produção | SQL ad-hoc | P2.9 | DELETE WHERE summary LIKE '[MOCK]%' (ver seção 8) |
| Campo `author` | fora de escopo | — | não existe em nenhuma camada do stack |

---

## 1. Setup de Sessão Limpa

```bash
cd /Users/nitai/dev/destaquesgovbr/gobus-mcp

# Criar/ativar venv (NUNCA pip install no sistema)
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Confirmar suite atual (deve ter 1 teste quebrado: test_limita_limit_a_50)
pytest tests/ -v 2>&1 | tail -20
```

**Resultado esperado antes de qualquer mudança:**
- `test_limita_limit_a_50` FAIL (limite nunca passado como variável GraphQL)
- Todos os outros testes PASS

---

## 2. Workflow TDD por Grupo

Para cada grupo de mudança:

```
1. ESCREVER os testes novos/corrigidos (conforme seções 3–7)
2. CONFIRMAR falha: pytest tests/test_tools/test_<arquivo>.py -v
3. IMPLEMENTAR as mudanças no código fonte
4. CONFIRMAR sucesso: pytest tests/test_tools/test_<arquivo>.py -v
5. SPOT-CHECK contra produção (ver seção 7)
```

Nunca pular os passos 2 e 4. TDD não é opcional.

---

## 3. Grupo A — search_news.py (4 mudanças)

### 3.1 Contexto: código atual

**`src/gobus_mcp/tools/search_news.py` (linhas 1–69, estado atual):**
```python
_SEARCH_QUERY = """
query SearchNews($query: String!, $filter: ArticleFilter, $page: Int) {
  search(query: $query, filter: $filter, page: $page) {
    articles {
      uniqueId title agencyName publishedAt summary url
      features { trendingScore viewCount }
    }
    found page
  }
}
"""

async def search_news(
    query: str,
    client: GobusGraphQLClient,
    agency_key: str | None = None,
    page: int = 1,
    limit: int = 10,          # ← recebido mas NUNCA usado
) -> str:
    variables: dict = {"query": query, "page": page}
    if agency_key:
        variables["filter"] = {"agencies": [agency_key]}
    data = await client.execute(_SEARCH_QUERY, variables)
    # ...iterates all articles sem fatiar
    for art in articles:
        agency = art.get("agencyName", "")   # ← só agencyName, sem agency code
```

**Teste quebrado em `tests/test_tools/test_search_news.py:38`:**
```python
async def test_limita_limit_a_50(self):
    await search_news("test", client, limit=100)
    call_variables = client.execute.call_args[0][1]
    assert call_variables["limit"] == 50   # FAIL: limit nunca está em variables
```

### 3.2 Testes novos — escrever ANTES de implementar

Substituir `tests/test_tools/test_search_news.py` inteiro por:

```python
import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.search_news import search_news


def _make_article(i: int, agency_code: str = "mec", agency_name: str = "MEC") -> dict:
    return {
        "uniqueId": f"id{i}",
        "title": f"Artigo {i}",
        "agencyName": agency_name,
        "agency": agency_code,
        "publishedAt": "2026-01-01T00:00:00Z",
        "summary": "Resumo",
        "url": f"https://gov.br/{agency_code}/artigo-{i}",
        "features": {"trendingScore": 0.0, "viewCount": 0},
    }


class TestSearchNews:
    @pytest.mark.asyncio
    async def test_retorna_artigos_formatados(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(1, "mec", "Ministério da Educação")],
            "found": 1, "page": 1,
        }})
        result = await search_news("educação", client)
        assert "Artigo 1" in result
        assert "Ministério da Educação" in result
        assert "id1" in result

    @pytest.mark.asyncio
    async def test_sem_resultados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("xyz_inexistente", client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_campo_agency_code_exibido(self):
        """agency code (ex: 'mec') deve aparecer no Markdown."""
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(1, "saude", "Ministério da Saúde")],
            "found": 1, "page": 1,
        }})
        result = await search_news("saúde", client)
        assert "[saude]" in result

    @pytest.mark.asyncio
    async def test_date_from_passado_no_filter(self):
        """date_from deve ir para filter.startDate."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, date_from="2026-06-01")
        variables = client.execute.call_args[0][1]
        assert variables["filter"]["startDate"] == "2026-06-01"

    @pytest.mark.asyncio
    async def test_date_to_passado_no_filter(self):
        """date_to deve ir para filter.endDate."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, date_to="2026-06-24")
        variables = client.execute.call_args[0][1]
        assert variables["filter"]["endDate"] == "2026-06-24"

    @pytest.mark.asyncio
    async def test_date_filter_combinado_com_agency(self):
        """date_from + agency_key devem ir no mesmo filter."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, agency_key="saude", date_from="2026-06-01", date_to="2026-06-24")
        variables = client.execute.call_args[0][1]
        assert "saude" in variables["filter"]["agencies"]
        assert variables["filter"]["startDate"] == "2026-06-01"
        assert variables["filter"]["endDate"] == "2026-06-24"

    @pytest.mark.asyncio
    async def test_limit_fatia_resultados_cliente(self):
        """limit deve fatiar a lista após receber a resposta do servidor."""
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(i) for i in range(20)],
            "found": 20, "page": 1,
        }})
        result = await search_news("test", client, limit=5)
        # Apenas 5 primeiros artigos no output
        assert "Artigo 0" in result
        assert "Artigo 4" in result
        assert "Artigo 5" not in result

    @pytest.mark.asyncio
    async def test_limit_cap_em_50(self):
        """limit > 50 deve ser silenciosamente capado em 50."""
        client = FakeGraphQLClient()
        client.set_response({"search": {
            "articles": [_make_article(i) for i in range(60)],
            "found": 60, "page": 1,
        }})
        result = await search_news("test", client, limit=100)
        # Máximo 50 artigos no output, não 60
        assert "Artigo 49" in result
        assert "Artigo 50" not in result

    @pytest.mark.asyncio
    async def test_hint_quando_agency_key_invalida_sem_resultados(self):
        """0 resultados com agency_key → hint para gobus://agencies."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("saúde", client, agency_key="invalida_xyz")
        assert "gobus://agencies" in result
```

**Confirmar falha (antes de implementar):**
```bash
pytest tests/test_tools/test_search_news.py -v
# Esperado: test_campo_agency_code_exibido FAIL
#           test_date_from_passado_no_filter FAIL
#           test_date_to_passado_no_filter FAIL
#           test_date_filter_combinado_com_agency FAIL
#           test_limit_fatia_resultados_cliente FAIL
#           test_limit_cap_em_50 FAIL (era test_limita_limit_a_50, agora com lógica correta)
#           test_hint_quando_agency_key_invalida_sem_resultados FAIL
```

### 3.3 Implementação

**`src/gobus_mcp/tools/search_news.py` — substituir inteiro:**

```python
from gobus_mcp.client import GobusGraphQLClient

_SEARCH_QUERY = """
query SearchNews($query: String!, $filter: ArticleFilter, $page: Int) {
  search(query: $query, filter: $filter, page: $page) {
    articles {
      uniqueId title agencyName agency publishedAt summary url
      features { trendingScore viewCount }
    }
    found page
  }
}
"""


async def search_news(
    query: str,
    client: GobusGraphQLClient,
    agency_key: str | None = None,
    page: int = 1,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Busca notícias no portal Gov.BR por texto e/ou agência.

    Args:
        query: Texto livre para busca semântica/full-text
        agency_key: Chave da agência (ex: "mec", "saude") — ver gobus://agencies
        page: Página de resultados (default 1)
        limit: Máximo de resultados (default 10, máx 50)
        date_from: Data de início ISO (ex: "2026-01-01")
        date_to: Data de fim ISO (ex: "2026-06-30")

    Returns:
        Markdown com artigos encontrados e metadados de paginação.
    """
    effective_limit = min(limit, 50)
    variables: dict = {"query": query, "page": page}

    filter_dict: dict = {}
    if agency_key:
        filter_dict["agencies"] = [agency_key]
    if date_from:
        filter_dict["startDate"] = date_from
    if date_to:
        filter_dict["endDate"] = date_to
    if filter_dict:
        variables["filter"] = filter_dict

    data = await client.execute(_SEARCH_QUERY, variables)
    result = data.get("search") or {}
    articles = (result.get("articles") or [])[:effective_limit]
    found = result.get("found", 0)

    if not articles:
        msg = f"Nenhum resultado encontrado para: **{query}**"
        if agency_key:
            msg += f"\n\n> Chave `{agency_key}` não encontrou artigos. Consulte `gobus://agencies` para códigos válidos."
        return msg

    lines = [f"# Resultados: {query}\n\n**{found:,} artigos encontrados** (página {page})\n"]
    for art in articles:
        pub_at = art.get("publishedAt", "")[:10] if art.get("publishedAt") else ""
        agency_code = art.get("agency") or ""
        agency_name = art.get("agencyName", "")
        agency_str = f"[{agency_code}] {agency_name}" if agency_code else agency_name
        features = art.get("features") or {}
        trending = features.get("trendingScore")
        trending_str = f" 🔥 trending={trending:.1f}" if trending and trending > 1.0 else ""
        lines.append(
            f"## {art['title']}\n"
            f"**{agency_str}** · {pub_at}{trending_str}\n"
            f"{art.get('summary') or ''}\n"
            f"🔗 {art.get('url', '')}  ID: `{art.get('uniqueId', '')}`\n"
        )

    return "\n".join(lines)
```

**`src/gobus_mcp/server.py` — atualizar `gobus_search_news` (linhas 41–48):**

```python
@mcp.tool()
async def gobus_search_news(
    query: str,
    agency_key: str = "",
    page: int = 1,
    limit: int = 10,
    date_from: str = "",
    date_to: str = "",
) -> str:
    """Busca notícias no portal Gov.BR por texto livre e/ou agência.
    
    Use date_from/date_to para filtrar por data (ISO: "2026-01-01").
    Para chaves de agência válidas, consulte o resource gobus://agencies.
    """
    return await search_news(
        query, _client,
        agency_key or None, page, limit,
        date_from or None, date_to or None,
    )
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_search_news.py -v
# Esperado: todos os 9 testes PASS
```

---

## 4. Grupo B — get_article.py (1 mudança)

### 4.1 Contexto: código atual

`get_article.py` query não inclui `agency` (só `agencyName`). Linha 50:
```python
f"**{art.get('agencyName', '')}** · {pub_at}",
```

### 4.2 Testes novos — escrever ANTES

Adicionar ao final de `tests/test_tools/test_get_article.py`:

```python
@pytest.mark.asyncio
async def test_exibe_agency_code():
    """O código de agência (ex: 'saude') deve aparecer no artigo."""
    client = FakeGraphQLClient()
    client.set_response({"article": {
        "uniqueId": "x1", "title": "Artigo Teste",
        "content": "Conteúdo do artigo.",
        "summary": "Resumo.", "agencyName": "Ministério da Saúde",
        "agency": "saude", "publishedAt": "2026-01-01T00:00:00Z",
        "url": "https://gov.br/saude/artigo",
        "tags": [], "features": {},
    }})
    result = await get_article("x1", client)
    assert "[saude]" in result
```

**Confirmar falha:**
```bash
pytest tests/test_tools/test_get_article.py::test_exibe_agency_code -v
# Esperado: FAIL
```

### 4.3 Implementação

**`src/gobus_mcp/tools/get_article.py`:**

1. Adicionar `agency` na query após `agencyName` (linha 11):
```
agencyName
agency
```

2. Mudar linha 50 de:
```python
f"**{art.get('agencyName', '')}** · {pub_at}",
```
para:
```python
agency_code = art.get("agency") or ""
agency_name = art.get("agencyName", "")
agency_str = f"[{agency_code}] {agency_name}" if agency_code else agency_name
f"**{agency_str}** · {pub_at}",
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_get_article.py -v
```

---

## 5. Grupo C — get_agency_analytics.py (3 sub-mudanças)

### 5.1 Contexto: código atual

Linha 79–80 (`legibilidade`):
```python
if flesch is not None:
    nivel = "fácil" if flesch > 70 else ("médio" if flesch > 50 else "difícil")
    metrics.append(f"legibilidade {nivel}")   # ← sem número
```

`pctNegative` e `avgWordCount` são fetched na query mas nunca exibidos.

### 5.2 Testes novos — escrever ANTES

Adicionar na classe `TestGetAgencyAnalytics` em `tests/test_tools/test_analytics_tools.py`:

```python
@pytest.mark.asyncio
async def test_legibilidade_exibe_score_numerico(self):
    """Flesch score numérico deve aparecer além do label."""
    client = FakeGraphQLClient()
    client.set_response({"agencyAnalytics": [{
        "period": "2026-06", "agencyKey": "mec", "agencyName": "MEC",
        "articleCount": 10, "avgSentimentScore": 0.1,
        "pctPositive": 0.3, "pctNegative": 0.1,
        "avgReadabilityFlesch": 72.5, "avgWordCount": 380.0,
    }]})
    result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
    assert "72.5" in result
    assert "fácil" in result.lower()

@pytest.mark.asyncio
async def test_exibe_pct_negativo(self):
    """pctNegative deve aparecer no output."""
    client = FakeGraphQLClient()
    client.set_response({"agencyAnalytics": [{
        "period": "2026-06", "agencyKey": "mec", "agencyName": "MEC",
        "articleCount": 10, "avgSentimentScore": 0.1,
        "pctPositive": 0.3, "pctNegative": 0.12,
        "avgReadabilityFlesch": 65.0, "avgWordCount": 300.0,
    }]})
    result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
    assert "12%" in result or "neg" in result.lower()

@pytest.mark.asyncio
async def test_exibe_avg_word_count(self):
    """avgWordCount deve aparecer no output."""
    client = FakeGraphQLClient()
    client.set_response({"agencyAnalytics": [{
        "period": "2026-06", "agencyKey": "mec", "agencyName": "MEC",
        "articleCount": 10, "avgSentimentScore": 0.1,
        "pctPositive": 0.3, "pctNegative": 0.05,
        "avgReadabilityFlesch": 65.0, "avgWordCount": 420.0,
    }]})
    result = await get_agency_analytics(["mec"], "2026-06-01", "2026-06-30", client)
    assert "420" in result
```

**Confirmar falha:**
```bash
pytest tests/test_tools/test_analytics_tools.py::TestGetAgencyAnalytics::test_legibilidade_exibe_score_numerico -v
# Esperado: FAIL (mostra "médio" não "65.0")
```

### 5.3 Implementação

**`src/gobus_mcp/tools/get_agency_analytics.py` — mudar linhas 67–82:**

```python
agency = row.get("agencyName") or row.get("agencyKey", "")
count = row.get("articleCount", 0)
sent = row.get("avgSentimentScore")
pct_pos = row.get("pctPositive")
pct_neg = row.get("pctNegative")
flesch = row.get("avgReadabilityFlesch")
avg_wc = row.get("avgWordCount")

metrics = [f"**{count}** artigos"]
if pct_pos is not None:
    neg_part = f" / {pct_neg*100:.0f}% neg" if pct_neg is not None else ""
    metrics.append(f"😊 {pct_pos*100:.0f}% pos{neg_part}")
if sent is not None:
    metrics.append(f"sentimento {sent:.2f}")
if flesch is not None:
    nivel = "fácil" if flesch > 70 else ("médio" if flesch > 50 else "difícil")
    metrics.append(f"legibilidade {flesch:.1f} ({nivel})")
if avg_wc is not None:
    metrics.append(f"📝 {avg_wc:.0f} palavras/artigo")
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_analytics_tools.py -v
```

---

## 6. Grupo D — detect_trends.py (1 mudança)

### 6.1 Contexto: código atual

`topArticles` é fetched com `agencyName` mas nunca usado. Linha 83–87:
```python
lines.append(
    f"{i}. {emoji} **{theme['themeLabel']}** · "
    f"Growth: **{growth:.1f}×** · "
    f"{window} artigos (janela) vs {baseline_avg:.1f}/dia (baseline)"
)
```

### 6.2 Testes novos — escrever ANTES

Adicionar na classe `TestDetectTrends` em `tests/test_tools/test_analytics_tools.py`:

```python
@pytest.mark.asyncio
async def test_exibe_agencias_por_tema(self):
    """Contagem de agências dos topArticles deve aparecer por tema."""
    client = FakeGraphQLClient()
    client.set_response({"trendingThemes": [{
        "themeLabel": "Saúde Pública",
        "themeCode": "SAU",
        "windowCount": 10,
        "baselineDailyAvg": 1.0,
        "growthScore": 2.5,
        "topArticles": [
            {"uniqueId": "a1", "title": "T1", "agencyName": "Ministério da Saúde",
             "publishedAt": "2026-06-01", "trendingScore": 1.5},
            {"uniqueId": "a2", "title": "T2", "agencyName": "Ministério da Saúde",
             "publishedAt": "2026-06-02", "trendingScore": 1.2},
            {"uniqueId": "a3", "title": "T3", "agencyName": "SECOM",
             "publishedAt": "2026-06-03", "trendingScore": 1.0},
        ],
    }]})
    result = await detect_trends(client)
    assert "Ministério da Saúde" in result
    assert "SECOM" in result
```

**Confirmar falha:**
```bash
pytest tests/test_tools/test_analytics_tools.py::TestDetectTrends::test_exibe_agencias_por_tema -v
```

### 6.3 Implementação

**`src/gobus_mcp/tools/detect_trends.py`:**

1. Adicionar import no topo:
```python
from collections import Counter
```

2. No loop de temas, após o `lines.append(...)` existente, adicionar:
```python
top_arts = theme.get("topArticles") or []
if top_arts:
    agency_counts = Counter(
        a.get("agencyName") for a in top_arts if a.get("agencyName")
    )
    agency_str = " · ".join(
        f"{name} ({cnt})" for name, cnt in agency_counts.most_common(3)
    )
    lines.append(f"   Agências: {agency_str}")
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_analytics_tools.py -v
```

---

## 7. Grupo E — get_entity_network.py (4 sub-mudanças)

### 7.1 Contexto: código atual

- Linha 55: `top_edges = sorted(edges, ...)[:20]` — cap hardcoded em 20 arestas
- Linha 59: `f"- **{src_name}** ↔ **{dst_name}** ({edge.get('weight', 0)} artigos)"` — `kind` fetched mas não exibido
- Sem parâmetro `node_types`; sem warning para depth=2; todos os nós listados sem cap

### 7.2 Testes novos — escrever ANTES

Criar `tests/test_tools/test_entity_network.py` (verificar se já existe em `tests/test_tools/test_entity_tools.py`):

```python
import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_entity_network import get_entity_network


def _make_node(i: int, kind: str = "ORG") -> dict:
    return {"entityId": f"Q{i}", "canonicalName": f"Entidade{i}", "type": kind, "wikidataId": None}


def _make_edge(src: int, dst: int, weight: int = 5, kind: str = "co-mention") -> dict:
    return {"src": f"Q{src}", "dst": f"Q{dst}", "weight": weight, "kind": kind}


class TestGetEntityNetwork:
    @pytest.mark.asyncio
    async def test_retorna_rede_formatada(self):
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [_make_node(0), _make_node(1)],
            "edges": [_make_edge(0, 1)],
        }})
        result = await get_entity_network("Q0", client)
        assert "Entidade0" in result
        assert "Entidade1" in result

    @pytest.mark.asyncio
    async def test_exibe_kind_nas_arestas(self):
        """O tipo de aresta (kind) deve aparecer na listagem de conexões."""
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [_make_node(0), _make_node(1)],
            "edges": [_make_edge(0, 1, kind="COAUTHOR")],
        }})
        result = await get_entity_network("Q0", client)
        assert "COAUTHOR" in result

    @pytest.mark.asyncio
    async def test_warning_para_depth2(self):
        """depth=2 deve incluir aviso sobre volume de dados."""
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {
            "nodes": [_make_node(0)],
            "edges": [],
        }})
        result = await get_entity_network("Q0", client, depth=2)
        assert "depth=2" in result or "aviso" in result.lower() or "⚠️" in result

    @pytest.mark.asyncio
    async def test_node_types_filtra_output(self):
        """node_types='PER' deve mostrar só nós do tipo PER no output."""
        nodes = [_make_node(i, "ORG" if i % 2 == 0 else "PER") for i in range(6)]
        nodes[0]["entityId"] = "Q0"   # centro é ORG
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {"nodes": nodes, "edges": []}})
        result = await get_entity_network("Q0", client, node_types="PER")
        assert "Entidade1" in result   # PER
        assert "Entidade2" not in result   # ORG (excluído)

    @pytest.mark.asyncio
    async def test_cap_de_50_nos_no_output(self):
        """Mais de 50 nós: output deve conter aviso de truncamento."""
        nodes = [_make_node(i) for i in range(60)]
        client = FakeGraphQLClient()
        client.set_response({"entityNetwork": {"nodes": nodes, "edges": []}})
        result = await get_entity_network("Q0", client)
        assert "omitidos" in result or "truncad" in result.lower()
```

**Confirmar falha:**
```bash
pytest tests/test_tools/test_entity_tools.py tests/test_tools/test_entity_network.py -v 2>/dev/null || \
pytest tests/test_tools/test_entity_network.py -v
```

### 7.3 Implementação

**`src/gobus_mcp/tools/get_entity_network.py` — substituir inteiro:**

```python
from gobus_mcp.client import GobusGraphQLClient

_NETWORK_QUERY = """
query EntityNetwork($id: String!, $depth: Int, $limit: Int) {
  entityNetwork(id: $id, depth: $depth, limit: $limit) {
    nodes { entityId canonicalName type wikidataId }
    edges { src dst weight kind }
  }
}
"""

_MAX_OUTPUT_NODES = 50
_MAX_OUTPUT_EDGES = 50


async def get_entity_network(
    entity_id: str,
    client: GobusGraphQLClient,
    depth: int = 1,
    limit: int = 50,
    node_types: str = "",
) -> str:
    """Retorna a rede de co-menções ao redor de uma entidade.

    Args:
        entity_id: ID canônico da entidade (ex: "Q4294522")
        depth: Profundidade da busca (1 ou 2). depth=2 pode retornar centenas de nós.
        limit: Máximo de arestas a retornar do servidor
        node_types: Tipos de nó a exibir separados por vírgula (ex: "PER,ORG")
                    Tipos válidos: ORG, PER, LOC, EVENT, POLICY, LAW

    Returns:
        Markdown com nós e arestas da rede de entidades.
    """
    data = await client.execute(
        _NETWORK_QUERY,
        {"id": entity_id, "depth": min(depth, 2), "limit": min(limit, 200)},
    )
    network = data.get("entityNetwork") or {}
    nodes = network.get("nodes") or []
    edges = network.get("edges") or []

    if not nodes:
        return f"Nenhuma rede encontrada para: `{entity_id}`"

    warnings = []
    if depth >= 2:
        warnings.append(
            "⚠️ **depth=2** pode retornar centenas de nós. "
            "Use `node_types` (ex: `\"PER,ORG\"`) para filtrar."
        )

    # Filtrar por tipo de nó se solicitado (centro sempre incluso)
    if node_types:
        allowed = {t.strip().upper() for t in node_types.split(",") if t.strip()}
        nodes = [
            n for n in nodes
            if n.get("type", "").upper() in allowed or n["entityId"] == entity_id
        ]

    total_nodes = len(nodes)
    nodes_shown = nodes[:_MAX_OUTPUT_NODES]

    node_map = {n["entityId"]: n["canonicalName"] or n["entityId"] for n in nodes_shown}

    lines = [f"# Rede de entidades: {node_map.get(entity_id, entity_id)}\n"]
    if warnings:
        for w in warnings:
            lines.append(f"> {w}\n")

    lines.append(f"**{total_nodes} nós · {len(edges)} conexões**\n")
    lines.append("## Nós")

    for node in nodes_shown:
        marker = " ← **[CENTRO]**" if node["entityId"] == entity_id else ""
        wikidata = (
            f" ([W](https://www.wikidata.org/wiki/{node.get('wikidataId')}))"
            if node.get("wikidataId") else ""
        )
        lines.append(
            f"- `{node['entityId']}` **{node.get('canonicalName', '')}** "
            f"({node.get('type', '')}){wikidata}{marker}"
        )

    if total_nodes > _MAX_OUTPUT_NODES:
        lines.append(
            f"\n> … **{total_nodes - _MAX_OUTPUT_NODES} nós adicionais omitidos**. "
            f"Use `node_types` para filtrar."
        )

    if edges:
        lines.append("\n## Conexões mais fortes")
        top_edges = sorted(edges, key=lambda e: e.get("weight", 0), reverse=True)[:_MAX_OUTPUT_EDGES]
        for edge in top_edges:
            src_name = node_map.get(edge["src"], edge["src"])
            dst_name = node_map.get(edge["dst"], edge["dst"])
            kind = edge.get("kind") or ""
            kind_str = f" [{kind}]" if kind else ""
            lines.append(
                f"- **{src_name}** ↔ **{dst_name}**{kind_str} ({edge.get('weight', 0)} artigos)"
            )

    return "\n".join(lines)
```

**`src/gobus_mcp/server.py` — atualizar `gobus_get_entity_network` (linha 75–77):**

```python
@mcp.tool()
async def gobus_get_entity_network(
    entity_id: str,
    depth: int = 1,
    limit: int = 50,
    node_types: str = "",
) -> str:
    """Rede de co-menções ao redor de uma entidade (depth 1 ou 2).
    
    Use node_types="PER,ORG" para filtrar tipos de nó e evitar respostas massivas.
    depth=2 retorna uma rede mais ampla mas pode exceder o contexto MCP.
    """
    return await get_entity_network(entity_id, _client, depth, limit, node_types)
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_entity_network.py -v
```

---

## 8. Grupo F — get_agency_summary.py (nova tool)

### 8.1 Testes — escrever ANTES

Criar `tests/test_tools/test_get_agency_summary.py`:

```python
import pytest
from unittest.mock import AsyncMock
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_agency_summary import get_agency_summary


class TestGetAgencySummary:
    @pytest.mark.asyncio
    async def test_combina_analytics_e_trends(self):
        """Deve fazer 2 chamadas GraphQL e combinar no output."""
        client = FakeGraphQLClient()
        # side_effect: primeira call = analytics, segunda = trends
        client.execute = AsyncMock(side_effect=[
            {"agencyAnalytics": [{
                "period": "2026-06",
                "agencyKey": "saude",
                "agencyName": "Ministério da Saúde",
                "articleCount": 42,
                "avgSentimentScore": 0.0,
                "pctPositive": 0.0,
                "avgReadabilityFlesch": 55.0,
            }]},
            {"trendingThemes": [{
                "themeLabel": "Vacinação",
                "growthScore": 2.3,
                "windowCount": 15,
                "topArticles": [
                    {"uniqueId": "a1", "title": "Novo imunizante aprovado",
                     "publishedAt": "2026-06-20", "url": "https://gov.br/saude/a1"},
                ],
            }]},
        ])
        result = await get_agency_summary("saude", client)
        assert "Ministério da Saúde" in result
        assert "42" in result
        assert "Vacinação" in result
        assert "Novo imunizante aprovado" in result

    @pytest.mark.asyncio
    async def test_sem_dados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.execute = AsyncMock(side_effect=[
            {"agencyAnalytics": []},
            {"trendingThemes": []},
        ])
        result = await get_agency_summary("invalida", client)
        assert "invalida" in result

    @pytest.mark.asyncio
    async def test_agency_key_passado_na_primeira_call(self):
        """analytics deve ser chamado com a agency_key."""
        client = FakeGraphQLClient()
        client.execute = AsyncMock(side_effect=[
            {"agencyAnalytics": []},
            {"trendingThemes": []},
        ])
        await get_agency_summary("mec", client, days=30)
        first_call_vars = client.execute.call_args_list[0][0][1]
        assert "mec" in first_call_vars["agencies"]
```

**Confirmar falha (módulo não existe):**
```bash
pytest tests/test_tools/test_get_agency_summary.py -v
# Esperado: ImportError (módulo ainda não existe)
```

### 8.2 Implementação

Criar `src/gobus_mcp/tools/get_agency_summary.py`:

```python
from datetime import date, timedelta
from gobus_mcp.client import GobusGraphQLClient

_ANALYTICS_QUERY = """
query AgencyAnalytics(
    $agencies: [String!]!, $dateFrom: String!, $dateTo: String!, $granularity: Granularity!
) {
    agencyAnalytics(
        agencies: $agencies dateFrom: $dateFrom dateTo: $dateTo granularity: $granularity
    ) {
        period agencyKey agencyName articleCount avgSentimentScore pctPositive avgReadabilityFlesch
    }
}
"""

_TRENDS_QUERY = """
query TrendingThemes(
    $windowDays: Int!, $baselineDays: Int!, $growthThreshold: Float, $agencyKey: String, $limit: Int
) {
    trendingThemes(
        windowDays: $windowDays baselineDays: $baselineDays
        growthThreshold: $growthThreshold agencyKey: $agencyKey limit: $limit
    ) {
        themeLabel growthScore windowCount
        topArticles { uniqueId title publishedAt url }
    }
}
"""


async def get_agency_summary(
    agency_key: str,
    client: GobusGraphQLClient,
    days: int = 30,
) -> str:
    """Resumo executivo de uma agência: volume + tendências em uma chamada.

    Args:
        agency_key: Chave da agência (ex: "saude", "mec") — ver gobus://agencies
        days: Janela em dias para analytics (default 30)

    Returns:
        Markdown com volume de publicações, métricas e temas em alta.
    """
    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=days)).isoformat()

    analytics_data = await client.execute(_ANALYTICS_QUERY, {
        "agencies": [agency_key],
        "dateFrom": date_from,
        "dateTo": date_to,
        "granularity": "MONTH",
    })
    trends_data = await client.execute(_TRENDS_QUERY, {
        "windowDays": 7,
        "baselineDays": 28,
        "growthThreshold": 1.0,
        "agencyKey": agency_key,
        "limit": 5,
    })

    rows = analytics_data.get("agencyAnalytics") or []
    themes = trends_data.get("trendingThemes") or []

    if not rows and not themes:
        return f"Sem dados para agência: `{agency_key}`"

    agency_name = rows[0].get("agencyName", agency_key) if rows else agency_key
    total_articles = sum(r.get("articleCount", 0) for r in rows)

    lines = [
        f"# Resumo: {agency_name}\n",
        f"**Período:** últimos {days} dias ({date_from} → {date_to})\n",
        f"**Volume:** {total_articles} artigos publicados\n",
    ]

    if rows:
        avg_flesch = next(
            (r.get("avgReadabilityFlesch") for r in rows if r.get("avgReadabilityFlesch")),
            None,
        )
        if avg_flesch is not None:
            nivel = "fácil" if avg_flesch > 70 else ("médio" if avg_flesch > 50 else "difícil")
            lines.append(f"**Legibilidade:** {avg_flesch:.1f} ({nivel})\n")

    if themes:
        lines.append("## Temas em alta (últimos 7 dias)\n")
        for t in themes:
            lines.append(f"- 📈 **{t['themeLabel']}** · {t['growthScore']:.1f}× crescimento")
            for art in (t.get("topArticles") or [])[:2]:
                title = art.get("title", "")[:70]
                url = art.get("url", "")
                lines.append(f"  - [{title}]({url})")

    return "\n".join(lines)
```

**Registrar em `src/gobus_mcp/server.py`:**

1. Adicionar import após os imports existentes de tools:
```python
from gobus_mcp.tools.get_agency_summary import get_agency_summary
```

2. Adicionar tool após `gobus_detect_trends`:
```python
@mcp.tool()
async def gobus_get_agency_summary(agency_key: str, days: int = 30) -> str:
    """Resumo executivo de uma agência: volume + métricas + temas em alta.
    
    Combina gobus_get_agency_analytics + gobus_detect_trends em uma única chamada.
    Use agency_key de gobus://agencies (ex: 'saude', 'mec', 'fazenda').
    """
    return await get_agency_summary(agency_key, _client, days)
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_get_agency_summary.py -v
```

---

## 9. Grupo G — taxonomy_queries.py (novo resource)

### 9.1 Testes — escrever ANTES

Criar `tests/test_resources/test_taxonomy_queries.py`:

```python
import pytest
from gobus_mcp.resources.taxonomy_queries import fetch_taxonomy_queries, TAXONOMY_QUERIES


class TestTaxonomyQueries:
    @pytest.mark.asyncio
    async def test_retorna_markdown(self):
        result = await fetch_taxonomy_queries()
        assert isinstance(result, str)
        assert "##" in result

    def test_categorias_tem_pelo_menos_3_termos(self):
        for cat, terms in TAXONOMY_QUERIES.items():
            assert len(terms) >= 3, f"Categoria '{cat}' tem menos de 3 termos"

    def test_saude_e_educacao_presentes(self):
        assert "Saúde" in TAXONOMY_QUERIES
        assert "Educação" in TAXONOMY_QUERIES

    @pytest.mark.asyncio
    async def test_output_contem_saude(self):
        result = await fetch_taxonomy_queries()
        assert "Saúde" in result
```

**Confirmar falha:**
```bash
pytest tests/test_resources/test_taxonomy_queries.py -v
# Esperado: ImportError
```

### 9.2 Implementação

Criar `src/gobus_mcp/resources/taxonomy_queries.py`:

```python
TAXONOMY_QUERIES: dict[str, list[str]] = {
    "Saúde": ["saúde pública", "SUS", "vacinação", "hospital", "medicamento"],
    "Educação": ["educação", "escola", "universidade", "ENEM", "bolsa estudo"],
    "Meio Ambiente e Sustentabilidade": ["COP30", "clima", "desmatamento", "carbono", "amazônia"],
    "Esportes e Lazer": ["Copa", "Olimpíadas", "atleta", "jogos", "futebol"],
    "Economia e Finanças": ["inflação", "IPCA", "PIB", "juros", "orçamento federal"],
    "Infraestrutura e Transporte": ["obra", "rodovia", "ferrovia", "porto", "PAC"],
    "Segurança Pública": ["segurança pública", "polícia federal", "crime", "violência"],
    "Ciência e Tecnologia": ["pesquisa", "inovação", "CNPq", "CAPES", "startup"],
    "Agricultura e Agronegócio": ["agronegócio", "colheita", "safra", "MAPA", "reforma agrária"],
    "Previdência e Assistência Social": ["INSS", "aposentadoria", "Bolsa Família", "BPC", "previdência"],
    "Trabalho e Emprego": ["emprego", "CAGED", "carteira de trabalho", "salário mínimo", "trabalhador"],
    "Relações Exteriores": ["diplomacia", "acordo bilateral", "Itamaraty", "MERCOSUL", "embaixada"],
    "Minorias e Grupos Especiais": ["indígena", "quilombola", "pessoa com deficiência", "LGBTQIA+", "igualdade racial"],
    "Turismo": ["turismo", "viagem", "hospedagem", "destino turístico", "Embratur"],
    "Defesa Nacional": ["Forças Armadas", "Exército", "Marinha", "Aeronáutica", "defesa nacional"],
}


async def fetch_taxonomy_queries() -> str:
    """Mapeamento de categorias taxonômicas para termos de busca efetivos.

    Use esses termos em gobus_search_news em vez dos rótulos literais de
    gobus_detect_trends — buscas com o rótulo exato retornam resultados ruins.
    """
    lines = [
        "# Dicionário de Termos por Categoria Taxonômica\n",
        "Use em `gobus_search_news` para buscar artigos de cada categoria detectada por `gobus_detect_trends`.\n",
    ]
    for category, terms in TAXONOMY_QUERIES.items():
        terms_str = " · ".join(f'`{t}`' for t in terms)
        lines.append(f"## {category}\n{terms_str}\n")
    return "\n".join(lines)
```

**Registrar em `src/gobus_mcp/server.py`:**

1. Adicionar import após os imports de resources:
```python
from gobus_mcp.resources.taxonomy_queries import fetch_taxonomy_queries
```

2. Adicionar resource após `platform_stats_resource`:
```python
@mcp.resource("gobus://taxonomy-queries")
async def taxonomy_queries_resource() -> str:
    """Mapeamento de categorias do detect_trends para termos de busca efetivos."""
    return await fetch_taxonomy_queries()
```

**Confirmar sucesso:**
```bash
pytest tests/test_resources/test_taxonomy_queries.py -v
```

---

## 10. Verificação Local contra Produção

Após todos os grupos passarem nos testes, rodar spot-checks contra dados reais:

```bash
source .venv/bin/activate
export GOBUS_GRAPHQL_URL="https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"
```

**A. search_news com date_from/date_to:**
```bash
python -c "
import asyncio
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.search_news import search_news

async def main():
    c = GobusGraphQLClient(url='https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql')
    r = await search_news('saúde', c, date_from='2026-06-01', date_to='2026-06-24', limit=3)
    print(r[:800])
asyncio.run(main())
"
# Verificar: todos os artigos têm publishedAt em junho 2026
# Verificar: campo [agency_code] aparece ao lado do agencyName
```

**B. search_news com agency_key inválida:**
```bash
python -c "
import asyncio
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.search_news import search_news

async def main():
    c = GobusGraphQLClient(url='https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql')
    r = await search_news('emprego', c, agency_key='trabalho')
    print(r)
asyncio.run(main())
"
# Verificar: mensagem menciona gobus://agencies
```

**C. get_agency_analytics com score numérico:**
```bash
python -c "
import asyncio
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.get_agency_analytics import get_agency_analytics

async def main():
    c = GobusGraphQLClient(url='https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql')
    r = await get_agency_analytics(['saude', 'mec'], '2026-03-01', '2026-06-24', c, 'MONTH')
    print(r[:1000])
asyncio.run(main())
"
# Verificar: 'legibilidade XX.X (nível)' em vez de só 'legibilidade nível'
```

**D. detect_trends com agências:**
```bash
python -c "
import asyncio
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.detect_trends import detect_trends

async def main():
    c = GobusGraphQLClient(url='https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql')
    r = await detect_trends(c, window_days=7, baseline_days=28, growth_threshold=1.0, limit=5)
    print(r)
asyncio.run(main())
"
# Verificar: linha 'Agências:' por tema com nomes e contagens
```

**E. get_agency_summary (nova tool):**
```bash
python -c "
import asyncio
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.get_agency_summary import get_agency_summary

async def main():
    c = GobusGraphQLClient(url='https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql')
    r = await get_agency_summary('saude', c, days=30)
    print(r)
asyncio.run(main())
"
# Verificar: volume + temas em alta em um único output
```

---

## 11. Estratégia de Subagentes

Lançar 4 agentes em paralelo (background). O agente principal orquestra, não implementa.

```
Agent 1 (run_in_background=True): Grupos A + B
  → tests/test_tools/test_search_news.py + tests/test_tools/test_get_article.py
  → src/gobus_mcp/tools/search_news.py + src/gobus_mcp/tools/get_article.py + server.py (search+article)
  → Spot-checks A e B

Agent 2 (run_in_background=True): Grupos C + D
  → tests/test_tools/test_analytics_tools.py
  → src/gobus_mcp/tools/get_agency_analytics.py + src/gobus_mcp/tools/detect_trends.py
  → Spot-checks C e D

Agent 3 (run_in_background=True): Grupo E
  → tests/test_tools/test_entity_network.py (criar) + tests/test_tools/test_entity_tools.py (manter)
  → src/gobus_mcp/tools/get_entity_network.py + server.py (entity_network)
  → Spot-check E

Agent 4 (run_in_background=True): Grupos F + G
  → tests/test_tools/test_get_agency_summary.py (criar)
  → tests/test_resources/test_taxonomy_queries.py (criar)
  → src/gobus_mcp/tools/get_agency_summary.py (criar)
  → src/gobus_mcp/resources/taxonomy_queries.py (criar)
  → server.py (registrar get_agency_summary + taxonomy_queries)
  → Spot-check E e G

Agent 5 (run_in_background=True): Grupos H + I + J + K (issue #2)
  → src/gobus_mcp/server.py (reescrever 8 docstrings de tools — Grupo H)
  → .claude/skills/gobus.md (criar — Grupo I)
  → src/gobus_mcp/tools/get_entity_network.py (adicionar max_nodes — Grupo J)
  → src/gobus_mcp/tools/get_entity_profile.py (adicionar summary_only — Grupo J)
  → src/gobus_mcp/server.py (atualizar assinaturas das tools — Grupo J)
  → tests/test_tools/test_entity_context_control.py (criar — Grupo J)
  → src/gobus_mcp/prompts/monitor_agency.py + trace_entity.py + weekly_digest.py (hints — Grupo K)
  → Validação qualitativa (seção 14.5)
```

**Após todos completarem:**
```bash
# Suite completa
pytest tests/ -v

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

---

## 12. Mudanças Upstream (repos separados)

### 12.1 graphql-api — Analytics Diária com Dias Vazios (P3.11)

**Arquivo:** `graphql-api/src/graphql_api/schema/resolvers/analytics.py`

No resolver de `agencyAnalytics` com `granularity=DAY`, usar `generate_series` para garantir todos os dias:
```sql
SELECT gs.day::date AS period, COALESCE(a.article_count, 0) AS article_count, ...
FROM generate_series(date_from::date, date_to::date, '1 day'::interval) AS gs(day)
LEFT JOIN agency_analytics a ON a.period = gs.day::date AND a.agency_key = ANY($agencies)
```

### 12.2 SQL Ad-Hoc — Limpeza de Artigos MOCK (P2.9)

Conectar ao Cloud SQL (<IP-CLOUD-SQL>, banco `govbrnews`) e executar:

```sql
-- Verificar primeiro
SELECT unique_id, title, LEFT(summary, 100) AS summary_preview
FROM news
WHERE summary LIKE '[MOCK]%' OR title LIKE '[MOCK]%'
ORDER BY published_at DESC;

-- Limpar (após revisar os IDs acima)
DELETE FROM news WHERE summary LIKE '[MOCK]%';

-- Verificar propagação (reindexação Typesense é via trigger)
```

---

## 13. Commit & PR

Convenções do repo gobus-mcp:
- **Idioma dos commits:** português
- **Prefixos:** `fix:` / `feature:` / `refactor:` / `chore:`
- **Sem Co-Authored-By** neste repo

Sugestão de mensagem de commit:
```
feature: filtros temporais, agency code, legibilidade numérica, agency summary e otimizações de agente

- search_news: date_from/date_to, campo agency, limit slicing, hint agency_key inválida
- get_article: campo agency code na exibição
- get_agency_analytics: score Flesch numérico, pctNegative, avgWordCount
- detect_trends: agências por tema via topArticles
- get_entity_network: node_types filter, warning depth=2, cap 50/50, kind nas arestas
- nova tool gobus_get_agency_summary: analytics + tendências em 1 chamada
- novo resource gobus://taxonomy-queries: dicionário categoria → termos de busca
- descriptions das 8 tools reescritas com 6 critérios do paper 2602.14878 (issue #2)
- nova skill host-side .claude/skills/gobus.md com mapa UC→tool (issue #2)
- get_entity_network: parâmetro max_nodes (default 20) para controle de contexto (issue #2)
- get_entity_profile: parâmetro summary_only para payload reduzido (issue #2)
- prompts MCP com hints explícitos de paralelismo (issue #2)
```

---

## 14. Issue #2 — Otimizar Desempenho do Agente

> Fonte: [github.com/destaquesgovbr/gobus-mcp/issues/2](https://github.com/destaquesgovbr/gobus-mcp/issues/2)
> Referência: paper 2602.14878 — "MCP Tool Descriptions Are Smelly!"

Quatro alavancas de performance não exploradas pelos grupos A–G:
- **H** — Descriptions das tools (maior alavanca: o modelo seleciona tools pelo texto do docstring)
- **I** — Skill host-side (ensina *quando* orquestrar os workflows, não apenas *como*)
- **J** — Controle de tamanho de contexto (`max_nodes`, `summary_only`)
- **K** — Hints de paralelismo nos MCP Prompts

---

### 14.1 Grupo H — Revisar descriptions das tools

**Sem TDD** — mudanças nos docstrings dos `@mcp.tool` em `server.py`. Validação qualitativa na seção 14.5.

#### Critérios de qualidade (6 componentes do paper 2602.14878)

| # | Critério | Obrigatório |
|---|----------|-------------|
| 1 | **Purpose** — o que a tool faz | sim |
| 2 | **Parameters** — o que cada parâmetro significa e valores válidos | sim |
| 3 | **Return value** — o que é retornado e em que formato | sim |
| 4 | **Side effects** — efeitos colaterais (N/A para tools read-only) | quando houver |
| 5 | **Examples** — exemplos de uso (quando a semântica não é óbvia) | recomendado |
| 6 | **Constraints** — limites, pré-condições, ordem de chamada recomendada | sim |

#### Substituir os docstrings em `src/gobus_mcp/server.py`

**`gobus_search_news`:**
```python
    """Busca notícias no portal Gov.BR por texto livre e/ou agência governamental.

    Parâmetros:
    - query: texto para busca semântica/full-text (obrigatório)
    - agency_key: chave curta da agência, ex: "saude", "mec" — consultar gobus://agencies;
      chave inválida retorna 0 resultados com dica automática
    - page: número da página de resultados (default 1)
    - limit: máximo de artigos (default 10, máximo 50)
    - date_from / date_to: filtros temporais ISO "YYYY-MM-DD" (ex: "2026-01-01")

    Retorna: Markdown com artigos (título, agência, data, resumo, URL, trendingScore, viewCount).

    Chamadas paralelizáveis: pode rodar em paralelo com gobus_get_agency_analytics
    quando ambas operam sobre a mesma agência.

    Restrições: Não substitui gobus_get_agency_analytics para análise temporal agregada.
    """
```

**`gobus_get_article`:**
```python
    """Retorna o conteúdo completo de um artigo pelo seu ID único.

    Parâmetros:
    - unique_id: ID do artigo obtido de gobus_search_news ou gobus_detect_trends
      (campo uniqueId na resposta dessas tools)

    Retorna: Markdown com título, agência, data de publicação, corpo completo
    e metadados (trendingScore, viewCount, agency code).

    Restrições: Não tente adivinhar IDs — use apenas IDs obtidos de outras tools.
    """
```

**`gobus_resolve_entity` (pré-condição crítica):**
```python
    """Resolve um nome de entidade para seu ID canônico (Wikidata QID).

    IMPORTANTE: chame esta tool ANTES de gobus_get_entity_profile e
    gobus_get_entity_network — ambas precisam do entityId canônico que só
    esta tool fornece.

    Parâmetros:
    - query: nome, alias ou variação (ex: "Lula", "Presidente da República", "PT")
    - entity_type: filtro opcional — ORG, PER, LOC, EVENT, POLICY, LAW
    - limit: máximo de candidatos (default 5)

    Retorna: Lista de candidatos com entityId (ex: "Q4294522"), nome canônico,
    tipo, aliases e score de confiança. Escolha o candidato com maior confiança.

    Exemplos:
    - query="Ministério da Saúde" entity_type="ORG" → Q3290862
    - query="COP30" entity_type="EVENT" → Q...

    Restrições: Pode retornar múltiplos candidatos quando há ambiguidade.
    Confirme o ID correto antes de usar em outras tools.
    """
```

**`gobus_get_entity_profile`:**
```python
    """Perfil completo de uma entidade: cobertura temporal + entidades relacionadas.

    Pré-condição: use gobus_resolve_entity primeiro para confirmar o nome canônico.

    Parâmetros:
    - entity_name: nome da entidade (de preferência canônico, de gobus_resolve_entity)
    - entity_type: tipo opcional — ORG, PER, LOC, EVENT, POLICY, LAW
    - date_from / date_to: filtros temporais ISO
    - summary_only: se True, retorna apenas contagens totais e top-3 relacionadas
      (payload menor — use quando tamanho do contexto importa)

    Retorna: Markdown com identificação (ID, Wikidata, aliases), série temporal
    de artigos por período/agência e entidades relacionadas por peso de co-menção.

    Chamadas paralelizáveis: após gobus_resolve_entity, pode rodar em paralelo
    com gobus_get_entity_network.
    """
```

**`gobus_get_entity_network`:**
```python
    """Rede de co-menções ao redor de uma entidade: nós (entidades) + arestas (força de associação).

    Pré-condição: use gobus_resolve_entity para obter o entityId canônico
    no formato "Q<número>" (ex: "Q4294522").

    Parâmetros:
    - entity_id: ID canônico Wikidata da entidade central
    - depth: profundidade — 1 = vizinhos diretos, 2 = vizinhos de vizinhos
    - limit: máximo de arestas retornadas (default 50)
    - max_nodes: máximo de nós no output (default 20; reduza para minimizar contexto)
    - node_types: filtro de tipos, ex: ["ORG", "PER"] — omitir = todos os tipos

    Retorna: Markdown com nós e arestas ordenadas por peso (artigos em comum) decrescente.

    AVISO: depth=2 expande exponencialmente — combine com max_nodes ≤ 15 quando usar.

    Chamadas paralelizáveis: após gobus_resolve_entity, pode rodar em paralelo
    com gobus_get_entity_profile.
    """
```

**`gobus_get_agency_analytics`:**
```python
    """Métricas de publicação por agência e período: volume, sentimento e legibilidade.

    Parâmetros:
    - agencies: lista de chaves de agência (ex: ["saude", "mec"]) — ver gobus://agencies
    - date_from / date_to: período no formato ISO "YYYY-MM-DD"
    - granularity: "DAY", "WEEK" ou "MONTH" (default "MONTH")

    Retorna: Markdown com tabela por período contendo:
    - Contagem de artigos
    - avgSentimentScore (−1 a +1), pctNegative, avgWordCount
    - Índice de legibilidade Flesch (numérico + nível: fácil/médio/difícil)

    Chamadas paralelizáveis: pode rodar em paralelo com gobus_search_news
    para a mesma agência.

    Restrições: granularity=DAY pode ter gaps em dias sem publicação.
    Use granularity=MONTH para séries históricas longas.
    """
```

**`gobus_detect_trends`:**
```python
    """Detecta temas em crescimento no portal Gov.BR comparando janela recente com baseline.

    Semântica temporal:
    - window_days: janela RECENTE de análise (ex: 7 = últimos 7 dias)
    - baseline_days: período de REFERÊNCIA anterior à janela (ex: 28 = 28 dias antes)
    - growthScore = count(window) / count(baseline) — valores > 1.5 indicam crescimento real

    Parâmetros:
    - window_days: dias da janela recente (default 7)
    - baseline_days: dias do baseline de comparação (default 28)
    - growth_threshold: fator mínimo de crescimento para inclusão (default 1.5)
    - agency_key: filtrar por agência (opcional) — ver gobus://agencies
    - limit: máximo de temas (default 10)

    Retorna: Markdown com temas ordenados por growthScore, top artigos e
    agências que mais publicaram sobre cada tema.

    Restrições: Detecta crescimento RELATIVO ao baseline, não absoluto. Temas novos
    sem histórico no baseline podem ter growthScore artificialmente alto.
    """
```

**`gobus_get_agency_summary` (novo — registrado no Grupo F):**
```python
    """Resumo executivo de uma agência: volume + métricas + temas em alta em uma única chamada.

    Combina gobus_get_agency_analytics + gobus_detect_trends (filtrado para a agência).
    Use quando precisar de overview rápido sem granularidade detalhada.

    Parâmetros:
    - agency_key: chave da agência (ex: "saude", "mec") — ver gobus://agencies
    - days: janela em dias (default 30)

    Retorna: Markdown com volume total de artigos, índice de legibilidade e
    temas em alta com links para artigos representativos.

    Restrições: Não substitui gobus_get_agency_analytics quando precisar de
    granularidade por dia/semana ou comparar múltiplas agências.
    """
```

---

### 14.2 Grupo I — Skill host-side para Claude Code / Claude Desktop

**Sem TDD** — criar arquivo de skill e validar qualitativamente (seção 14.5).

Criar `.claude/skills/gobus.md` na raiz do repo:

```markdown
---
name: gobus
description: >
  Orquestra as tools do gobus-mcp para responder perguntas sobre atividade do governo federal
  brasileiro. Use quando o usuário perguntar sobre notícias, agências, entidades ou tendências
  do portal Gov.BR.
---

# Gobus MCP — Guia de Orquestração

## Mapa de Use Cases → Tools

| UC | Pergunta típica | Tool principal | Tools auxiliares |
|----|----------------|----------------|-----------------|
| UC-01 | "O que saiu hoje/ontem no MEC?" | `search_news` (agency_key + date_from) | `get_agency_analytics` (em paralelo) |
| UC-02 | "Quero ler este artigo completo" | `get_article` (unique_id) | — |
| UC-03 | "Quem é [entidade] no gov.br?" | `resolve_entity` → `get_entity_profile` | `get_entity_network` (em paralelo com perfil) |
| UC-04 | "Quais temas estão crescendo?" | `detect_trends` | `search_news` por tema (paralelo entre temas) |
| UC-05 | "Com quem [entidade] aparece associada?" | `resolve_entity` → `get_entity_network` | — |
| UC-06 | "Faça um boletim semanal" | prompt `weekly_digest` | — |
| UC-07 | "Escreva um release sobre [tema]" | prompt `draft_press_release` | — |
| UC-08 | "Compare MEC e Saúde no último mês" | `get_agency_analytics` (agencies=[...]) | — |
| UC-09 | "Trace a trajetória de [entidade]" | prompt `trace_entity` | — |
| UC-10 | "Resumo rápido da agência X" | `get_agency_summary` | — |

## Regras de Orquestração

### Regra 1: Sempre `resolve_entity` antes de operações de entidade
`get_entity_profile` e `get_entity_network` precisam do entityId canônico (Wikidata QID).
Nunca use nomes literais diretamente — sempre resolva primeiro.

### Regra 2: UC-01 — perguntas "o que saiu hoje/ontem"
→ Use `search_news` com agency_key + date_from (ontem ou hoje ISO).
→ Execute `get_agency_analytics` em paralelo para métricas de volume.

### Regra 3: UC-04 — perguntas sobre tendências
→ Use `detect_trends` com window_days=7 e baseline_days=28.
→ Para cada tema encontrado, execute `search_news` buscando os termos do tema.
→ Consulte `gobus://taxonomy-queries` para obter termos de busca corretos por categoria.

### Regra 4: Paralelismo
- `search_news` + `get_agency_analytics` para a mesma agência: **paralelo**
- `get_entity_profile` + `get_entity_network` após resolver entityId: **paralelo**
- `search_news` para temas diferentes em UC-04: **paralelo entre temas**

### Regra 5: Controle de contexto para redes grandes
- `get_entity_network` com depth=2: sempre use `max_nodes ≤ 15`
- `get_entity_profile` quando só precisar de resumo: use `summary_only=True`

## Glossário Mínimo

| Termo | Significado |
|-------|-------------|
| `agency_key` | Chave curta de agência (ex: "saude", "mec") — listar em gobus://agencies |
| `entity_id` | ID canônico Wikidata no formato "Q<número>" (ex: "Q4294522") |
| `granularity` | Agrupamento temporal: "DAY", "WEEK" ou "MONTH" |
| `window_days` | Janela RECENTE em detect_trends (quantos dias "agora") |
| `baseline_days` | Período de REFERÊNCIA em detect_trends (quantos dias de histórico) |
| `growthScore` | count(window) / count(baseline) — > 1.5 indica tendência real |

## Resources disponíveis

- `gobus://agencies` — lista completa de agências e suas chaves
- `gobus://themes` — taxonomia de temas do portal
- `gobus://platform-stats` — estatísticas gerais (últimos 30 dias)
- `gobus://taxonomy-queries` — dicionário categoria → termos de busca efetivos
```

---

### 14.3 Grupo J — Parâmetros de controle de contexto

TDD padrão (escrever testes → confirmar falha → implementar → confirmar sucesso).

#### 14.3.1 Testes — escrever ANTES

Criar `tests/test_tools/test_entity_context_control.py`:

```python
import pytest
from tests.conftest import FakeGraphQLClient
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile


def _make_network_response(n_nodes: int) -> dict:
    nodes = [
        {"entityId": f"Q{i}", "canonicalName": f"Ent{i}", "type": "ORG", "wikidataId": None}
        for i in range(n_nodes)
    ]
    edges = [{"src": "Q0", "dst": f"Q{i}", "weight": i, "kind": "co_mention"} for i in range(1, n_nodes)]
    return {"entityNetwork": {"nodes": nodes, "edges": edges}}


class TestMaxNodes:
    @pytest.mark.asyncio
    async def test_max_nodes_limita_output(self):
        client = FakeGraphQLClient()
        client.set_response(_make_network_response(40))
        result = await get_entity_network("Q0", client, depth=1, max_nodes=5)
        node_lines = [l for l in result.split("\n") if l.startswith("- `Q")]
        assert len(node_lines) <= 5

    @pytest.mark.asyncio
    async def test_max_nodes_default_e_20(self):
        client = FakeGraphQLClient()
        client.set_response(_make_network_response(40))
        result = await get_entity_network("Q0", client, depth=1)
        node_lines = [l for l in result.split("\n") if l.startswith("- `Q")]
        assert len(node_lines) <= 20


_ENTITY_SEARCH_HIT = {
    "entityId": "Q123", "canonicalName": "Saúde", "type": "ORG",
    "description": None, "wikidataUrl": None, "agencyKey": None,
    "aliases": [], "articleCount": 100, "confidence": 0.9, "matchType": "exact",
}
_COVERAGE_ROW = {
    "period": "2026-01", "agencyKey": "saude", "agencyName": "Saúde",
    "articleCount": 10, "totalMentions": 20, "avgSentimentScore": None,
}
_RELATED_ROW = {"canonicalId": "Q456", "canonicalName": "SUS", "type": "ORG", "weight": 5}


class TestSummaryOnly:
    @pytest.mark.asyncio
    async def test_summary_only_omite_serie_temporal(self):
        client = FakeGraphQLClient()
        # set_responses é chamado sequencialmente a cada client.execute()
        client.set_responses([
            {"entitySearch": [_ENTITY_SEARCH_HIT]},
            {"entityCoverage": [_COVERAGE_ROW] * 12},
            {"relatedEntities": [_RELATED_ROW] * 5},
        ])
        result = await get_entity_profile("Saúde", client, summary_only=True)
        # Sem listagem linha-a-linha da série temporal
        assert "2026-01" not in result
        # Total e top-3 relacionadas ainda presentes
        assert "100" in result or "artigos" in result.lower()
        assert "SUS" in result

    @pytest.mark.asyncio
    async def test_summary_only_false_retorna_serie_completa(self):
        client = FakeGraphQLClient()
        client.set_responses([
            {"entitySearch": [_ENTITY_SEARCH_HIT]},
            {"entityCoverage": [_COVERAGE_ROW]},
            {"relatedEntities": []},
        ])
        result = await get_entity_profile("Saúde", client, summary_only=False)
        assert "2026-01" in result
```

> **Nota sobre `set_responses`:** Verifique `tests/conftest.py` — se `FakeGraphQLClient`
> não suportar `set_responses(list)` para múltiplas chamadas sequenciais, adicione esse método:
> ```python
> def set_responses(self, responses: list[dict]) -> None:
>     self.execute.side_effect = [r for r in responses]
> ```

**Confirmar falha:**
```bash
pytest tests/test_tools/test_entity_context_control.py -v
# Esperado: TypeError (parâmetros max_nodes/summary_only não existem ainda)
```

#### 14.3.2 Implementação

**`src/gobus_mcp/tools/get_entity_network.py`** — adicionar `max_nodes`:

Alterar assinatura da função:
```python
async def get_entity_network(
    entity_id: str,
    client: GobusGraphQLClient,
    depth: int = 1,
    limit: int = 50,
    max_nodes: int = 20,          # ← novo
    node_types: list[str] | None = None,  # ← já deve existir do Grupo E
) -> str:
```

Aplicar cap após receber os dados do GraphQL (antes de montar `node_map`):
```python
    nodes = network.get("nodes") or []
    edges = network.get("edges") or []

    if node_types:
        nodes = [n for n in nodes if n.get("type") in node_types]
    nodes = nodes[:max_nodes]   # ← adicionar aqui
    node_ids = {n["entityId"] for n in nodes}
    edges = [e for e in edges if e["src"] in node_ids and e["dst"] in node_ids]
```

**`src/gobus_mcp/tools/get_entity_profile.py`** — adicionar `summary_only`:

Alterar assinatura:
```python
async def get_entity_profile(
    entity_name: str,
    client: GobusGraphQLClient,
    entity_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    summary_only: bool = False,   # ← novo
) -> str:
```

Adicionar branch antes da renderização da cobertura detalhada:
```python
    if summary_only:
        total_articles = sum(p["articleCount"] for p in coverage)
        lines.append(f"\n**Cobertura total:** {total_articles} artigos")
        if related:
            top3_str = ", ".join(
                f"{r.get('canonicalName')} ({r.get('type')})" for r in related[:3]
            )
            lines.append(f"**Top relacionadas:** {top3_str}")
        return "\n".join(lines)
    # caso contrário: fluxo normal com série completa (código existente)
```

**`src/gobus_mcp/server.py`** — atualizar assinaturas dos dois tools:
```python
@mcp.tool()
async def gobus_get_entity_network(
    entity_id: str,
    depth: int = 1,
    limit: int = 50,
    max_nodes: int = 20,
    node_types: list[str] | None = None,
) -> str:
    ...
    return await get_entity_network(entity_id, _client, depth, limit, max_nodes, node_types)


@mcp.tool()
async def gobus_get_entity_profile(
    entity_name: str,
    entity_type: str = "",
    date_from: str = "",
    date_to: str = "",
    summary_only: bool = False,
) -> str:
    ...
    return await get_entity_profile(
        entity_name, _client, entity_type or None, date_from or None, date_to or None, summary_only
    )
```

**Confirmar sucesso:**
```bash
pytest tests/test_tools/test_entity_context_control.py -v
pytest tests/test_tools/test_entity_tools.py -v  # Regressão
```

---

### 14.4 Grupo K — Hints de paralelismo nos MCP Prompts

**Sem TDD** — mudanças textuais nos prompts. Inspecionar output final manualmente.

**`src/gobus_mcp/prompts/monitor_agency.py`** — adicionar após a linha do step "## 2.":

```
> **Dica de paralelismo:** As chamadas `search_news` (step 1) e `get_agency_analytics`
> (step 2) são independentes entre si — execute-as em paralelo para reduzir latência.
```

**`src/gobus_mcp/prompts/trace_entity.py`** — adicionar após "### 3." e antes de "### 4.":

```
> **Dica de paralelismo:** Após obter o entityId de `resolve_entity` (step 1),
> `get_entity_profile` (step 2) e `get_entity_network` (step 3) são independentes
> e podem ser executadas em paralelo.
```

**`src/gobus_mcp/prompts/weekly_digest.py`** — adicionar após "### 3.":

```
> **Dica de paralelismo:** Para os temas retornados por `detect_trends` (step 1),
> as chamadas `search_news` de cada tema (step 3) são independentes entre si
> e podem ser executadas em paralelo.
```

---

### 14.5 Validação Qualitativa (Grupos H, I, K)

Após implementar todos os grupos da issue #2, testar em sessão limpa (sem contexto prévio do gobus):

**Critério de conclusão:** Agente sem system prompt extra consegue executar UC-01, UC-03 e UC-04 corretamente usando apenas as tools do MCP.

**Teste UC-01:**
```
O que o Ministério da Saúde publicou ontem?
```
→ Esperado: agente chama `search_news` com agency_key="saude" + date_from=ontem ISO,
  e opcionalmente `get_agency_analytics` em paralelo. **NÃO** deve exigir que o usuário forneça agency_key manualmente.

**Teste UC-03:**
```
Quero ver o perfil de cobertura do SUS no portal gov.br
```
→ Esperado: agente chama `resolve_entity` primeiro, depois `get_entity_profile` + `get_entity_network` em paralelo.

**Teste UC-04:**
```
Quais temas do governo estão crescendo esta semana?
```
→ Esperado: agente chama `detect_trends` com window_days=7 e baseline_days=28 (não com valores arbitrários), depois `search_news` para os temas em alta.

---

## Apêndice: Arquivos a Criar/Modificar

| Operação | Arquivo |
|----------|---------|
| Substituir | `src/gobus_mcp/tools/search_news.py` |
| Modificar | `src/gobus_mcp/tools/get_article.py` |
| Modificar | `src/gobus_mcp/tools/get_agency_analytics.py` |
| Modificar | `src/gobus_mcp/tools/detect_trends.py` |
| Substituir | `src/gobus_mcp/tools/get_entity_network.py` |
| Criar | `src/gobus_mcp/tools/get_agency_summary.py` |
| Criar | `src/gobus_mcp/resources/taxonomy_queries.py` |
| Modificar | `src/gobus_mcp/server.py` (4 mudanças A–G + 8 docstrings H + 2 assinaturas J) |
| Substituir | `tests/test_tools/test_search_news.py` |
| Modificar | `tests/test_tools/test_analytics_tools.py` (+ novos testes em classes existentes) |
| Modificar | `tests/test_tools/test_get_article.py` (+ 1 novo teste) |
| Criar | `tests/test_tools/test_entity_network.py` |
| Criar | `tests/test_tools/test_get_agency_summary.py` |
| Criar | `tests/test_resources/test_taxonomy_queries.py` |
| Criar | `tests/test_tools/test_entity_context_control.py` (Grupo J) |
| Criar | `.claude/skills/gobus.md` (Grupo I) |
| Modificar | `src/gobus_mcp/tools/get_entity_network.py` (+ max_nodes — Grupo J) |
| Modificar | `src/gobus_mcp/tools/get_entity_profile.py` (+ summary_only — Grupo J) |
| Modificar | `src/gobus_mcp/prompts/monitor_agency.py` (Grupo K) |
| Modificar | `src/gobus_mcp/prompts/trace_entity.py` (Grupo K) |
| Modificar | `src/gobus_mcp/prompts/weekly_digest.py` (Grupo K) |
