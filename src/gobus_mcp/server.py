import asyncio
import logging

from fastmcp import FastMCP

from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.config import settings
from gobus_mcp.tools.search_news import search_news
from gobus_mcp.tools.get_article import get_article
from gobus_mcp.tools.resolve_entity import resolve_entity
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_agency_analytics import get_agency_analytics
from gobus_mcp.tools.detect_trends import detect_trends
from gobus_mcp.tools.get_agency_summary import get_agency_summary
from gobus_mcp.resources.agencies import fetch_agencies
from gobus_mcp.resources.themes import fetch_themes
from gobus_mcp.resources.platform_stats import fetch_platform_stats
from gobus_mcp.resources.taxonomy_queries import fetch_taxonomy_queries
from gobus_mcp.prompts.monitor_agency import monitor_agency_prompt
from gobus_mcp.prompts.draft_press_release import draft_press_release_prompt
from gobus_mcp.prompts.trace_entity import trace_entity_prompt
from gobus_mcp.prompts.weekly_digest import weekly_digest_prompt

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP(name="Gobus")

_client = GobusGraphQLClient(
    url=settings.graphql_url,
    api_key=settings.graphql_api_key,
    timeout=settings.request_timeout,
)


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def gobus_search_news(
    query: str,
    agency_key: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    limit: int = 10,
) -> str:
    """Busca notícias no portal Gov.BR por texto livre e/ou agência.

    Parâmetros:
    - query: Texto livre de busca (ex: "vacinação infantil")
    - agency_key: Chave da agência para filtrar (ex: "saude", "mec") — ver gobus://agencies
    - date_from: Data de início ISO (ex: "2024-01-01") — opcional
    - date_to: Data de fim ISO (ex: "2024-12-31") — opcional
    - page: Página de resultados (default 1)
    - limit: Artigos por página (default 10, máx 50)

    Retorna: Lista de artigos com título, agência, data e trecho do conteúdo.

    Dica: Execute em paralelo com gobus_get_agency_analytics para a mesma agência.
    """
    return await search_news(query, _client, agency_key or None, page, limit, date_from or None, date_to or None)


@mcp.tool()
async def gobus_get_article(unique_id: str) -> str:
    """Retorna conteúdo completo de um artigo pelo seu unique_id.

    Parâmetros:
    - unique_id: ID único do artigo (obtido via gobus_search_news)

    Retorna: Markdown com título, agência, data, corpo completo e metadados.

    Restrições: Não use para descoberta — primeiro busque com gobus_search_news,
    depois use este tool para ler os artigos de interesse.
    """
    return await get_article(unique_id, _client)


@mcp.tool()
async def gobus_resolve_entity(query: str, entity_type: str = "", limit: int = 5) -> str:
    """Resolve nome ou alias de entidade para o ID canônico (Wikidata QID).

    Parâmetros:
    - query: Nome ou alias da entidade (ex: "Lula", "Ministério da Saúde")
    - entity_type: Tipo para filtrar — ORG, PER, LOC, EVENT, POLICY, LAW (opcional)
    - limit: Número máximo de candidatos retornados (default 5)

    Retorna: Lista de entidades com entityId, nome canônico, tipo e score de confiança.

    Fluxo: SEMPRE use este tool antes de gobus_get_entity_profile ou
    gobus_get_entity_network — ambos precisam do entityId canônico.
    """
    return await resolve_entity(query, _client, entity_type or None, limit)


@mcp.tool()
async def gobus_get_entity_profile(
    entity_name: str,
    entity_type: str = "",
    date_from: str = "",
    date_to: str = "",
    summary_only: bool = False,
) -> str:
    """Perfil completo de entidade: cobertura temporal + entidades relacionadas.

    Parâmetros:
    - entity_name: Nome ou alias da entidade (ex: "Ministério da Saúde")
    - entity_type: Tipo para filtrar — ORG, PER, LOC, EVENT, POLICY, LAW (opcional)
    - date_from: Data de início ISO (ex: "2024-01-01") — opcional
    - date_to: Data de fim ISO (ex: "2024-12-31") — opcional
    - summary_only: Se True, retorna apenas totais e top-3 relacionadas (sem série temporal)

    Retorna: Markdown com identidade, série temporal de cobertura e entidades relacionadas.

    Dica de paralelismo: Após resolver o entityId, execute em paralelo com
    gobus_get_entity_network para economizar latência.
    Use summary_only=True quando precisar apenas de um overview rápido.
    """
    return await get_entity_profile(
        entity_name, _client,
        entity_type or None, date_from or None, date_to or None, summary_only
    )


@mcp.tool()
async def gobus_get_entity_network(
    entity_id: str,
    depth: int = 1,
    limit: int = 50,
    max_nodes: int = 20,
    node_types: str = "",
) -> str:
    """Rede de co-menções ao redor de uma entidade (grafo de relacionamentos).

    Parâmetros:
    - entity_id: ID canônico Wikidata (ex: "Q4294522") — obter via gobus_resolve_entity
    - depth: Profundidade do grafo — 1 (vizinhos diretos) ou 2 (vizinhos de vizinhos)
    - limit: Máximo de nós buscados na API (default 50, máx 200)
    - max_nodes: Máximo de nós exibidos no output (default 20)
    - node_types: Tipos de nó para filtrar, separados por vírgula (ex: "PER,ORG")

    Retorna: Markdown com lista de nós e conexões mais fortes por peso de co-menção.

    Atenção: depth=2 pode retornar centenas de nós — use sempre max_nodes ≤ 15
    e node_types para filtrar quando depth=2.
    """
    return await get_entity_network(entity_id, _client, depth, limit, max_nodes, node_types or "")


@mcp.tool()
async def gobus_get_agency_analytics(
    agencies: list[str],
    date_from: str,
    date_to: str,
    granularity: str = "MONTH",
) -> str:
    """Métricas de publicação por agência: volume, sentimento e legibilidade.

    Parâmetros:
    - agencies: Lista de chaves de agência (ex: ["saude", "mec"]) — ver gobus://agencies
    - date_from: Data de início ISO (ex: "2024-01-01")
    - date_to: Data de fim ISO (ex: "2024-12-31")
    - granularity: Agrupamento temporal — "DAY", "WEEK" ou "MONTH" (default "MONTH")

    Retorna: Markdown com tabela de métricas por período: artigos publicados,
    sentimento médio, % positivo e índice de legibilidade Flesch.

    Dica de paralelismo: Execute em paralelo com gobus_search_news para a mesma agência.
    Para overview rápido sem granularidade, prefira gobus_get_agency_summary.
    """
    return await get_agency_analytics(agencies, date_from, date_to, _client, granularity)


@mcp.tool()
async def gobus_detect_trends(
    window_days: int = 7,
    baseline_days: int = 28,
    min_articles: int = 3,
    growth_threshold: float = 1.5,
    agency_key: str = "",
    limit: int = 10,
) -> str:
    """Detecta temas em crescimento comparando janela recente com baseline histórico.

    Parâmetros:
    - window_days: Janela RECENTE em dias (default 7 — "esta semana")
    - baseline_days: Período de REFERÊNCIA em dias (default 28 — "último mês")
    - min_articles: Mínimo de artigos na janela recente para considerar (default 3)
    - growth_threshold: Multiplicador mínimo de crescimento, ex: 1.5 = 50% a mais (default 1.5)
    - agency_key: Filtrar por agência específica (opcional) — ver gobus://agencies
    - limit: Máximo de temas retornados (default 10)

    Retorna: Markdown com temas em alta, growthScore e artigos representativos.
    growthScore = count(window) / count(baseline) — valores > 1.5 indicam tendência real.

    Dica: Use gobus://taxonomy-queries para mapear temas detectados a termos de busca.
    Para cada tema, execute gobus_search_news em paralelo com o nome do tema.
    """
    return await detect_trends(_client, window_days, baseline_days, min_articles, growth_threshold, agency_key or None, limit)


@mcp.tool()
async def gobus_get_agency_summary(agency_key: str, days: int = 30) -> str:
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
    return await get_agency_summary(agency_key, _client, days)


# ── Resources ────────────────────────────────────────────────────────────────

@mcp.resource("gobus://agencies")
async def agencies_resource() -> str:
    """Lista completa de agências governamentais com suas chaves."""
    return await fetch_agencies(_client)


@mcp.resource("gobus://themes")
async def themes_resource() -> str:
    """Taxonomia completa de temas do portal Gov.BR."""
    return await fetch_themes(_client)


@mcp.resource("gobus://platform-stats")
async def platform_stats_resource() -> str:
    """Estatísticas gerais da plataforma (últimos 30 dias)."""
    return await fetch_platform_stats(_client)


@mcp.resource("gobus://taxonomy-queries")
async def taxonomy_queries_resource() -> str:
    """Mapeamento de categorias do detect_trends para termos de busca efetivos."""
    return await fetch_taxonomy_queries()


# ── Prompts ──────────────────────────────────────────────────────────────────

@mcp.prompt()
def prompt_monitor_agency(agency_key: str, agency_name: str = "", days: int = 1) -> list[dict]:
    """Briefing diário de comunicação de uma agência governamental."""
    return monitor_agency_prompt(agency_key, agency_name, days)


@mcp.prompt()
def prompt_draft_press_release(topic: str, agency_key: str = "", limit: int = 5) -> list[dict]:
    """Rascunho de release de imprensa baseado em artigos do portal."""
    return draft_press_release_prompt(topic, agency_key, limit)


@mcp.prompt()
def prompt_trace_entity(entity_name: str, entity_type: str = "", date_from: str = "", date_to: str = "") -> list[dict]:
    """Trajetória completa de uma entidade no portal Gov.BR."""
    return trace_entity_prompt(entity_name, entity_type, date_from, date_to)


@mcp.prompt()
def prompt_weekly_digest() -> list[dict]:
    """Boletim semanal do governo federal em linguagem acessível para o cidadão."""
    return weekly_digest_prompt()


def main():
    import os

    logger.info("Iniciando Gobus MCP Server...")
    logger.info("GraphQL endpoint: %s", settings.graphql_url)

    # Cloud Run injeta PORT=8080 → SSE em /sse. max_instance_count=1 no Terraform
    # é obrigatório para SSE (sessão com estado). Sem PORT → stdio (Claude Desktop).
    port = int(os.environ.get("PORT", 0))
    transport = "sse" if port else "stdio"

    try:
        if transport == "stdio":
            logger.info("Transport: stdio (modo local)")
            mcp.run()
        else:
            effective_port = port or 8080
            logger.info("Transport: %s em 0.0.0.0:%d", transport, effective_port)
            mcp.run(transport=transport, host="0.0.0.0", port=effective_port)
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error("Erro no servidor: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()
