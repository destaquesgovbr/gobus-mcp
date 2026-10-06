"""Fixtures do G2 (anomalias, forecast e health): o estado medido em 05/10/2026 e cenários
sintéticos. Dados de entidades e agências são fictícios, mas seguem os formatos da API
(``period`` do ``entityCoverage`` em ``'AAAA-MM-DD 00:00:00+00'``, do ``agencyAnalytics``
DAY em ``'AAAA-MM-DD'``; ``computedAt`` como o Postgres devolve).

Estado de 05/10/2026 (``_plan/fase2_5/investigacao/live-probe.md``):
- temas sem classificação desde 26/09 (25/09: 49 de 175); ~189 artigos por dia útil,
  ~50 no sábado e ~23 no domingo;
- ``trendingEntities(50)``: todas as linhas com baseline zero no piso antigo
  (``volumeRatio = windowCount × 142,857``, de 714× a 8571×), ``computedAt`` espalhado
  por 32 execuções de 25/06 a 05/10 (só 2 linhas da última).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta

from gobus_mcp.calendario import BRT
from tests.conftest import FakeGraphQLClient, route_catalog

TODAY_0510 = date(2026, 10, 5)
NOW_0510 = datetime(2026, 10, 5, 22, 0, tzinfo=BRT)  # 06/10 01:00 UTC
LAST_RUN_0510 = "2026-10-05 21:00:20.644118+00"
FLOOR_FACTOR = 1 / 0.007  # 142,857: baseline implícito 0,007 (piso 0,001 × 7)

RANGE_DAYS = (3, 7, 14, 21, 28, 84)

# Fatias dos temas entre os artigos do dia (o resto fica sem tema mesmo em dia normal).
THEME_SHARES: Mapping[str, float] = {
    "Economia e Finanças": 0.20,
    "Saúde": 0.15,
    "Educação": 0.12,
    "Desenvolvimento Social": 0.10,
    "Segurança Pública": 0.10,
    "Cultura": 0.10,
    "Infraestrutura e Transportes": 0.10,
    "Meio Ambiente e Sustentabilidade": 0.10,
}


def weekday_volume(day: date) -> int:
    """Artigos por dia no defeso: 189 em dia útil, 50 no sábado, 23 no domingo."""
    return {5: 50, 6: 23}.get(day.weekday(), 189)


def theme_response(counts: Mapping[str, int], total: int) -> dict:
    return {
        "topThemes": [
            {"label": label, "count": n}
            for label, n in sorted(counts.items(), key=lambda kv: -kv[1])
            if n
        ],
        "analyticsKpis": {"total": total},
    }


def ranges_from_daily(
    label_daily: Callable[[str, int], int],
    total_daily: Callable[[int], int],
    labels: list[str],
    days: tuple[int, ...] = RANGE_DAYS,
) -> dict[int, dict]:
    """Respostas ``ThemeRangeCounts`` a partir de séries diárias (``i`` = dias atrás, 0 = hoje).

    O range de ``d`` dias soma ``i ∈ [0, d)``: assim todo range maior inclui o menor."""
    out: dict[int, dict] = {}
    for d in days:
        counts = {label: sum(label_daily(label, i) for i in range(d)) for label in labels}
        out[d] = theme_response(counts, sum(total_daily(i) for i in range(d)))
    return out


def _classified_0510(i: int) -> float:
    """Fração classificada ``i`` dias antes de 05/10: 0 desde 26/09, 28% em 25/09."""
    day = TODAY_0510 - timedelta(days=i)
    if day >= date(2026, 9, 26):
        return 0.0
    if day == date(2026, 9, 25):
        return 49 / 175
    return 1.0


def theme_ranges_0510() -> dict[int, dict]:
    """``topThemes`` + ``analyticsKpis`` de 05/10: 3 e 7 dias com 0% classificado."""

    def total(i: int) -> int:
        return weekday_volume(TODAY_0510 - timedelta(days=i))

    def label_daily(label: str, i: int) -> int:
        return round(total(i) * THEME_SHARES[label] * _classified_0510(i))

    return ranges_from_daily(label_daily, total, list(THEME_SHARES))


def trending_rows_0510() -> list[dict]:
    """As 50 linhas do ``trendingEntities`` de 05/10: piso antigo e 32 execuções."""
    runs = [f"2026-{m:02d}-{d:02d} 21:00:20.1+00" for m, d in _run_dates()] + [LAST_RUN_0510]
    rows = [
        {
            "entityId": "dgb_censo-escolar-2025",
            "canonicalName": "Censo Escolar 2025",
            "type": "EVENT",
            "trendingScore": 5144.1,
            "volumeRatio": 8571.4,
            "windowCount": 60,
            "windowAgencies": 5,
            "computedAt": "2026-07-03 21:00:20.1+00",
        },
        {
            "entityId": "Q2469225",
            "canonicalName": "Nossa Senhora Aparecida",
            "type": "PER",
            "trendingScore": 514.79,
            "volumeRatio": 857.14,
            "windowCount": 6,
            "windowAgencies": 2,
            "computedAt": LAST_RUN_0510,
        },
    ]
    for i in range(48):
        wc = 5 + i % 9
        rows.append(
            {
                "entityId": f"dgb_entidade-{i:02d}",
                "canonicalName": f"Entidade legada {i:02d}",
                "type": ("ORG", "LAW", "PER", "LOC", "POLICY")[i % 5],
                "trendingScore": round(0.6 * wc * FLOOR_FACTOR, 2),
                "volumeRatio": round(wc * FLOOR_FACTOR, 2),
                "windowCount": wc,
                "windowAgencies": 1 + i % 6,
                "computedAt": LAST_RUN_0510 if i == 0 else runs[i % (len(runs) - 1)],
            }
        )
    return rows


def _run_dates() -> list[tuple[int, int]]:
    start = date(2026, 6, 25)
    return [((start + timedelta(days=3 * k)).month, (start + timedelta(days=3 * k)).day)
            for k in range(30)]  # fmt: skip


# ── cenários sintéticos ─────────────────────────────────────────────────────


def healthy_theme_ranges(days: tuple[int, ...] = RANGE_DAYS) -> dict[int, dict]:
    """Temas 95% classificados; "Saúde" acelera (pico sustentado), "Educação" desacelera,
    o resto estável."""
    rates = {
        "Saúde": lambda i: 40 if i < 3 else 30 if i < 7 else 10,
        "Educação": lambda i: 4 if i < 3 else 8 if i < 7 else 15,
        "Economia e Finanças": lambda i: 25,
        "Segurança Pública": lambda i: 15,
        "Meio Ambiente e Sustentabilidade": lambda i: 8,
        "Cultura": lambda i: 6,
    }

    def total(i: int) -> int:
        return round(sum(f(i) for f in rates.values()) / 0.95)

    return ranges_from_daily(lambda label, i: rates[label](i), total, list(rates), days)


def coverage_rows(agency: str, counts: Mapping[date, int]) -> list[dict]:
    """Linhas ``entityCoverage(DAY)`` de uma agência (dias UTC)."""
    return [
        {"period": f"{day.isoformat()} 00:00:00+00", "agencyKey": agency, "articleCount": n}
        for day, n in sorted(counts.items())
        if n
    ]


def spread(start: date, end: date, total: int) -> dict[date, int]:
    """``total`` artigos distribuídos (round-robin) nos dias de ``[start, end]``."""
    days = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    out: dict[date, int] = {}
    for k in range(total):
        out[days[k % len(days)]] = out.get(days[k % len(days)], 0) + 1
    return out


def activity_route(spec: Mapping[str, Callable[[date], int]]):
    """Rota ``AgencyActivitySnapshot``: linhas DAY de cada agência de ``spec`` entre
    ``dateFrom`` e ``dateTo`` (inclusivo), com zeros explícitos."""

    def respond(variables: dict) -> dict:
        start = date.fromisoformat(variables["dateFrom"])
        end = date.fromisoformat(variables["dateTo"])
        rows = []
        for agency, fn in spec.items():
            if agency not in variables["agencies"]:
                continue
            day = start
            while day <= end:
                rows.append(
                    {
                        "period": day.isoformat(),
                        "agencyKey": agency,
                        "agencyName": agency.upper(),
                        "articleCount": fn(day),
                    }
                )
                day += timedelta(days=1)
        return {"agencyAnalytics": rows}

    return respond


def busy(day: date) -> int:
    """Agência ativa: 10 artigos por dia útil, 3 no sábado, 1 no domingo."""
    return {5: 3, 6: 1}.get(day.weekday(), 10)


def route_g2(
    client: FakeGraphQLClient,
    *,
    themes: Mapping[int, dict] | None = None,
    trending: list[dict] | None = None,
    contexts: Mapping[str, dict] | None = None,
    activity: Mapping[str, Callable[[date], int]] | None = None,
) -> FakeGraphQLClient:
    """Registra catálogo, temas, ranking, contexto de entidade e snapshot de atividade."""
    route_catalog(client)
    theme_data = healthy_theme_ranges() if themes is None else themes
    client.route(
        "ThemeRangeCounts",
        lambda v: theme_data.get(v["days"], theme_response({}, 0)),
    )
    client.route("AnomalyTrendingEntities", {"trendingEntities": trending or []})
    ctx = contexts or {}
    client.route(
        "AnomalyEntityContext",
        lambda v: ctx.get(v["id"], {"entity": None, "entityCoverage": [], "policyDetails": None}),
    )
    spec = {"saude": busy, "mec": busy, "pf": busy, "cgu": busy} if activity is None else activity
    client.route("AgencyActivitySnapshot", activity_route(spec))
    return client


def trending_row(entity_id: str, name: str, *, type_: str = "ORG", vr: float, wc: int,
                 run: str = "2026-10-05 03:00:00+00", score: float | None = None) -> dict:  # fmt: skip
    return {
        "entityId": entity_id,
        "canonicalName": name,
        "type": type_,
        "trendingScore": score if score is not None else round(vr * 0.6, 2),
        "volumeRatio": vr,
        "windowCount": wc,
        "windowAgencies": 2,
        "computedAt": run,
    }


def context(entity_id: str, name: str, *, type_: str = "ORG", agency_key: str | None = None,
            rows: list[dict], domain: str | None = None) -> dict:  # fmt: skip
    return {
        "entity": {
            "entityId": entity_id,
            "canonicalName": name,
            "type": type_,
            "agencyKey": agency_key,
        },
        "entityCoverage": rows,
        "policyDetails": {"domain": domain} if type_ == "POLICY" else None,
    }


# ── cenários de anomalias (testes da tool e fixtures dos apps) ─────────────────

RUN_0510 = "2026-10-05 21:00:00+00"


def silent_since_blackout(day: date) -> int:
    """Agência que parou de publicar no início do defeso (04/07)."""
    return busy(day) if day < date(2026, 7, 4) else 0


def resumed_on_26_10(day: date) -> int:
    """Agência calada no defeso que voltou a publicar em 26/10."""
    return busy(day) if day < date(2026, 7, 4) or day >= date(2026, 10, 26) else 0


ACTIVITY_0510 = {
    "saude": busy,
    "mec": busy,
    "pf": busy,
    "cgu": busy,
    "secom": silent_since_blackout,
}


def scenario_0510() -> tuple[list[dict], dict[str, dict]]:
    """Ranking já corrigido (uma execução, Laplace) e a cobertura de cada candidato em
    05/10: janela 28/09–04/10 e baseline 31/08–27/09."""
    rows = [
        trending_row("dgb_novo", "Programa Novo", vr=32.0, wc=7, run=RUN_0510),
        trending_row(
            "dgb_censo-escolar-2025",
            "Censo Escolar 2025",
            type_="EVENT",
            vr=4321.0,
            wc=60,
            run=RUN_0510,
        ),  # fmt: skip
        trending_row("dgb_concentrada", "Pauta Concentrada", vr=10.4, wc=12, run=RUN_0510),
        trending_row("dgb_silencio", "Tema Calado", vr=13.0, wc=9, run=RUN_0510),
        trending_row("dgb_secom", "Pauta da Secom", vr=7.0, wc=6, run=RUN_0510),
        trending_row("dgb_normal", "Assunto Comum", vr=1.06, wc=12, run=RUN_0510),
        trending_row("dgb_pe-de-meia", "Pé-de-Meia", type_="POLICY", vr=1.14, wc=5, run=RUN_0510),
        trending_row("dgb_republicada", "Só Republicada", vr=2.0, wc=5, run=RUN_0510),
    ]
    normal_rows = []
    for agency in ("saude", "mec", "pf", "cgu", "defesa", "trabalho-e-emprego"):
        normal_rows += coverage_rows(
            agency,
            {
                **spread(date(2026, 8, 31), date(2026, 9, 27), 8),
                **spread(date(2026, 9, 28), date(2026, 10, 4), 2),
            },
        )
    contexts = {
        # baseline zero com padrão de concentrada (2 agências, 3 dias): é entidade nova
        "dgb_novo": context(
            "dgb_novo",
            "Programa Novo",
            rows=coverage_rows("mec", {date(2026, 9, 29): 3, date(2026, 10, 1): 2})
            + coverage_rows("cgu", {date(2026, 10, 2): 2}),
        ),  # fmt: skip
        # caso Censo: 57 de 60 artigos num dia
        "dgb_censo-escolar-2025": context(
            "dgb_censo-escolar-2025",
            "Censo Escolar 2025",
            type_="EVENT",
            rows=coverage_rows(
                "inep", {date(2026, 9, 10): 2, date(2026, 10, 1): 57, date(2026, 10, 2): 3}
            ),
        ),  # fmt: skip
        "dgb_concentrada": context(
            "dgb_concentrada",
            "Pauta Concentrada",
            rows=coverage_rows(
                "mec",
                {
                    **spread(date(2026, 9, 1), date(2026, 9, 20), 4),
                    **spread(date(2026, 9, 29), date(2026, 10, 2), 8),
                },
            )
            + coverage_rows("saude", spread(date(2026, 9, 29), date(2026, 10, 2), 4)),
        ),  # fmt: skip
        "dgb_silencio": context(
            "dgb_silencio",
            "Tema Calado",
            agency_key="saude",
            rows=coverage_rows("saude", spread(date(2026, 9, 1), date(2026, 9, 25), 6))
            + coverage_rows(
                "mec",
                {
                    **spread(date(2026, 9, 2), date(2026, 9, 20), 2),
                    **spread(date(2026, 9, 28), date(2026, 10, 3), 4),
                },
            )
            + coverage_rows("pf", spread(date(2026, 9, 29), date(2026, 10, 2), 3))
            + coverage_rows("cgu", {date(2026, 9, 30): 1, date(2026, 10, 1): 1}),
        ),  # fmt: skip
        "dgb_secom": context(
            "dgb_secom",
            "Pauta da Secom",
            agency_key="secom",
            rows=coverage_rows(
                "mec", {date(2026, 9, 5): 2, date(2026, 9, 29): 2, date(2026, 9, 30): 1}
            )
            + coverage_rows("pf", {date(2026, 10, 1): 2, date(2026, 10, 2): 1}),
        ),  # fmt: skip
        "dgb_normal": context("dgb_normal", "Assunto Comum", rows=normal_rows),
        "dgb_pe-de-meia": context(
            "dgb_pe-de-meia",
            "Pé-de-Meia",
            type_="POLICY",
            domain="EDUCATION",
            rows=coverage_rows(
                "mec",
                {
                    **spread(date(2026, 8, 31), date(2026, 9, 27), 20),
                    **spread(date(2026, 9, 28), date(2026, 10, 4), 5),
                },
            ),
        ),  # fmt: skip
        "dgb_republicada": context(
            "dgb_republicada",
            "Só Republicada",
            rows=coverage_rows(
                "agencia_brasil",
                {date(2026, 9, 10): 3, **spread(date(2026, 9, 28), date(2026, 10, 2), 5)},
            ),
        ),  # fmt: skip
    }
    return rows, contexts


def many_candidates(n: int = 30) -> tuple[list[dict], dict[str, dict]]:
    rows, contexts = [], {}
    agencies = ("saude", "mec", "pf", "cgu", "defesa", "trabalho-e-emprego", "mds")
    for i in range(n):
        entity_id = f"dgb_entidade-com-nome-longo-{i:02d}"
        name = f"Entidade com um nome canônico razoavelmente longo número {i:02d}"
        rows.append(trending_row(entity_id, name, vr=2.0 + i, wc=20 + i, run=RUN_0510))
        cov = []
        for k, agency in enumerate(agencies):
            cov += coverage_rows(
                agency,
                {**spread(date(2026, 7, 7), date(2026, 9, 27), 20 + k),
                 **spread(date(2026, 9, 28), date(2026, 10, 4), 3 + (i + k) % 4)},
            )  # fmt: skip
        contexts[entity_id] = context(entity_id, name, agency_key="saude", rows=cov)
    return rows, contexts
