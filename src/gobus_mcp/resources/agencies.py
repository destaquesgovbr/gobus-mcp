"""gobus://agencies — agências do catálogo com nome humano e código.

A API devolve ``label == code`` em ``agencies``; o nome vem do ``AgencyCatalog``
(``agencyAnalytics.agencyName``). Republicadoras (EBC, Agência Brasil, TV Brasil, Rádio
Agência Nacional) ficam em seção própria.
"""

from __future__ import annotations

from gobus_mcp.agency_catalog import AgencyCatalog
from gobus_mcp.client import GobusGraphQLClient


def _line(name: str, code: str) -> str:
    return f"- **{name}** (`{code}`)" if name != code else f"- `{code}`"


async def fetch_agencies(
    client: GobusGraphQLClient, *, catalog: AgencyCatalog | None = None
) -> str:
    catalog = catalog or AgencyCatalog(client)
    agencies = await catalog.all()
    if not agencies:
        return "Nenhuma agência encontrada."
    republishers = await catalog.republishers()
    by_name = sorted(agencies, key=lambda a: a.name.casefold())
    main = [a for a in by_name if a.code not in republishers]
    reps = [a for a in by_name if a.code in republishers]

    lines = [
        f"# Agências Governamentais ({len(agencies)})\n",
        "Use o código entre crases em `agency_key` / `agencies` das tools.\n",
    ]
    lines += [_line(a.name, a.code) for a in main]
    if reps:
        lines.append("\n## Republicadoras\n")
        lines.append(
            "Republicam conteúdo de outros órgãos; as análises de cobertura as tratam à parte.\n"
        )
        lines += [_line(a.name, a.code) for a in reps]
    return "\n".join(lines)
