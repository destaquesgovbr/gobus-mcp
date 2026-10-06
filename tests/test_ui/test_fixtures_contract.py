"""Fixtures JSON dos MCP Apps (``tests/fixtures/ui``): contrato pydantic, orçamentos e
arquivos em dia com os builders (são geradas por ``tests/fixtures/ui/build.py``)."""

import json
from pathlib import Path

import pytest

from gobus_mcp.analytics.render import fit_summary
from gobus_mcp.payloads.anomalies import AnomalyReport
from gobus_mcp.payloads.forecast import ForecastReport
from gobus_mcp.payloads.readability import ReadabilityReport
from gobus_mcp.payloads.scorecard import ScoreReport
from tests.fixtures.ui.build import FIXTURES_DIR, build_all, dumps

MODELS = {
    "gobus.readability": ReadabilityReport,
    "gobus.scorecard": ScoreReport,
    "gobus.anomalies": AnomalyReport,
    "gobus.forecast": ForecastReport,
}
FILES = sorted(FIXTURES_DIR.glob("*/*.json"))


def _results(fixture: dict) -> list[dict]:
    return [fixture["result"], *(call["result"] for call in fixture["toolCalls"])]


def test_ha_fixtures_para_cada_kind():
    kinds = {json.loads(path.read_text())["result"]["structuredContent"]["kind"] for path in FILES}
    assert kinds == set(MODELS)


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_valida_no_pydantic_e_cabe_no_orcamento(path: Path):
    fixture = json.loads(path.read_text())

    assert fixture["app"] == path.parent.name and fixture["state"] == path.stem
    assert fixture["description"].startswith("DEV — dados fictícios")
    for result in _results(fixture):
        sc = result["structuredContent"]
        assert result["isError"] is False
        assert next(iter(sc)) == "summary"
        (block,) = result["content"]
        assert block["type"] == "text"
        assert sc["summary"] == fit_summary(block["text"])  # content = Markdown completo
        assert len(sc["summary"].encode()) <= 6 * 1024
        assert len(json.dumps(sc, ensure_ascii=False).encode()) <= 20_000
        MODELS[sc["kind"]].model_validate(sc)


async def test_fixtures_em_dia_com_os_builders():
    expected = await build_all()

    assert sorted(expected) == FILES
    for path, fixture in expected.items():
        assert path.read_text() == dumps(fixture), (
            f"{path.name} desatualizada: PYTHONPATH=src python -m tests.fixtures.ui.build"
        )
