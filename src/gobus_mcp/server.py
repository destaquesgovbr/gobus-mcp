import logging

from fastmcp import FastMCP
from fastmcp.server.http import Mount, Request, Response, SseServerTransport

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
from gobus_mcp.tools.get_readability_recommendations import get_readability_recommendations
from gobus_mcp.tools.get_policy_lifecycle import get_policy_lifecycle
from gobus_mcp.tools.detect_anomalies import detect_anomalies
from gobus_mcp.tools.forecast_trends import forecast_trends
from gobus_mcp.tools.score_article import score_article
from gobus_mcp.resources.agencies import fetch_agencies
from gobus_mcp.resources.readability_dashboard import fetch_readability_dashboard
from gobus_mcp.resources.readability_report import fetch_readability_report
from gobus_mcp.resources.health_pipelines import fetch_health_pipelines
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

# ── Backward-compat SSE (spec 2024-11-05) ────────────────────────────────────
# O endpoint primário é /mcp (stateless, spec 2025-03-26) sem expiração de sessão.
# /sse + /messages ficam disponíveis para clientes que ainda usam o protocolo antigo.
_sse = SseServerTransport("/messages/")


@mcp.custom_route("/sse", methods=["GET"])
async def _sse_compat(request: Request) -> Response:
    async with _sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp._mcp_server.run(
            streams[0], streams[1],
            mcp._mcp_server.create_initialization_options(),
        )
    return Response()


mcp._additional_http_routes.append(Mount("/messages", app=_sse.handle_post_message))  # Starlette redireciona /messages → /messages/ sem trailing slash

# ─────────────────────────────────────────────────────────────────────────────

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


@mcp.tool()
async def gobus_get_readability_recommendations(
    agency_key: str = "",
    days: int = 90,
    limit: int = 10,
) -> str:
    """Diagnóstico de legibilidade por agência com recomendações de estilo.

    Parâmetros:
    - agency_key: Chave da agência (ex: "cgu", "defesa") — se vazio, retorna ranking geral
    - days: Janela de análise em dias (default 90)
    - limit: Máximo de agências no ranking geral (default 10)

    Retorna: Ranking de agências por Flesch × volume com gap vs meta (≥50 para serviço,
    ≥30 para institucional) e 3 recomendações de estilo priorizadas. A Agência Brasil
    (Flesch ~33) é o benchmark interno — nenhuma outra agência a supera hoje.
    """
    return await get_readability_recommendations(agency_key or None, _client, days, limit)


@mcp.tool()
async def gobus_get_policy_lifecycle(
    policy_name: str,
    date_from: str = "2024-01-01",
) -> str:
    """Ciclo de vida comunicacional de uma política pública no portal Gov.BR.

    Analisa a série temporal de cobertura mensal para identificar fases:
    ANNOUNCED (pico de lançamento), IMPLEMENTATION (sustentação), ROUTINE (queda).
    Identifica as agências dominantes por fase (âncoras narrativos) e apresenta
    artigos representativos do período de maior cobertura.

    Parâmetros:
    - policy_name: Nome ou alias da política (ex: "Pé-de-Meia", "Bolsa Família")
    - date_from: Data de início da série temporal ISO (ex: "2023-01-01") — default "2024-01-01"

    Retorna: Markdown com fases identificadas, âncoras narrativos por fase,
    perspectiva da fase atual e artigos representativos do pico de cobertura.

    Dica: Use gobus_resolve_entity com entity_type="POLICY" para descobrir o
    nome canônico antes de chamar este tool.
    """
    return await get_policy_lifecycle(policy_name, _client, date_from)


@mcp.tool()
async def gobus_detect_anomalies(sensitivity: str = "medium") -> str:
    """Detecta anomalias comunicacionais: picos sustentados e cobertura concentrada.

    Cruza duas janelas de detecção de temas (3d/21d e 7d/28d) para achar picos
    sustentados e inspeciona entidades em alta para achar "silêncio concentrado" —
    assuntos com alto volume relativo cobertos por poucas agências.

    Parâmetros:
    - sensitivity: "high" | "medium" | "low" — quão sensível é o detector de
      concentração (high = mais alertas, low = só os casos mais extremos)

    Retorna: Markdown com picos sustentados, cobertura concentrada e tendências normais.
    """
    return await detect_anomalies(_client, sensitivity)


@mcp.tool()
async def gobus_forecast_trends(horizon_days: int = 21, limit: int = 5) -> str:
    """Projeta tendências combinando três janelas de detecção de temas (3d, 7d, 21d).

    Cada tema recebe um score composto (média ponderada por janela), leitura de
    momentum (acelerando/desacelerando/estável) e confiança conforme o número de
    janelas em que aparece.

    Parâmetros:
    - horizon_days: Horizonte da projeção em dias (informativo — default 21)
    - limit: Máximo de temas retornados, ordenados por score composto (default 5)

    Retorna: Markdown com tabela Tema | Score Composto | Momentum | Confiança.
    Atenção: a janela de 3 dias sofre viés de borda de fim de semana.
    """
    return await forecast_trends(_client, horizon_days, limit)


@mcp.tool()
async def gobus_score_article(unique_id: str) -> str:
    """Atribui uma nota editorial (0-10) a um artigo comparando-o ao benchmark da agência.

    Combina legibilidade (Flesch), concisão (tamanho vs. média da agência) e
    densidade de entidades numa nota ponderada (50/30/20).

    Parâmetros:
    - unique_id: ID único do artigo (obtido via gobus_search_news)

    Retorna: Markdown com nota geral, notas por dimensão e benchmark da agência.
    """
    return await score_article(unique_id, _client)


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


@mcp.resource("ui://readability-dashboard")
async def readability_dashboard_resource() -> str:
    """Dashboard interativo de legibilidade por agência (HTML/JS auto-contido)."""
    return await fetch_readability_dashboard(_client)


@mcp.resource("gobus://readability-report")
async def readability_report_resource() -> str:
    """Relatório JSON de legibilidade por agência com gap até a meta (Flesch 50)."""
    return await fetch_readability_report(_client)


@mcp.resource("gobus://health/pipelines")
async def health_pipelines_resource() -> str:
    """Health-check dos pipelines de dados (trendingScore, sentimento, legibilidade)."""
    return await fetch_health_pipelines(_client)


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

    # Cloud Run injeta PORT=8080 → HTTP stateless em /mcp (spec 2025-03-26).
    # /sse + /messages ficam disponíveis para backwards-compat (spec 2024-11-05).
    # Sem PORT → stdio (Claude Desktop / desenvolvimento local).
    port = int(os.environ.get("PORT", 0))

    try:
        if not port:
            logger.info("Transport: stdio (modo local)")
            mcp.run()
        else:
            logger.info(
                "Transport: http stateless em 0.0.0.0:%d — /mcp (2025-03-26) + /sse (2024-11-05)",
                port,
            )
            mcp.run(transport="http", host="0.0.0.0", port=port, stateless_http=True)
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error("Erro no servidor: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()
