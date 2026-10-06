"""``ForecastReport`` (integration.md §1.5): G2 produz, o app ``ui://forecast-radar`` consome."""

from datetime import date

import pytest
from pydantic import ValidationError

from gobus_mcp.payloads.anomalies import MAX_PAYLOAD_BYTES, payload_size
from gobus_mcp.payloads.forecast import ForecastReport, fit_forecast_budget
from tests.factories import forecast_report, forecast_theme, projection, window_ratio


def test_relatorio_valida_e_serializa_em_camel_case():
    report = forecast_report()
    data = report.model_dump(mode="json")
    assert data["schemaVersion"] == 1
    assert data["kind"] == "gobus.forecast" and data["tool"] == "gobus_forecast_trends"
    assert set(data["windows"]) == {"3d", "7d", "21d"}
    w3 = data["windows"]["3d"]
    assert w3["windowDays"] == 3 and w3["baselineDays"] == 14
    assert {"weight", "effectiveWeight", "classifiedCoverage", "businessDays"} <= set(w3)
    assert data["platform"]["weekdayProfile"]["5"] == 0.26
    assert data["platform"]["profileSource"] == "snapshot"
    theme = data["themes"][0]
    assert theme["windows"]["21d"] is None
    assert theme["windows"]["3d"]["perDayRate"] == 0.024
    proj = theme["projection"]
    assert {"horizonDays", "expectedArticles", "low", "high", "shareNow", "shareAtHorizon"} <= set(
        proj
    )
    assert proj["daily"][0] == {"date": "2026-10-05", "expected": 5.0}
    assert "weekendCorrection" not in data["params"]
    assert ForecastReport.model_validate(data) == report


def test_momentum_e_chaves_de_janela_em_ingles():
    with pytest.raises(ValidationError):
        forecast_theme(momentum="acelerando")
    with pytest.raises(ValidationError):
        forecast_theme(windows={"3": window_ratio()})
    forecast_theme(momentum="undetermined", acceleration=None, per_day_rate=None)


def test_no_maximo_10_temas_e_28_dias_de_projecao():
    forecast_report(themes=[forecast_theme(f"T{i}") for i in range(10)])
    with pytest.raises(ValidationError):
        forecast_report(themes=[forecast_theme(f"T{i}") for i in range(11)])
    projection(horizon=28)
    with pytest.raises(ValidationError):
        projection(horizon=29)


def test_projecao_pode_faltar():
    report = forecast_report(themes=[forecast_theme(projection=None, confidence="low")])
    assert report.model_dump(mode="json")["themes"][0]["projection"] is None


def test_fit_forecast_budget_tira_a_serie_diaria_dos_ultimos_temas():
    themes = [
        forecast_theme(f"Tema {i}", projection=projection(date(2026, 10, 5), 28)) for i in range(10)
    ]
    report = forecast_report(themes=themes, horizon=28, summary="m" * 6000)
    assert payload_size(report) > MAX_PAYLOAD_BYTES
    fitted = fit_forecast_budget(report)
    assert payload_size(fitted) <= MAX_PAYLOAD_BYTES
    assert len(fitted.themes) == 10
    assert fitted.themes[0].projection.daily  # o primeiro tema mantém a série
    assert fitted.themes[-1].projection.daily == []
    assert fitted.themes[-1].projection.expected_articles == themes[-1].projection.expected_articles
    assert fit_forecast_budget(forecast_report()) == forecast_report()
