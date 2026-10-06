import logging
from dataclasses import dataclass, field

from fastmcp import FastMCP
from fastmcp.server.http import Mount, Request, Response, SseServerTransport
from fastmcp.tools import ToolResult

from gobus_mcp.agency_activity import AgencyActivityService
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.config import settings
from gobus_mcp.prompts.draft_press_release import draft_press_release_prompt
from gobus_mcp.prompts.monitor_agency import monitor_agency_prompt
from gobus_mcp.prompts.trace_entity import trace_entity_prompt
from gobus_mcp.prompts.weekly_digest import weekly_digest_prompt
from gobus_mcp.resources.agencies import fetch_agencies
from gobus_mcp.resources.health_pipelines import fetch_health_pipelines
from gobus_mcp.resources.platform_stats import fetch_platform_stats
from gobus_mcp.resources.readability_report import fetch_readability_report
from gobus_mcp.resources.taxonomy_queries import fetch_taxonomy_queries
from gobus_mcp.resources.themes import fetch_themes
from gobus_mcp.tools.detect_anomalies import detect_anomalies
from gobus_mcp.tools.detect_trends import detect_trends
from gobus_mcp.tools.forecast_trends import forecast_trends
from gobus_mcp.tools.get_agency_analytics import get_agency_analytics
from gobus_mcp.tools.get_agency_summary import get_agency_summary
from gobus_mcp.tools.get_article import get_article
from gobus_mcp.tools.get_entity_network import get_entity_network
from gobus_mcp.tools.get_entity_profile import get_entity_profile
from gobus_mcp.tools.get_policy_lifecycle import get_policy_lifecycle
from gobus_mcp.tools.get_readability_recommendations import build_readability_payload
from gobus_mcp.tools.resolve_entity import resolve_entity
from gobus_mcp.tools.score_article import score_article
from gobus_mcp.tools.search_news import search_news
from gobus_mcp.ui import app_result, app_tool_kwargs, register_ui_resources

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
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )
    return Response()


mcp._additional_http_routes.append(
    Mount("/messages", app=_sse.handle_post_message)
)  # Starlette redireciona /messages → /messages/ sem trailing slash

# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Deps:
    """Dependências compartilhadas pelas tools e resources.

    Um único contêiner por processo; os testes trocam ``server._deps`` (monkeypatch) e
    tudo que é lido via ``get_deps()`` passa a usar o fake.

    - ``activity``: snapshot de atividade das agências (cache de 6 h), usado por
      anomalias, forecast e health; criado a partir de ``client``/``catalog`` se omitido;
    - ``cache``: cache das tools do G2 (ranges de tema 5 min, ranking 10 min, contexto de
      entidade 30 min).
    """

    client: GobusGraphQLClient
    catalog: AgencyCatalog
    activity: AgencyActivityService | None = None
    cache: TTLCache = field(default_factory=TTLCache)

    def __post_init__(self) -> None:
        if self.activity is None:
            self.activity = AgencyActivityService(self.client, self.catalog)


def _build_deps() -> Deps:
    client = GobusGraphQLClient(
        url=settings.graphql_url,
        api_key=settings.graphql_api_key,
        timeout=settings.request_timeout,
    )
    catalog = AgencyCatalog(client)
    return Deps(client=client, catalog=catalog, activity=AgencyActivityService(client, catalog))


_deps = _build_deps()


def get_deps() -> Deps:
    """Contêiner de dependências corrente (lido a cada chamada)."""
    return _deps


# ── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
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
    return await search_news(
        query,
        get_deps().client,
        agency_key or None,
        page,
        limit,
        date_from or None,
        date_to or None,
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
async def gobus_get_article(unique_id: str) -> str:
    """Retorna conteúdo completo de um artigo pelo seu unique_id.

    Parâmetros:
    - unique_id: ID único do artigo (obtido via gobus_search_news)

    Retorna: Markdown com título, agência, data, corpo completo e metadados.

    Restrições: Não use para descoberta — primeiro busque com gobus_search_news,
    depois use este tool para ler os artigos de interesse.
    """
    deps = get_deps()
    return await get_article(unique_id, deps.client, catalog=deps.catalog)


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
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
    return await resolve_entity(query, get_deps().client, entity_type or None, limit)


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
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
        entity_name,
        get_deps().client,
        entity_type or None,
        date_from or None,
        date_to or None,
        summary_only,
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
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
    return await get_entity_network(
        entity_id, get_deps().client, depth, limit, max_nodes, node_types or ""
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
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
    - date_to: Data de fim ISO, inclusiva em toda granularidade (ex: "2024-12-31")
    - granularity: Agrupamento temporal — "DAY", "WEEK" ou "MONTH" (default "MONTH")

    Retorna: Markdown com métricas por período: artigos publicados, sentimento médio,
    % positivo e índice de legibilidade Flesch (faixa única 0/25/50/75, limitado a 0–100).
    Métrica sem dado aparece como "indisponível" (nunca 0), com aviso no topo.

    Dica de paralelismo: Execute em paralelo com gobus_search_news para a mesma agência.
    Para overview rápido sem granularidade, prefira gobus_get_agency_summary.
    """
    deps = get_deps()
    return await get_agency_analytics(
        agencies, date_from, date_to, deps.client, granularity, catalog=deps.catalog
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
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
    - baseline_days: Período de REFERÊNCIA em dias (default 28 — "último mês"); deve ser
      maior que window_days
    - min_articles: Mínimo de artigos na janela recente para considerar (default 3)
    - growth_threshold: Razão mínima de crescimento sem sobreposição, ex: 1.5 = 50% a mais
      por dia que nos dias anteriores do baseline (default 1.5; mínimo 1.0)
    - agency_key: Filtrar por agência específica (opcional) — ver gobus://agencies
    - limit: Máximo de temas retornados (default 10)

    Retorna: Markdown com temas em alta, a razão sem sobreposição (artigos/dia na janela
    ÷ artigos/dia nos dias anteriores do baseline), o growthScore da API (cujo baseline
    inclui a janela) e artigos representativos. Se a classificação de temas não cobre a
    janela, avisa "Temas: indisponível" em vez de dizer que nada cresceu.

    Dica: Use gobus://taxonomy-queries para mapear temas detectados a termos de busca.
    Para cada tema, execute gobus_search_news em paralelo com o nome do tema.
    """
    deps = get_deps()
    return await detect_trends(
        deps.client,
        window_days,
        baseline_days,
        min_articles,
        growth_threshold,
        agency_key or None,
        limit,
        catalog=deps.catalog,
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
async def gobus_get_agency_summary(agency_key: str, days: int = 30) -> str:
    """Resumo executivo de uma agência: volume + métricas + temas em alta em uma única chamada.

    Combina gobus_get_agency_analytics + gobus_detect_trends (filtrado para a agência).
    Use quando precisar de overview rápido sem granularidade detalhada.

    Parâmetros:
    - agency_key: chave da agência (ex: "saude", "mec") — ver gobus://agencies
    - days: janela em dias (default 30)

    Retorna: Markdown com volume total de artigos, índice de legibilidade, sentimento
    e temas em alta (razão ≥ 1.5× sem sobreposição, últimos 7 dias) com artigos
    representativos. Métrica sem dado aparece como "indisponível" (nunca 0). Chave de
    agência inválida devolve sugestões (ex: "trabalho" → "trabalho-e-emprego").

    Restrições: Não substitui gobus_get_agency_analytics quando precisar de
    granularidade por dia/semana ou comparar múltiplas agências.
    """
    deps = get_deps()
    return await get_agency_summary(agency_key, deps.client, days, catalog=deps.catalog)


@mcp.tool(**app_tool_kwargs("readability_dashboard"))
async def gobus_get_readability_recommendations(
    agency_key: str = "",
    days: int = 90,
    limit: int = 10,
    date_to: str = "",
) -> ToolResult:
    """Diagnóstico de legibilidade (índice Flesch) por agência com recomendações de estilo.

    Parâmetros:
    - agency_key: Chave da agência (ex: "saude", "defesa") — se vazio, retorna o ranking
      das agências ativas. Chave inválida devolve sugestões (ex: "ms" → "saude").
    - days: Tamanho da janela de análise em dias (default 90)
    - limit: Máximo de agências no ranking geral (default 10)
    - date_to: Último dia da janela, ISO (ex: "2026-06-30") — opcional; o padrão é ontem

    Retorna: Ranking por Flesch com gap até a meta (≥50 para serviço ao cidadão, ≥30 para
    institucional) ou, com agency_key, o diagnóstico da agência: média, benchmark da
    Agência Brasil calculado na mesma janela, pior e melhor artigo de uma amostra e 3
    recomendações de estilo.

    Dados: agência sem Flesch aparece como "sem dado" (nunca 0.0). Se o cálculo do Flesch
    parou antes do fim da janela, a análise usa a janela efetiva (mesmo tamanho, até o
    último mês com dado) e avisa "dados até MM/AAAA". Escala: fórmula inglesa do textstat,
    limitada a 0–100.

    MCP App: em hosts com suporte (Claude Desktop, claude.ai) abre o painel
    ui://readability-dashboard; o texto devolvido é o mesmo resumo em Markdown.
    """
    deps = get_deps()
    report = await build_readability_payload(
        deps.client,
        agency_key=agency_key or None,
        days=days,
        limit=limit,
        date_to=date_to or None,
        catalog=deps.catalog,
    )
    return app_result(report)


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
async def gobus_get_policy_lifecycle(
    policy_name: str,
    date_from: str = "2024-01-01",
) -> str:
    """Ciclo de vida comunicacional de uma política pública no portal Gov.BR.

    Analisa a série mensal de cobertura (somando as agências de cada mês; meses sem
    artigos, até o mês corrente, entram com 0) para identificar fases: ANNOUNCED (mês de
    pico), IMPLEMENTATION (≥40% do pico) e ROUTINE (abaixo disso). A fase atual é a do
    último mês fechado; o mês corrente aparece como parcial, fora da classificação, e
    há aviso quando a cobertura parou. Identifica as agências dominantes por mês e por
    fase (âncoras narrativos) e apresenta artigos publicados no mês de pico.

    Parâmetros:
    - policy_name: Nome ou alias da política (ex: "Pé-de-Meia", "Bolsa Família")
    - date_from: Data de início da série temporal ISO (ex: "2023-01-01") — default "2024-01-01"

    Retorna: Markdown com fases identificadas, âncoras narrativos por fase,
    perspectiva da fase atual e artigos representativos do pico de cobertura.

    Dica: Use gobus_resolve_entity com entity_type="POLICY" para descobrir o
    nome canônico antes de chamar este tool.
    """
    return await get_policy_lifecycle(policy_name, get_deps().client, date_from)


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
async def gobus_detect_anomalies(sensitivity: str = "medium", domain_filter: str = "") -> str:
    """Detecta anomalias comunicacionais de temas e de entidades, ciente do defeso eleitoral.

    Temas (janelas móveis de 3 e 7 dias, UTC): share-of-voice — a fatia do tema entre os
    artigos classificados contra o baseline anterior (21 e 28 dias) — com pico ou queda
    sustentados só quando as duas janelas passam do limiar. Se a classificação de temas
    não cobre as janelas, o bloco fica "indisponível" (nunca "nada mudou").

    Entidades (janela fechada de 7 dias até ontem 23:59 BRT, contra 28 dias de baseline;
    na recuperação pós-defeso, os 28 dias antes do defeso): candidatos do ranking em alta
    recalculados pela cobertura diária (entityCoverage), sem republicadoras. Classes, em
    ordem de precedência: rajada (≥80% num dia), entidade nova (sem baseline), explicado
    pelo calendário (dona calada no defeso ou janela dominada por agências retomadas),
    silêncio coordenado (outras agências sobem e a agência dona some), cobertura
    concentrada (poucas agências) e normal. O volumeRatio do upstream nunca é usado como
    sinal.

    Parâmetros:
    - sensitivity: "high" (mais sinais) | "medium" (padrão) | "low" (só sinais fortes)
    - domain_filter: domínio de política — HEALTH, EDUCATION, SOCIAL, ECONOMIC, SECURITY,
      ENVIRONMENT, GOVERNANCE ou OTHER (aceita em português: saude, educacao, social,
      economia, seguranca, meio_ambiente, governanca, outros). Vazio = todos. Valor
      inválido devolve as opções.

    Retorna: Markdown com o cabeçalho das janelas, o calendário (defeso eleitoral até
    25/10/2026, recuperação até 29/11), avisos de dados e as seções Picos Sustentados,
    Quedas Sustentadas, Silêncio Coordenado, Cobertura Concentrada, Explicado pelo
    Calendário, Rajadas e Entidades Novas e Tendências Normais, com severidade 0–1,
    faixa (normal/atenção/alerta) e confiança.
    """
    deps = get_deps()
    return await detect_anomalies(
        deps.client,
        sensitivity,
        domain_filter,
        catalog=deps.catalog,
        activity=deps.activity,
        cache=deps.cache,
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
async def gobus_forecast_trends(horizon_days: int = 21, limit: int = 5) -> str:
    """Projeta tendências de temas por share-of-voice em três janelas (3, 7 e 21 dias).

    Para cada tema: razão da fatia entre os artigos classificados na janela contra o
    baseline anterior a ela (14, 28 e 84 dias), taxa log por dia, ritmo composto (pesos
    0,5/0,3/0,2 renormalizados nas janelas com cobertura de classificação), momentum
    (acelerando, desacelerando, estável ou indeterminado) e confiança (cai um nível na
    recuperação pós-defeso). A projeção é amortecida e usa o perfil de dia útil (feriado
    conta como domingo) e o nível de volume da fase do calendário em cada dia.

    Parâmetros:
    - horizon_days: horizonte efetivo da projeção, 1–28 dias (default 21; fora disso é
      ajustado, com aviso)
    - limit: máximo de temas, 1–10, ordenados pelo ritmo composto (default 5)

    Retorna: Markdown com a tabela Tema | Ritmo (×/semana) | Momentum | Confiança |
    Artigos esperados no horizonte (intervalo de 95%) | Razão por janela, mais os avisos
    de cobertura de classificação e de calendário.
    """
    deps = get_deps()
    return await forecast_trends(
        deps.client,
        horizon_days,
        limit,
        catalog=deps.catalog,
        activity=deps.activity,
        cache=deps.cache,
    )


@mcp.tool(output_schema=None, annotations={"readOnlyHint": True})
async def gobus_score_article(unique_id: str) -> str:
    """Atribui uma nota editorial (0-10) a um artigo comparando-o ao benchmark da agência.

    Combina legibilidade (Flesch limitado a 0–100), concisão (palavras contra a mediana
    da agência) e densidade de entidades (por 100 palavras) numa nota ponderada 50/30/20.

    O benchmark é calculado a cada chamada: amostra de artigos da agência e da Agência
    Brasil nos 90 dias antes da publicação do artigo, com medianas (null com menos de 10
    artigos).

    Estados: "scored" (3 dimensões); "parcial" (sem benchmark de concisão, nota
    renormalizada); "Nota indisponível" quando o artigo não tem Flesch ou contagem de
    palavras — nunca uma nota neutra inventada.

    Parâmetros:
    - unique_id: ID único do artigo (obtido via gobus_search_news)

    Retorna: Markdown com nota geral, notas por dimensão e benchmark da agência.
    """
    deps = get_deps()
    return await score_article(unique_id, deps.client, catalog=deps.catalog)


# ── Resources ────────────────────────────────────────────────────────────────


@mcp.resource("gobus://agencies")
async def agencies_resource() -> str:
    """Lista completa de agências governamentais: nome, código e republicadoras."""
    deps = get_deps()
    return await fetch_agencies(deps.client, catalog=deps.catalog)


@mcp.resource("gobus://themes")
async def themes_resource() -> str:
    """Taxonomia completa de temas do portal Gov.BR."""
    return await fetch_themes(get_deps().client)


@mcp.resource("gobus://platform-stats")
async def platform_stats_resource() -> str:
    """Estatísticas gerais da plataforma (últimos 30 dias)."""
    return await fetch_platform_stats(get_deps().client)


@mcp.resource("gobus://taxonomy-queries")
async def taxonomy_queries_resource() -> str:
    """Mapeamento de categorias do detect_trends para termos de busca efetivos."""
    return await fetch_taxonomy_queries()


@mcp.resource("gobus://readability-report", mime_type="application/json")
async def readability_report_resource() -> str:
    """Relatório JSON de legibilidade das agências ativas, com gap até a meta (Flesch 50),
    janela efetiva e cobertura (sem dado → null, nunca 0)."""
    deps = get_deps()
    return await fetch_readability_report(deps.client, catalog=deps.catalog)


@mcp.resource("gobus://health/pipelines", mime_type="application/json")
async def health_pipelines_resource() -> str:
    """Saúde das fontes de dados (JSON): temas, legibilidade, sentimento, ranking de
    entidades, atraso de indexação e atividade das agências (silenciadas e retomadas),
    cada uma ok | degraded | unavailable, com avisos."""
    deps = get_deps()
    return await fetch_health_pipelines(deps.client, catalog=deps.catalog, activity=deps.activity)


# MCP Apps: um resource ui:// por app (HTML estático, sem I/O; os dados vêm da tool).
register_ui_resources(mcp)


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
def prompt_trace_entity(
    entity_name: str, entity_type: str = "", date_from: str = "", date_to: str = ""
) -> list[dict]:
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
