"""Contratos de payload compartilhados (integration.md §1.2–1.3)."""

import json
from datetime import UTC, date, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from gobus_mcp.payloads.common import (
    CalendarContext,
    DataKey,
    DataStatus,
    Notice,
    NoticeCode,
    Payload,
    ReportBase,
    ReportStatus,
    Status,
    Window,
)


def _calendar(**overrides) -> CalendarContext:
    base = dict(
        phase="blackout",
        label="Defeso eleitoral 2026",
        blackout_start=date(2026, 7, 4),
        blackout_end=date(2026, 10, 25),
        recovery_until=date(2026, 11, 29),
        days_to_end=20,
        silenced_agencies=None,
        resumed_agencies=None,
    )
    base.update(overrides)
    return CalendarContext(**base)


def test_vocabularios_de_status_e_codigos():
    assert set(get_args(Status)) == {"ok", "degraded", "unavailable"}
    assert set(get_args(ReportStatus)) == {"ok", "partial", "empty", "unavailable"}
    assert set(get_args(DataKey)) == {
        "themes",
        "summaries",
        "sentiment_labels",
        "sentiment_analytics",
        "entities_ner",
        "readability",
        "word_count",
        "article_trending",
        "entity_ranking",
        "indexing_lag",
        "agency_activity",
    }
    assert set(get_args(NoticeCode)) == {
        "THEMES_UNCLASSIFIED",
        "SENTIMENT_UNAVAILABLE",
        "READABILITY_UNAVAILABLE",
        "TRENDING_ENTITIES_STALE",
        "BASELINE_ZERO_SUPPRESSED",
        "CLASSIFIER_CHANGED",
        "ELECTORAL_BLACKOUT",
        "POST_BLACKOUT_RECOVERY",
        "INDEXING_LAG",
        "SAMPLE_TRUNCATED",
    }


def test_payload_serializa_em_camel_case_por_padrao_e_aceita_nome_ou_alias():
    ds = DataStatus(key="themes", status="unavailable", since=date(2026, 9, 26), message="x")
    assert ds.model_dump(mode="json") == {
        "key": "themes",
        "status": "unavailable",
        "since": "2026-09-26",
        "message": "x",
        "metric": {},
    }

    cal = _calendar()
    dumped = cal.model_dump(mode="json")
    assert dumped["blackoutStart"] == "2026-07-04"
    assert dumped["daysToEnd"] == 20
    assert "blackout_start" not in dumped

    # validate_by_name + validate_by_alias
    assert CalendarContext.model_validate(dumped) == cal
    assert CalendarContext.model_validate(cal.model_dump()) == cal


def test_null_sai_como_null_no_json():
    cal = _calendar(phase="normal", label=None, blackout_start=None, days_to_end=None)
    data = json.loads(cal.model_dump_json())
    assert data["label"] is None
    assert data["silencedAgencies"] is None
    assert "blackoutStart" in data


def test_campo_extra_e_valor_fora_do_vocabulario_sao_rejeitados():
    with pytest.raises(ValidationError):
        DataStatus(key="themes", status="ok", since=None, message="", foo=1)
    with pytest.raises(ValidationError):
        DataStatus(key="temas", status="ok", since=None, message="")
    with pytest.raises(ValidationError):
        DataStatus(key="themes", status="indisponivel", since=None, message="")
    with pytest.raises(ValidationError):
        Notice(code="NAO_EXISTE", severity="warn", message="", since=None)


def test_notice_defaults():
    notice = Notice(code="THEMES_UNCLASSIFIED", severity="warn", message="m", since=None)
    assert notice.affects == []
    assert notice.model_dump(mode="json")["affects"] == []


def test_window_kind_e_fuso():
    w = Window(
        kind="closed",
        start=datetime(2026, 9, 28, 3, tzinfo=UTC),
        end=datetime(2026, 10, 5, 3, tzinfo=UTC),
        days=7,
        bucket_tz="America/Sao_Paulo",
    )
    assert w.baseline_overlaps_blackout is False
    assert w.model_dump(mode="json")["bucketTz"] == "America/Sao_Paulo"
    with pytest.raises(ValidationError):
        Window(kind="fechada", start=w.start, end=w.end, days=7, bucket_tz="UTC")


class _ExampleReport(ReportBase):
    kind: str = "gobus.example"
    tool: str = "gobus_example"
    items: list[int] = []


def test_report_base_campos_comuns_e_schema_version():
    report = _ExampleReport(
        summary="## Exemplo",
        status="partial",
        generated_at=datetime(2026, 10, 5, 15, tzinfo=UTC),
        reference_date=date(2026, 10, 5),
        params={"sensitivity": "medium"},
        calendar=_calendar(),
        data_status=[
            DataStatus(key="themes", status="unavailable", since=date(2026, 9, 26), message="m")
        ],
        notices=[],
        items=[1, 2],
    )
    data = report.model_dump(mode="json")
    assert data["schemaVersion"] == 1
    assert list(data)[:3] == ["schemaVersion", "kind", "tool"]
    assert data["summary"] == "## Exemplo"
    assert data["referenceDate"] == "2026-10-05"
    assert data["dataStatus"][0]["key"] == "themes"
    assert _ExampleReport.model_validate(data) == report

    with pytest.raises(ValidationError):
        _ExampleReport.model_validate({**data, "schemaVersion": 2})


def test_payload_e_a_base_de_todos_os_modelos():
    for model in (DataStatus, Notice, CalendarContext, Window, ReportBase):
        assert issubclass(model, Payload)
