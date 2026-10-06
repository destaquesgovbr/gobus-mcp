"""Payload do app ``ui://forecast-radar`` (``structuredContent`` de ``gobus_forecast_trends``).

- o ``content`` leva o Markdown completo; o ``summary`` é o mesmo texto até 6 KB;
- série diária da projeção só nos temas que o app desenha com momentum (o top-3); os
  demais ficam com os totais e o intervalo;
- as opções de horizonte do controle vêm no payload (o JS não fixa 7/14/21/28).
"""

from gobus_mcp.analytics.render import SUMMARY_MAX_BYTES, fit_summary
from gobus_mcp.payloads.forecast import (
    HORIZON_OPTIONS,
    MAX_HORIZON_DAYS,
    MAX_PAYLOAD_BYTES,
    MAX_SERIES_THEMES,
    compact_forecast_payload,
    payload_size,
)
from gobus_mcp.tools.forecast_trends import build_forecast_output, build_forecast_report
from tests.conftest import FakeGraphQLClient
from tests.factories import forecast_report, forecast_theme, projection
from tests.fixtures.g2 import NOW_0510, route_g2


def _themes(n: int) -> list:
    return [forecast_theme(label=f"Tema {i}", projection=projection(horizon=28)) for i in range(n)]


def test_serie_da_projecao_so_no_top_3():
    report = forecast_report(themes=_themes(8), horizon=28)

    compact = compact_forecast_payload(report)

    for i, theme in enumerate(compact.themes):
        original = report.themes[i].projection
        assert theme.projection.expected_articles == original.expected_articles
        assert (theme.projection.low, theme.projection.high) == (original.low, original.high)
        if i < MAX_SERIES_THEMES:
            assert len(theme.projection.daily) == 28
        else:
            assert theme.projection.daily == []
    assert [t.label for t in compact.themes] == [t.label for t in report.themes]


def test_compactacao_aceita_tema_sem_projecao():
    themes = [forecast_theme(label="Sem projeção", projection=None), *_themes(4)]
    report = forecast_report(themes=themes)

    compact = compact_forecast_payload(report)

    assert compact.themes[0].projection is None
    assert compact.themes[3].projection.daily == []


def test_opcoes_de_horizonte_no_payload():
    data = forecast_report().model_dump(mode="json")

    assert data["horizonOptions"] == list(HORIZON_OPTIONS)
    assert max(HORIZON_OPTIONS) == MAX_HORIZON_DAYS


async def test_output_markdown_completo_e_payload_compacto():
    client = route_g2(FakeGraphQLClient())

    report, markdown = await build_forecast_output(client, horizon_days=28, limit=10, now=NOW_0510)
    again = await build_forecast_report(client, horizon_days=28, limit=10, now=NOW_0510)

    assert again == report
    assert "truncado" not in markdown and "### Metodologia" in markdown
    assert report.summary == fit_summary(markdown)
    assert len(report.summary.encode()) <= SUMMARY_MAX_BYTES
    with_series = [t.label for t in report.themes if t.projection and t.projection.daily]
    assert with_series == [t.label for t in report.themes[:MAX_SERIES_THEMES]]
    assert payload_size(report) <= MAX_PAYLOAD_BYTES
