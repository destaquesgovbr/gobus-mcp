"""ui://readability-dashboard — dashboard HTML auto-contido de legibilidade por agência.

Agências ativas do catálogo, médias null-aware (sem dado → "—", nunca barra de 0.0) e
janela efetiva quando o Flesch parou. O HTML atual é mantido; a migração para MCP App
(SEP-1865) é do G3.
"""

from __future__ import annotations

import html
import json
from datetime import date

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.calendario import closed_window, reference_date
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.readability import flesch_band
from gobus_mcp.readability_data import load_agency_readability, rank_agencies

WINDOW_DAYS = 90
AGENCY_LIMIT = 20
_BAND_COLORS = {
    "very_hard": "#e74c3c",
    "hard": "#e67e22",
    "medium": "#f1c40f",
    "easy": "#2ecc71",
}
_NO_DATA_COLOR = "#999999"


def _flesch_color(flesch: float | None) -> str:
    """Cor CSS da faixa do Flesch (já limitado a 0–100); cinza sem dado."""
    band = flesch_band(flesch)
    return _BAND_COLORS[band.key] if band else _NO_DATA_COLOR


def _render_bar_chart_svg(agencies_data: list[dict]) -> str:
    """SVG de barras horizontais (agências com dado × Flesch limitado a 0–100)."""
    agencies_data = [d for d in agencies_data if d["flesch"] is not None]
    if not agencies_data:
        return "<svg width='600' height='50'><text x='10' y='30'>Sem dados</text></svg>"

    bar_height = 30
    padding = 120
    max_chart_width = 350
    max_flesch = max(d["flesch"] for d in agencies_data) or 50

    svgs = []
    for i, d in enumerate(agencies_data):
        y = i * (bar_height + 8) + 10
        bar_width = d["flesch"] / max_flesch * max_chart_width
        color = _flesch_color(d["flesch"])
        label = html.escape(d["agency"][:18])
        svgs.append(
            f'<rect x="{padding}" y="{y}" width="{bar_width:.0f}" height="{bar_height}" '
            f'fill="{color}" rx="3"/>'
        )
        svgs.append(
            f'<text x="{padding - 5}" y="{y + 20}" text-anchor="end" '
            f'font-size="12" font-family="sans-serif" fill="#333">{label}</text>'
        )
        svgs.append(
            f'<text x="{padding + bar_width + 6}" y="{y + 20}" '
            f'font-size="12" font-family="sans-serif" fill="#555">{d["flesch"]:.1f}</text>'
        )

    total_height = len(agencies_data) * 38 + 30
    svg_content = "".join(svgs)
    return (
        f'<svg width="600" height="{total_height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Gráfico de legibilidade por agência">'
        f"{svg_content}"
        f"</svg>"
    )


def _cell(value: float | None, fmt: str) -> str:
    return "—" if value is None else format(value, fmt)


async def fetch_readability_dashboard(
    client: GobusGraphQLClient,
    *,
    catalog: AgencyCatalog | None = None,
    today: date | None = None,
) -> str:
    """Gera dashboard HTML auto-contido com barchart de legibilidade por agência.

    Returns:
        HTML auto-contido (sem referências externas) com gráfico SVG e JSON island.
    """
    catalog = catalog or AgencyCatalog(client)
    today = today or reference_date()
    requested = closed_window(WINDOW_DAYS, today)
    agencies = await catalog.active(WINDOW_DAYS, limit=AGENCY_LIMIT)
    window, items = await load_agency_readability(client, catalog, agencies, requested)
    with_data, without = rank_agencies(items)

    agencies_data = [
        {
            "agencyKey": a.code,
            "agencyName": a.name,
            "articleCount": a.article_count,
            "avgReadabilityFlesch": None if a.flesch.value is None else round(a.flesch.value, 2),
            "avgReadabilityFleschRaw": None if a.flesch.raw is None else round(a.flesch.raw, 2),
            "avgWordCount": None if a.avg_word_count is None else round(a.avg_word_count, 1),
        }
        for a in [*with_data, *without]
    ]
    effective = window.effective.effective
    if effective is None:
        period_note = "sem dados de legibilidade no histórico consultado"
    elif window.effective.shifted:
        period_note = (
            f"janela efetiva {effective.start:%d/%m/%Y}–{effective.end:%d/%m/%Y} "
            f"({window.effective.note})"
        )
    else:
        period_note = f"{requested.start:%d/%m/%Y}–{requested.end:%d/%m/%Y}"

    # Prepara dados para o SVG
    chart_items = [
        {"agency": d["agencyName"], "flesch": d["avgReadabilityFlesch"], "count": d["articleCount"]}
        for d in agencies_data
    ]
    svg_chart = _render_bar_chart_svg(chart_items)

    # JSON island — contém avgReadabilityFlesch para que os testes possam verificar
    # "</" escapado: um nome com "</script>" não fecha o bloco
    json_island = json.dumps(agencies_data, ensure_ascii=False, indent=2).replace("</", "<\\/")

    # JS inline minimal — implementa classe Chart para uso com canvas
    # (sem CDN; o canvas fica oculto pois usamos SVG, mas Chart está disponível para extensão)
    js_chart_impl = """
// Implementação minimal de Chart para uso com Canvas API (sem CDN externo)
class Chart {
    constructor(ctx, config) {
        this.ctx = ctx;
        this.config = config;
        this.data = config.data || {};
        this.type = config.type || 'bar';
    }
    render() {
        // Renderização delegada ao SVG inline — canvas disponível para extensões futuras
        console.info('Chart: usando SVG embutido como renderizador principal');
    }
    destroy() {}
    static register() {}
}

// Inicialização a partir do JSON island
(function() {
    const island = document.getElementById('readability-data');
    if (!island) return;
    const agenciesData = JSON.parse(island.textContent);

    // Expõe dados globalmente para uso interativo
    window.readabilityData = agenciesData;

    // Canvas disponível para extensões — Chart já registrado acima
    const canvas = document.getElementById('readabilityChart');
    if (canvas && typeof Chart !== 'undefined') {
        const chart = new Chart(canvas, {
            type: 'horizontalBar',
            data: { labels: agenciesData.map(d => d.agencyName), datasets: [{ data: agenciesData.map(d => d.avgReadabilityFlesch) }] }
        });
        chart.render();
    }
})();
"""

    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard de Legibilidade — Destaques Gov.BR</title>
<style>
  body {{ font-family: sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: 0.9rem; margin-bottom: 20px; }}
  .card {{ background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.1); margin-bottom: 20px; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; font-size: 0.8rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
  canvas {{ display: none; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
  th {{ background: #f9f9f9; font-weight: 600; }}
</style>
</head>
<body>
<h1>Dashboard de Legibilidade por Agência</h1>
<p class="subtitle">Índice Flesch médio (escala inglesa, limitado a 0–100) · {
        html.escape(period_note)
    } · Fonte: Destaques Gov.BR</p>

<!-- JSON data island -->
<script type="application/json" id="readability-data">
{json_island}
</script>

<!-- Canvas para extensão futura com Chart API -->
<canvas id="readabilityChart" width="600" height="400"></canvas>

<div class="card">
  <div class="legend">
    <span class="legend-item"><span class="swatch" style="background:#e74c3c"></span> 0–25 (muito difícil)</span>
    <span class="legend-item"><span class="swatch" style="background:#e67e22"></span> 25–50 (difícil)</span>
    <span class="legend-item"><span class="swatch" style="background:#f1c40f"></span> 50–75 (médio)</span>
    <span class="legend-item"><span class="swatch" style="background:#2ecc71"></span> ≥ 75 (fácil)</span>
    <span class="legend-item"><span class="swatch" style="background:#999999"></span> sem dado</span>
  </div>
  {svg_chart}
</div>

<div class="card">
  <table>
    <thead>
      <tr><th>#</th><th>Agência</th><th>Flesch</th><th>Artigos</th><th>Palavras/art.</th></tr>
    </thead>
    <tbody>
      {
        "\n      ".join(
            f"<tr><td>{i + 1}</td><td>{html.escape(d['agencyName'])}</td>"
            f'<td style="color:{_flesch_color(d["avgReadabilityFlesch"])};font-weight:600">'
            f"{_cell(d['avgReadabilityFlesch'], '.1f')}</td>"
            f"<td>{d['articleCount']}</td><td>{_cell(d['avgWordCount'], '.0f')}</td></tr>"
            for i, d in enumerate(agencies_data)
        )
    }
    </tbody>
  </table>
</div>

<script>
{js_chart_impl}
</script>
</body>
</html>"""

    return page
