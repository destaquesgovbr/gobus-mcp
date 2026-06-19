import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.config import settings
from gobus_mcp.tools.search_news import search_news
from gobus_mcp.tools.get_article import get_article
from gobus_mcp.tools.resolve_entity import resolve_entity
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_agency_analytics import get_agency_analytics
from gobus_mcp.tools.detect_trends import detect_trends
from gobus_mcp.resources.agencies import fetch_agencies
from gobus_mcp.resources.themes import fetch_themes
from gobus_mcp.resources.platform_stats import fetch_platform_stats
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
    page: int = 1,
    limit: int = 10,
) -> str:
    """Busca notícias no portal Gov.BR por texto livre e/ou agência."""
    return await search_news(query, _client, agency_key or None, page, limit)


@mcp.tool()
async def gobus_get_article(unique_id: str) -> str:
    """Retorna conteúdo completo de um artigo pelo seu ID único."""
    return await get_article(unique_id, _client)


@mcp.tool()
async def gobus_resolve_entity(query: str, entity_type: str = "", limit: int = 5) -> str:
    """Resolve nome de entidade para ID canônico (ORG, PER, LOC, EVENT, POLICY, LAW)."""
    return await resolve_entity(query, _client, entity_type or None, limit)


@mcp.tool()
async def gobus_get_entity_profile(
    entity_name: str,
    entity_type: str = "",
    date_from: str = "",
    date_to: str = "",
) -> str:
    """Perfil completo de entidade: cobertura temporal + entidades relacionadas."""
    return await get_entity_profile(entity_name, _client, entity_type or None, date_from or None, date_to or None)


@mcp.tool()
async def gobus_get_entity_network(entity_id: str, depth: int = 1, limit: int = 50) -> str:
    """Rede de co-menções ao redor de uma entidade (depth 1 ou 2)."""
    return await get_entity_network(entity_id, _client, depth, limit)


@mcp.tool()
async def gobus_get_agency_analytics(
    agencies: list[str],
    date_from: str,
    date_to: str,
    granularity: str = "MONTH",
) -> str:
    """Métricas de publicação (volume, sentimento, legibilidade) por agência e período."""
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
    """Detecta temas em crescimento comparando janela recente com baseline histórico."""
    return await detect_trends(_client, window_days, baseline_days, min_articles, growth_threshold, agency_key or None, limit)


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

    # Cloud Run injeta PORT; presença indica modo HTTP (SSE).
    # Localmente (stdio para Claude Desktop/Code) PORT não está setado.
    port = int(os.environ.get("PORT", 0))
    transport = os.environ.get("MCP_TRANSPORT", "sse" if port else "stdio")

    try:
        if transport == "stdio":
            logger.info("Transport: stdio (modo local)")
            mcp.run()
        else:
            host = "0.0.0.0"
            port = port or 8080
            logger.info("Transport: %s em %s:%d", transport, host, port)
            mcp.run(transport=transport, host=host, port=port)
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error("Erro no servidor: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()
