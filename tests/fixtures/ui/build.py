"""Fixtures JSON dos MCP Apps (``tests/fixtures/ui/<app>/<estado>.json``). DEV — dados fictícios.

Cada fixture é o que um host entrega ao app:
``{app, state, description, toolName, toolInput, result, toolCalls}``, com ``result`` no
formato ``CallToolResult`` (``content``, ``structuredContent``, ``isError``) e ``toolCalls``
= respostas para os ``tools/call`` que o app faz nas interações (o mini-host casa por
nome e argumentos).

Os payloads saem dos **builders reais** (``build_*_payload`` + ``ui.app_result``) com um
``FakeGraphQLClient`` e relógio fixo, então valem o contrato pydantic por construção. São
compartilhadas pelo pytest de contrato (``tests/test_ui/test_fixtures_contract.py``, que
confere que os arquivos estão em dia), pelo mini-host Playwright (``tests/browser``) e,
mais tarde, pelas tools de preview dev.

Regerar depois de mudar builder, render ou payload::

    PYTHONPATH=src .venv/bin/python3.12 -m tests.fixtures.ui.build
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path

from gobus_mcp import ui
from gobus_mcp.calendario import BRT
from gobus_mcp.client import GobusGraphQLError
from gobus_mcp.readability import period_range
from gobus_mcp.tools.get_readability_recommendations import build_readability_payload
from gobus_mcp.tools.score_article import build_score_payload
from tests.conftest import CATALOG_AGENCIES, FakeGraphQLClient, route_catalog
from tests.fixtures.g2 import (
    ACTIVITY_0510,
    NOW_0510,
    many_candidates,
    ranges_from_daily,
    route_g2,
    scenario_0510,
    theme_ranges_0510,
    trending_rows_0510,
)

FIXTURES_DIR = Path(__file__).parent
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=BRT)
DEV_NOTE = "DEV — dados fictícios"

XSS_IMG = "<img src=x onerror=alert(1)>"
XSS_SCRIPT = "</script><script>alert(2)</script>"


def call_result(result) -> dict:
    """``ToolResult`` → ``CallToolResult`` como o host repassa ao app."""
    return {
        "content": [block.model_dump(mode="json", exclude_none=True) for block in result.content],
        "structuredContent": result.structured_content,
        "isError": bool(result.is_error),
    }


# ── readability ─────────────────────────────────────────────────────────────

# Catálogo do conftest + 2 agências: 10 com Flesch (o card inline mostra só o top-8).
READABILITY_AGENCIES: list[tuple[str, bool, str]] = [
    *CATALOG_AGENCIES,
    ("mma", False, "Ministério do Meio Ambiente e Mudança do Clima"),
    ("mcti", False, "Ministério da Ciência, Tecnologia e Inovação"),
]
# (agência, mês) → (artigos, Flesch bruto | None, palavras | None). Abr–jun com dado.
READABILITY_MONTHS = ("2026-04", "2026-05", "2026-06")
READABILITY_BASE: dict[str, tuple[int, float | None, float | None]] = {
    "agencia_brasil": (310, 33.6, 434.0),
    "saude": (95, 13.7, 682.0),
    "mec": (60, 28.4, 590.0),
    "secom": (52, 41.2, 512.0),
    "cgu": (40, -1.2, 620.0),
    "defesa": (66, -22.9, 800.0),
    "pf": (48, 52.3, 380.0),
    "trabalho-e-emprego": (35, 38.9, 540.0),
    "mma": (28, 24.5, 610.0),
    "mcti": (26, 19.8, 655.0),
    "mds": (30, None, None),
    "tvbrasil": (25, None, None),
}


def readability_rows(
    base: dict[str, tuple[int, float | None, float | None]],
    months: tuple[str, ...] = READABILITY_MONTHS,
    *,
    names: dict[str, str] | None = None,
) -> list[dict]:
    names = names or {code: name for code, _, name in READABILITY_AGENCIES}
    rows = []
    for i, month in enumerate(months):
        for code, (count, flesch, words) in base.items():
            drift = (i - 1) * 1.5  # mês a mês, para o histórico não ser constante
            rows.append(
                {
                    "period": f"{month}-01 00:00:00+00",
                    "agencyKey": code,
                    "agencyName": names.get(code, code),
                    "articleCount": count + 3 * i,
                    "avgReadabilityFlesch": None if flesch is None else round(flesch + drift, 1),
                    "avgWordCount": words,
                }
            )
    return rows


def route_readability(
    client: FakeGraphQLClient,
    rows: list[dict],
    *,
    agencies: list[tuple[str, bool, str]] | None = None,
    articles: list[dict] | None = None,
) -> FakeGraphQLClient:
    """Rotas do ``build_readability_payload``: catálogo, ``ReadabilityWindow`` (MONTH,
    ``dateTo`` exclusivo) e ``ReadabilityArticles`` (amostra do modo agência)."""
    route_catalog(client, READABILITY_AGENCIES if agencies is None else agencies)

    def window(variables: dict) -> dict:
        start = date.fromisoformat(variables["dateFrom"])
        stop = date.fromisoformat(variables["dateTo"])  # exclusivo
        out = []
        for row in rows:
            if row["agencyKey"] not in variables["agencies"]:
                continue
            month = period_range(row["period"], "MONTH")
            if month.start < stop and month.end >= start:
                out.append(row)
        return {"agencyAnalytics": out}

    client.route("ReadabilityWindow", window)
    sample = articles if articles is not None else []
    client.route("ReadabilityArticles", {"articles": {"found": len(sample), "articles": sample}})
    return client


def readability_articles(code: str = "saude") -> list[dict]:
    titles = [
        ("Ministério amplia vacinação contra a gripe para todas as idades", 42.6, 454),
        ("Portaria regulamenta repasses do fundo nacional aos municípios", -8.3, 958),
        ("Campanha orienta sobre prevenção à dengue no verão", 31.0, 520),
        ("Novo protocolo clínico para tratamento de hipertensão", 5.4, 870),
        ("Unidades de saúde ampliam horário de atendimento", 38.2, 410),
        ("Programa leva especialistas a regiões remotas", 22.1, 640),
        ("Balanço do primeiro semestre da atenção primária", None, 700),
    ]
    return [
        {
            "uniqueId": f"{code}-artigo-{i}",
            "title": title,
            "url": f"https://www.gov.br/{code}/pt-br/assuntos/noticias/2026/06/artigo-{i}",
            "publishedAt": f"2026-06-{28 - i:02d}T13:00:00+00:00",
            "features": {"readabilityFlesch": flesch, "wordCount": words},
        }
        for i, (title, flesch, words) in enumerate(titles)
    ]


async def _readability(client: FakeGraphQLClient, **kwargs) -> dict:
    report = await build_readability_payload(client, now=NOW, **kwargs)
    return call_result(ui.app_result(report))


def readability_args(**kwargs) -> dict:
    """Argumentos que o app manda no ``tools/call`` (mesma regra do JS: ``days`` e
    ``limit`` sempre; ``date_to``/``agency_key`` só quando definidos)."""
    args = {"days": kwargs.pop("days", 90), "limit": kwargs.pop("limit", 10)}
    args.update({k: v for k, v in kwargs.items() if v})
    return args


async def readability_fixtures() -> dict[str, dict]:
    tool = "gobus_get_readability_recommendations"
    rows = readability_rows(READABILITY_BASE)

    def fresh(rows_=rows, **kw) -> FakeGraphQLClient:
        return route_readability(FakeGraphQLClient(), rows_, **kw)

    ok_args = readability_args(date_to="2026-06-30")
    detail_args = readability_args(date_to="2026-06-30", agency_key="saude")
    ok = await _readability(fresh(), days=90, date_to="2026-06-30")
    detail = await _readability(
        fresh(articles=readability_articles()),
        agency_key="saude",
        days=90,
        date_to="2026-06-30",
    )
    shifted = await _readability(fresh(), days=90)
    nothing = [{**r, "avgReadabilityFlesch": None, "avgWordCount": None} for r in rows]
    unavailable = await _readability(fresh(nothing), days=90)
    error = await _readability(fresh(), agency_key="tcu", days=90)

    xss_agencies = [
        ("agencia_brasil", True, "Agência Brasil"),
        ("xss-img", False, XSS_IMG),
        ("xss-script", False, XSS_SCRIPT),
    ]
    xss_names = {code: name for code, _, name in xss_agencies}
    xss_rows = readability_rows(
        {
            "agencia_brasil": (300, 33.6, 434.0),
            "xss-img": (40, 27.0, 500.0),
            "xss-script": (30, 12.0, 610.0),
        },
        names=xss_names,
    )
    xss = await _readability(
        route_readability(FakeGraphQLClient(), xss_rows, agencies=xss_agencies),
        days=90,
        date_to="2026-06-30",
    )

    def fixture(state, description, tool_input, result, tool_calls=()):
        return {
            "app": "readability_dashboard",
            "state": state,
            "description": f"{DEV_NOTE}: {description}",
            "toolName": tool,
            "toolInput": tool_input,
            "result": result,
            "toolCalls": [
                {"name": tool, "arguments": args, "result": res} for args, res in tool_calls
            ],
        }

    return {
        "ok": fixture(
            "ok",
            "ranking de 12 agências (abr–jun/2026), 2 sem Flesch; clique em saude abre o detalhe",
            ok_args,
            ok,
            [(detail_args, detail)],
        ),
        "agency_detail": fixture(
            "agency_detail",
            "diagnóstico do Ministério da Saúde com pior/melhor artigo e benchmark",
            detail_args,
            detail,
        ),
        "shifted": fixture(
            "shifted",
            "janela pedida (jul–out) sem Flesch: janela efetiva até 06/2026",
            readability_args(),
            shifted,
            [(ok_args, ok)],
        ),
        "unavailable": fixture(
            "unavailable", "nenhum Flesch no histórico consultado", readability_args(), unavailable
        ),
        "error": fixture(
            "error",
            "agência fora do catálogo (tcu)",
            readability_args(agency_key="tcu"),
            error,
        ),
        "xss": fixture("xss", "nomes de agência com HTML e </script>", ok_args, xss),
    }


# ── scorecard ───────────────────────────────────────────────────────────────

SCORE_ARTICLES: dict[str, dict] = {
    "pf-operacao-desarticula-quadrilha": {
        "title": "Operação desarticula quadrilha que fraudava benefícios",
        "agency": "pf",
        "agencyName": "pf",
        "publishedAt": "2026-06-10T13:00:00+00:00",
        "flesch": 48.2,
        "wordCount": 420,
        "entities": 6,
    },
    "pf-balanco-semestral": {
        "title": "PF divulga balanço das operações do semestre",
        "agency": "pf",
        "agencyName": "pf",
        "publishedAt": "2026-06-20T15:00:00+00:00",
        "flesch": 12.4,
        "wordCount": 980,
        "entities": 3,
    },
    "saude-campanha-gripe": {
        "title": "Campanha de vacinação contra a gripe começa na segunda",
        "agency": "saude",
        "agencyName": "saude",
        "publishedAt": "2026-06-05T12:00:00+00:00",
        "flesch": 22.0,
        "wordCount": 700,
        "entities": 4,
    },
    "pf-operacao-outubro": {
        "title": "Operação cumpre mandados em três estados",
        "agency": "pf",
        "agencyName": "pf",
        "publishedAt": "2026-10-02T11:00:00+00:00",
        "flesch": None,
        "wordCount": None,
        "entities": 2,
    },
    "xss-artigo": {
        "title": XSS_SCRIPT + " Título " + XSS_IMG,
        "agency": "xss-img",
        "agencyName": XSS_IMG,
        "publishedAt": "2026-06-10T13:00:00+00:00",
        "flesch": 35.0,
        "wordCount": 500,
        "entities": 3,
    },
}


def score_article_node(uid: str) -> dict | None:
    art = SCORE_ARTICLES.get(uid)
    if art is None:
        return None
    return {
        "uniqueId": uid,
        "title": art["title"],
        "url": f"https://www.gov.br/{art['agency']}/pt-br/assuntos/noticias/2026/{uid}",
        "agency": art["agency"],
        "agencyName": art["agencyName"],
        "publishedAt": art["publishedAt"],
        "features": {
            "readabilityFlesch": art["flesch"],
            "wordCount": art["wordCount"],
            "entities": [{"type": "ORG"}] * art["entities"],
        },
    }


def score_sample(code: str, n: int, *, flesch0: float, words0: int, month: str = "2026-05") -> dict:
    """Amostra do benchmark: ``n`` artigos com títulos, Flesch e palavras variados."""
    articles = []
    for i in range(n):
        articles.append(
            {
                "uniqueId": f"{code}-amostra-{i:02d}",
                "title": f"Notícia {i + 1} da amostra de {code}",
                "publishedAt": f"{month}-{1 + i % 28:02d}T12:00:00+00:00",
                "features": {
                    "readabilityFlesch": round(flesch0 + (i * 7.3) % 40 - 15, 1),
                    "wordCount": words0 + (i * 37) % 300 - 120,
                },
            }
        )
    return {"found": n * 3, "articles": articles}


def route_score(
    client: FakeGraphQLClient,
    *,
    samples: dict[str, dict] | None = None,
    agencies: list[tuple[str, bool, str]] | None = None,
) -> FakeGraphQLClient:
    """Rotas do ``build_score_payload``: ``ScoreArticle`` por ``uniqueId`` e o benchmark
    (``ag`` pela agência pedida, ``ab`` da Agência Brasil)."""
    samples = samples or {}
    route_catalog(client, READABILITY_AGENCIES if agencies is None else agencies)

    def sample_of(code: str) -> dict:
        if code in samples:
            return samples[code]
        if code == "agencia_brasil":
            return score_sample(code, 60, flesch0=36.0, words0=450)
        return score_sample(code, 40, flesch0=30.0, words0=520)

    def article(variables: dict) -> dict:
        uid = variables["uniqueId"]
        node = score_article_node(uid)
        if node is None and "-amostra-" in uid:  # sugestões de comparação vêm da amostra
            code = uid.split("-amostra-")[0]
            found = next((a for a in sample_of(code)["articles"] if a["uniqueId"] == uid), None)
            if found is not None:
                node = {
                    **found,
                    "url": f"https://www.gov.br/{code}/pt-br/assuntos/noticias/2026/{uid}",
                    "agency": code,
                    "agencyName": code,
                    "features": {**found["features"], "entities": [{"type": "ORG"}] * 4},
                }
        return {"article": node}

    client.route("ScoreArticle", article)

    def benchmark(variables: dict) -> dict:
        return {"ag": sample_of(variables["agencies"][0]), "ab": sample_of("agencia_brasil")}

    client.route("ScoreArticleBenchmark", benchmark)
    return client


async def _score(client: FakeGraphQLClient, unique_id: str, compare_with: str = "") -> dict:
    report = await build_score_payload(client, unique_id, compare_with=compare_with, now=NOW)
    return call_result(ui.app_result(report))


def score_args(unique_id: str, compare_with: str = "") -> dict:
    """Argumentos do ``tools/call`` do app (``compare_with`` só quando definido)."""
    return {"unique_id": unique_id, **({"compare_with": compare_with} if compare_with else {})}


async def scorecard_fixtures() -> dict[str, dict]:
    tool = "gobus_score_article"
    main = "pf-operacao-desarticula-quadrilha"
    scored = await _score(route_score(FakeGraphQLClient()), main)
    best = scored["structuredContent"]["suggestedComparisons"][0]["uniqueId"]
    compared = await _score(route_score(FakeGraphQLClient()), main, best)
    versus = await _score(route_score(FakeGraphQLClient()), main, "saude-campanha-gripe")
    thin = {"pf": score_sample("pf", 6, flesch0=30.0, words0=520)}
    partial = await _score(route_score(FakeGraphQLClient(), samples=thin), "pf-balanco-semestral")
    refused = await _score(route_score(FakeGraphQLClient()), "pf-operacao-outubro")
    xss_agencies = [("agencia_brasil", True, "Agência Brasil"), ("xss-img", False, XSS_IMG)]
    xss = await _score(route_score(FakeGraphQLClient(), agencies=xss_agencies), "xss-artigo")

    def fixture(state, description, tool_input, result, tool_calls=()):
        return {
            "app": "article_scorecard",
            "state": state,
            "description": f"{DEV_NOTE}: {description}",
            "toolName": tool,
            "toolInput": tool_input,
            "result": result,
            "toolCalls": [
                {"name": tool, "arguments": args, "result": res} for args, res in tool_calls
            ],
        }

    return {
        "scored": fixture(
            "scored",
            "nota com as 3 dimensões e benchmark; Comparar abre o melhor da amostra da agência",
            score_args(main),
            scored,
            [(score_args(main, best), compared)],
        ),
        "compare": fixture(
            "compare",
            "dois artigos lado a lado (PF contra Ministério da Saúde)",
            score_args(main, "saude-campanha-gripe"),
            versus,
        ),
        "partial": fixture(
            "partial",
            "amostra da agência com menos de 10 artigos: concisão sem benchmark",
            score_args("pf-balanco-semestral"),
            partial,
        ),
        "refused": fixture(
            "refused",
            "artigo de outubro sem Flesch nem contagem de palavras: nota recusada",
            score_args("pf-operacao-outubro"),
            refused,
        ),
        "xss": fixture(
            "xss", "título e agência com HTML e </script>", score_args("xss-artigo"), xss
        ),
    }


# ── anomaly radar ───────────────────────────────────────────────────────────

ANOMALY_TOOL = "gobus_detect_anomalies"
RECOVERY_NOW = datetime(2026, 11, 3, 12, 0, tzinfo=BRT)


def flat_theme_ranges() -> dict[int, dict]:
    """Temas 95% classificados e estáveis: nenhum pico nem queda."""
    rates = {"Saúde": 20, "Educação": 15, "Economia e Finanças": 25, "Cultura": 6}

    def total(i: int) -> int:
        return round(sum(rates.values()) / 0.95)

    return ranges_from_daily(lambda label, i: rates[label], total, list(rates))


def xss_theme_ranges() -> dict[int, dict]:
    """Temas com HTML no rótulo: um pico e uma queda sustentados."""
    rates = {
        XSS_IMG: lambda i: 40 if i < 3 else 30 if i < 7 else 10,
        XSS_SCRIPT: lambda i: 4 if i < 3 else 8 if i < 7 else 15,
        "Economia e Finanças": lambda i: 25,
    }

    def total(i: int) -> int:
        return round(sum(f(i) for f in rates.values()) / 0.95)

    return ranges_from_daily(lambda label, i: rates[label](i), total, list(rates))


def route_anomaly_scenario(
    client: FakeGraphQLClient, *, names: dict[str, str] | None = None, **overrides
) -> FakeGraphQLClient:
    """Cenário de 05/10 do G2 (rajada, entidade nova, concentrada, silêncio, calendário e
    normais) com temas saudáveis; ``names`` troca o nome canônico de entidades."""
    rows, contexts = scenario_0510()
    for entity_id, name in (names or {}).items():
        rows = [{**r, "canonicalName": name} if r["entityId"] == entity_id else r for r in rows]
        ctx = contexts[entity_id]
        contexts[entity_id] = {**ctx, "entity": {**ctx["entity"], "canonicalName": name}}
    params = {"trending": rows, "contexts": contexts, "activity": ACTIVITY_0510}
    params.update(overrides)
    return route_g2(client, **params)


def route_graphql_down(client: FakeGraphQLClient) -> FakeGraphQLClient:
    """Toda consulta falha (a graphql-api fora do ar)."""
    client.execute.side_effect = GobusGraphQLError([{"message": "graphql-api fora do ar"}])
    return client


async def _anomalies(client: FakeGraphQLClient, now: datetime = NOW_0510, **kwargs) -> dict:
    from gobus_mcp.tools.detect_anomalies import build_anomaly_output

    report, markdown = await build_anomaly_output(client, now=now, **kwargs)
    return call_result(ui.app_result(report, content=markdown))


def anomaly_args(sensitivity: str = "medium", domain_filter: str = "") -> dict:
    """Argumentos do ``tools/call`` do app (``domain_filter`` só quando definido)."""
    return {
        "sensitivity": sensitivity,
        **({"domain_filter": domain_filter} if domain_filter else {}),
    }


async def anomaly_fixtures() -> dict[str, dict]:
    def scenario(**kw) -> FakeGraphQLClient:
        return route_anomaly_scenario(FakeGraphQLClient(), **kw)

    ok = await _anomalies(scenario())
    high = await _anomalies(scenario(), sensitivity="high")
    low = await _anomalies(scenario(), sensitivity="low")
    health = await _anomalies(scenario(), domain_filter="HEALTH")
    partial = await _anomalies(
        route_g2(
            FakeGraphQLClient(),
            themes=theme_ranges_0510(),
            trending=trending_rows_0510(),
            activity=ACTIVITY_0510,
        )
    )
    unavailable = await _anomalies(route_graphql_down(FakeGraphQLClient()))
    rows, contexts = scenario_0510()
    normal_only = {
        "trending": [r for r in rows if r["entityId"] == "dgb_normal"],
        "contexts": contexts,
        "activity": ACTIVITY_0510,
        "themes": flat_theme_ranges(),
    }
    quiet = await _anomalies(route_g2(FakeGraphQLClient(), **normal_only))
    empty = await _anomalies(
        route_g2(FakeGraphQLClient(), **normal_only), domain_filter="ENVIRONMENT"
    )
    recovery = await _anomalies(scenario(), now=RECOVERY_NOW)
    xss = await _anomalies(
        scenario(
            names={"dgb_concentrada": XSS_IMG, "dgb_silencio": XSS_SCRIPT, "dgb_normal": XSS_IMG},
            themes=xss_theme_ranges(),
        )
    )
    many_rows, many_contexts = many_candidates()
    max_ = await _anomalies(
        route_g2(
            FakeGraphQLClient(), trending=many_rows, contexts=many_contexts, activity=ACTIVITY_0510
        )
    )

    def fixture(state, description, tool_input, result, tool_calls=()):
        return {
            "app": "anomaly_radar",
            "state": state,
            "description": f"{DEV_NOTE}: {description}",
            "toolName": ANOMALY_TOOL,
            "toolInput": tool_input,
            "result": result,
            "toolCalls": [
                {"name": ANOMALY_TOOL, "arguments": args, "result": res} for args, res in tool_calls
            ],
        }

    return {
        "ok": fixture(
            "ok",
            "05/10 com temas saudáveis: pico e queda de tema, silêncio coordenado, concentrada, "
            "rajada, entidade nova, explicado pelo calendário e normais",
            {},
            ok,
            [
                (anomaly_args("high"), high),
                (anomaly_args("low"), low),
                (anomaly_args("medium", "HEALTH"), health),
                (anomaly_args("medium"), ok),
            ],
        ),
        "partial": fixture(
            "partial",
            "estado medido em 05/10: temas sem classificação desde 26/09 e ranking só com "
            "linhas do piso antigo (nenhum candidato)",
            {},
            partial,
        ),
        "unavailable": fixture("unavailable", "graphql-api fora do ar", {}, unavailable),
        "quiet": fixture(
            "quiet", "temas estáveis e uma entidade sem anomalia (status ok)", {}, quiet
        ),
        "empty": fixture(
            "empty",
            "domínio Meio ambiente sem nenhum sinal (status empty)",
            anomaly_args("medium", "ENVIRONMENT"),
            empty,
        ),
        "recovery": fixture(
            "recovery",
            "03/11/2026, recuperação pós-defeso: baselines pré-defeso e ranking envelhecido",
            {},
            recovery,
        ),
        "xss": fixture("xss", "nomes de entidade e rótulos de tema com HTML e </script>", {}, xss),
        "max": fixture(
            "max",
            "30 candidatos com nomes longos: payload compactado (omitidos) e Markdown completo",
            {},
            max_,
        ),
    }


# ── forecast radar ──────────────────────────────────────────────────────────

FORECAST_TOOL = "gobus_forecast_trends"
FORECAST_LIMIT = 8


def sparse_theme_ranges() -> dict[int, dict]:
    """Um artigo por dia, todo classificado, cada dia num tema diferente (60 temas): as
    janelas têm cobertura, mas nenhum tema chega a 5 artigos (lista vazia)."""
    labels = [f"Tema raro {k:02d}" for k in range(60)]
    index = {label: k for k, label in enumerate(labels)}
    return ranges_from_daily(lambda label, i: int(i % 60 == index[label]), lambda i: 1, labels)


async def _forecast(client: FakeGraphQLClient, now: datetime = NOW_0510, **kwargs) -> dict:
    from gobus_mcp.tools.forecast_trends import build_forecast_output

    report, markdown = await build_forecast_output(client, now=now, **kwargs)
    return call_result(ui.app_result(report, content=markdown))


def forecast_args(horizon_days: int = 21, limit: int = FORECAST_LIMIT) -> dict:
    """Argumentos do ``tools/call`` do app (horizonte do controle e o ``limit`` atual)."""
    return {"horizon_days": horizon_days, "limit": limit}


async def forecast_fixtures() -> dict[str, dict]:
    def healthy(**kw) -> FakeGraphQLClient:
        return route_g2(FakeGraphQLClient(), **kw)

    by_horizon = {
        h: await _forecast(healthy(), horizon_days=h, limit=FORECAST_LIMIT) for h in (7, 14, 21, 28)
    }
    partial = await _forecast(
        healthy(themes=theme_ranges_0510()), horizon_days=21, limit=FORECAST_LIMIT
    )
    unavailable = await _forecast(route_graphql_down(FakeGraphQLClient()))
    empty = await _forecast(healthy(themes=sparse_theme_ranges()), limit=FORECAST_LIMIT)
    recovery = await _forecast(healthy(), now=RECOVERY_NOW, horizon_days=14, limit=FORECAST_LIMIT)
    xss = await _forecast(healthy(themes=xss_theme_ranges()), limit=FORECAST_LIMIT)

    def fixture(state, description, tool_input, result, tool_calls=()):
        return {
            "app": "forecast_radar",
            "state": state,
            "description": f"{DEV_NOTE}: {description}",
            "toolName": FORECAST_TOOL,
            "toolInput": tool_input,
            "result": result,
            "toolCalls": [
                {"name": FORECAST_TOOL, "arguments": args, "result": res}
                for args, res in tool_calls
            ],
        }

    return {
        "ok": fixture(
            "ok",
            "temas 95% classificados: Saúde acelerando, Educação desacelerando, o resto estável; "
            "horizonte 21 dias, com as respostas de 7, 14 e 28",
            forecast_args(21),
            by_horizon[21],
            [(forecast_args(h), by_horizon[h]) for h in (7, 14, 21, 28)],
        ),
        "partial": fixture(
            "partial",
            "estado medido em 05/10: janelas de 3 e 7 dias sem classificação, 21 dias degradada",
            forecast_args(21),
            partial,
        ),
        "unavailable": fixture("unavailable", "graphql-api fora do ar", {}, unavailable),
        "empty": fixture(
            "empty",
            "janelas com cobertura, mas nenhum tema com 5 artigos (lista vazia)",
            forecast_args(21),
            empty,
        ),
        "recovery": fixture(
            "recovery",
            "03/11/2026, recuperação pós-defeso: confiança reduzida em um nível; horizonte 14",
            forecast_args(14),
            recovery,
        ),
        "xss": fixture("xss", "rótulos de tema com HTML e </script>", forecast_args(21), xss),
    }


# ── geração ─────────────────────────────────────────────────────────────────

BUILDERS: dict[str, Callable[[], Awaitable[dict[str, dict]]]] = {
    "readability_dashboard": readability_fixtures,
    "article_scorecard": scorecard_fixtures,
    "anomaly_radar": anomaly_fixtures,
    "forecast_radar": forecast_fixtures,
}


async def build_all() -> dict[Path, dict]:
    out: dict[Path, dict] = {}
    for app, builder in BUILDERS.items():
        for state, fixture in (await builder()).items():
            out[FIXTURES_DIR / app / f"{state}.json"] = fixture
    return out


# lista só de números (séries diárias) numa linha só: o JSON indentado fica legível e pequeno
_NUMBER_LIST_RE = re.compile(r"\[\s*(-?[\d.]+(?:,\s*-?[\d.]+)*)\s*\]")


def dumps(fixture: dict) -> str:
    text = json.dumps(fixture, ensure_ascii=False, indent=2)
    text = _NUMBER_LIST_RE.sub(
        lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text
    )
    return text + "\n"


def main() -> None:
    fixtures = asyncio.run(build_all())
    for path, fixture in fixtures.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(fixture))
        print(f"{path.relative_to(FIXTURES_DIR.parents[1])}: {len(dumps(fixture)) // 1024} KB")


if __name__ == "__main__":
    main()
