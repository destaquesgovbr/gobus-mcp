"""Calibração (sanity check) do ``gobus_get_message_coherence`` contra a graphql-api pública.

Só queries de leitura. Uso, na raiz do clone (ou worktree):

    PYTHONPATH=src .venv/bin/python3.12 _experiments/coherence-calibration-2026-10/run.py

Grava ``outputs/<caso>.md`` (o Markdown da tool) e ``results.json`` (dimensões e índice).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient
from gobus_mcp.tools.get_message_coherence import build_coherence_output

URL = os.environ.get(
    "GOBUS_LIVE_URL", "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"
)
HERE = Path(__file__).parent

# (caso, kwargs, rótulo de referência do UC-03 ou None)
CASES = [
    ("uc03-defesa-jun", {"theme": "Defesa e Forças Armadas"}, 4),
    ("uc03-minorias-jun", {"theme": "Minorias e Grupos Especiais"}, 3),
    ("uc03-justica-jun", {"theme": "Justiça e Direitos Humanos"}, 2),
    (
        "q575545-ago-set",
        {"entity_id": "Q575545", "date_from": "2026-08-01", "date_to": "2026-09-30"},
        None,
    ),
    ("q575545-jun", {"entity_id": "Q575545"}, None),
    ("pe-de-meia-jun", {"entity_id": "dgb_pe-de-meia"}, None),
    (
        "pe-de-meia-abr",
        {"entity_id": "dgb_pe-de-meia", "date_from": "2026-04-01", "date_to": "2026-04-30"},
        None,
    ),
    (
        "saude-tema-set-out",
        {"theme": "saude", "date_from": "2026-09-22", "date_to": "2026-10-05"},
        None,
    ),
]
JUNE = {"date_from": "2026-06-01", "date_to": "2026-06-30"}


async def main() -> None:
    client = GobusGraphQLClient(URL, timeout=30.0)
    catalog, cache = AgencyCatalog(client), TTLCache()
    out_dir = HERE / "outputs"
    out_dir.mkdir(exist_ok=True)
    results = []
    for name, kwargs, reference in CASES:
        kwargs = {**JUNE, **kwargs}
        start = time.perf_counter()
        report, markdown = await build_coherence_output(
            client, catalog=catalog, cache=cache, **kwargs
        )
        elapsed = time.perf_counter() - start
        (out_dir / f"{name}.md").write_text(markdown, encoding="utf-8")
        results.append(
            {
                "case": name,
                "params": report.params,
                "reference_uc03": reference,
                "index_status": report.index_status,
                "score": report.index.score,
                "level": report.index.level,
                "dimensions": {d.key: d.value for d in report.dimensions},
                "emitters": report.sample.emitters,
                "found": report.sample.found,
                "republisher_share": report.republishers.share,
                "hhi": report.hhi,
                "seconds": round(elapsed, 2),
                "markdown_bytes": len(markdown.encode()),
                "notices": sorted({n.code for n in report.notices}),
            }
        )
        print(
            f"{name:20s} {report.index.level}/5 score={report.index.score} "
            f"dims={ {d.key: d.value for d in report.dimensions} } "
            f"emissores={report.sample.emitters} {elapsed:.2f}s"
        )
    (HERE / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
