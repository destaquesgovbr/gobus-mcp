"""Smoke ao vivo do G2 contra a graphql-api de produção (só queries de leitura).

Fora do CI: ``pytest -m live tests/test_live_g2.py -s`` (o ``-s`` imprime o Markdown).
``GOBUS_LIVE_URL`` troca o endpoint. Só verifica forma, orçamento e as garantias de
contrato (nada de ``volumeRatio`` do upstream no Markdown); o conteúdo muda a cada dia.
"""

import json
import os
import time

import pytest

from gobus_mcp.agency_activity import AgencyActivityService
from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.data_status import LEGACY_FLOOR_RATIO
from gobus_mcp.payloads.anomalies import MAX_PAYLOAD_BYTES, AnomalyReport, payload_size
from gobus_mcp.payloads.forecast import ForecastReport
from gobus_mcp.resources.health_pipelines import fetch_health_pipelines
from gobus_mcp.tools.detect_anomalies import _TRENDING_QUERY, build_anomaly_report
from gobus_mcp.tools.forecast_trends import build_forecast_report
from tests.fixtures.refresh_schema import DEFAULT_URL

pytestmark = pytest.mark.live


@pytest.fixture
def live():
    client = GobusGraphQLClient(os.environ.get("GOBUS_LIVE_URL") or DEFAULT_URL, timeout=30.0)
    catalog = AgencyCatalog(client)
    return client, catalog, AgencyActivityService(client, catalog), TTLCache()


async def _legacy_ratios(client: GobusGraphQLClient) -> list[str]:
    """``volumeRatio`` das linhas do piso antigo (``vr/wc ≥ 100``), formatados como o
    Markdown formataria. Desde o DP-B o upstream usa o mesmo Laplace do gobus, então a
    razão recalculada pode coincidir com o ``volumeRatio`` de uma linha boa; o que nunca
    pode aparecer são os valores do piso antigo."""
    data = await client.execute(_TRENDING_QUERY)
    out = []
    for row in data.get("trendingEntities") or []:
        vr, wc = row.get("volumeRatio") or 0, max(row.get("windowCount") or 0, 1)
        if vr / wc >= LEGACY_FLOOR_RATIO:
            out += [f"{vr:.1f}".replace(".", ",") + "×", f"{vr:.1f}"]
    return out


async def test_detect_anomalies_ao_vivo(live):
    client, catalog, activity, cache = live

    start = time.perf_counter()
    report = await build_anomaly_report(client, catalog=catalog, activity=activity, cache=cache)
    cold = time.perf_counter() - start
    start = time.perf_counter()
    await build_anomaly_report(client, catalog=catalog, activity=activity, cache=cache)
    warm = time.perf_counter() - start
    print(f"\n[anomalias] frio {cold:.2f} s · quente {warm:.2f} s · {payload_size(report)} B")
    print(report.summary)

    AnomalyReport.model_validate(report.model_dump(mode="json"))
    assert payload_size(report) <= MAX_PAYLOAD_BYTES
    assert len(report.summary.encode()) <= 6_144
    for legacy in await _legacy_ratios(client):
        assert legacy not in report.summary
    assert not [
        s
        for s in report.entities.signals
        if s.baseline_count == 0 and s.kind in ("coordinated_silence", "concentrated_coverage")
    ]
    assert warm <= 2.0


async def test_forecast_trends_ao_vivo(live):
    client, catalog, activity, cache = live

    r7 = await build_forecast_report(
        client, horizon_days=7, catalog=catalog, activity=activity, cache=cache
    )
    start = time.perf_counter()
    r21 = await build_forecast_report(
        client, horizon_days=21, catalog=catalog, activity=activity, cache=cache
    )
    warm = time.perf_counter() - start
    print(f"\n[forecast] quente {warm:.2f} s · {payload_size(r21)} B")
    print(r21.summary)

    for report in (r7, r21):
        ForecastReport.model_validate(report.model_dump(mode="json"))
        assert payload_size(report) <= MAX_PAYLOAD_BYTES
    assert r7.summary != r21.summary
    assert warm <= 2.0


async def test_health_pipelines_ao_vivo(live):
    client, catalog, activity, _ = live

    data = json.loads(await fetch_health_pipelines(client, catalog=catalog, activity=activity))
    print("\n[health]", json.dumps(
        {k: (v["status"], v["message"]) for k, v in data["pipelines"].items()},
        ensure_ascii=False, indent=1,
    ))  # fmt: skip

    assert {"indexing_lag", "agency_activity"} <= set(data["pipelines"])
    assert data["agencyActivity"] is not None
