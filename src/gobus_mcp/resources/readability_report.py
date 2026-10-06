"""gobus://readability-report — legibilidade (Flesch) por agência, em JSON.

Agências: as 20 mais ativas dos últimos 90 dias (catálogo, nada de lista fixa).
Null-aware: agência sem Flesch tem ``avgReadabilityFlesch`` e ``gapToTarget`` nulos (nunca
0.0). Se o cálculo do Flesch parou antes do fim da janela, os valores vêm da **janela
efetiva** (mesmo tamanho, até o último mês com dado), com ``windowShifted`` e ``note``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.payloads.readability import DayRange, flesch_bands
from gobus_mcp.readability import FLESCH_SCALE_ID, TARGET_SERVICE, flesch_band
from gobus_mcp.readability_data import AgencyReadability, load_agency_readability, rank_agencies

SCHEMA_VERSION = 2
WINDOW_DAYS = 90
AGENCY_LIMIT = 20


def _agency(item: AgencyReadability) -> dict:
    value, raw = item.flesch.value, item.flesch.raw
    band = flesch_band(item.flesch)
    return {
        "agencyKey": item.code,
        "agencyName": item.name,
        "isRepublisher": item.is_republisher,
        "articleCount": item.article_count,
        "articlesWithData": item.articles_with_data,
        "avgReadabilityFlesch": None if value is None else round(value, 2),
        "avgReadabilityFleschRaw": None if raw is None else round(raw, 2),
        "band": band.key if band else None,
        "gapToTarget": None if value is None else round(value - TARGET_SERVICE, 2),
        "avgWordCount": None if item.avg_word_count is None else round(item.avg_word_count, 1),
    }


async def fetch_readability_report(
    client: GobusGraphQLClient,
    *,
    catalog: AgencyCatalog | None = None,
    today: date | None = None,
) -> str:
    """JSON (``schemaVersion`` 2) com a legibilidade por agência e a janela efetiva."""
    catalog = catalog or AgencyCatalog(client)
    today = today or reference_date()
    requested = closed_window(WINDOW_DAYS, today)
    agencies = await catalog.active(WINDOW_DAYS, limit=AGENCY_LIMIT)
    window, items = await load_agency_readability(client, catalog, agencies, requested)
    with_data, without = rank_agencies(items)
    effective = window.effective.effective
    coverage = window.coverage

    result = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "referenceDate": today.isoformat(),
        "scale": FLESCH_SCALE_ID,
        "targetFlesch": int(TARGET_SERVICE),
        "bands": [b.model_dump(mode="json") for b in flesch_bands()],
        "requestedWindow": DayRange.of(requested).model_dump(mode="json"),
        "effectiveWindow": DayRange.of(effective).model_dump(mode="json") if effective else None,
        "windowShifted": window.effective.shifted,
        "note": window.effective.note,
        "coverage": {
            "periodsTotal": coverage.periods_total,
            "periodsWithData": coverage.periods_with_data,
            "articlesTotal": coverage.articles_total,
            "articlesInPeriodsWithData": coverage.articles_in_periods_with_data,
            "lastPeriodWithData": coverage.last_period_with_data,
        },
        "dataStatus": [window.data_status.model_dump(mode="json")],
        "agencies": [_agency(a) for a in [*with_data, *without]],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
