"""Contagens de temas por range móvel para anomalias e forecast (D7 do plano).

Uma consulta ``ThemeRangeCounts`` por range: ``topThemes(range:{days}, limit:100)`` (artigos
por label L1) e ``analyticsKpis(range:{days}){total}``. Os dois leem o Typesense com o
mesmo ``range:{days}`` — janela **móvel** de ``days`` × 24 h até a consulta, em UTC —, então
o atraso de indexação afeta numerador e denominador igualmente.

- Os ranges vão em paralelo; a falha de um não derruba os outros (fica em ``errors``).
- Cache curto (``THEME_RANGE_TTL``) por range, single-flight; falha não é cacheada.
- ``as_of`` é o instante da consulta mais antiga entre as usadas: é o fim das janelas
  móveis (com o cache, pode ser até ``THEME_RANGE_TTL`` antes de agora).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from gobus_mcp.analytics.themes import ThemeRange, WindowPair
from gobus_mcp.cache import TTLCache
from gobus_mcp.client import GobusGraphQLClient

THEME_RANGE_TTL = 300.0  # 5 min

_THEME_RANGE_QUERY = """
query ThemeRangeCounts($days: Int!) {
  topThemes(range: {days: $days}, limit: 100) {
    label
    count
  }
  analyticsKpis(range: {days: $days}) {
    total
  }
}
"""


@dataclass(frozen=True)
class ThemeRangeFetch:
    """Ranges consultados (por ``days``), erros por range e o fim das janelas móveis."""

    ranges: Mapping[int, ThemeRange]
    errors: Mapping[int, str]
    as_of: datetime

    def pair(self, window_days: int, including_days: int) -> WindowPair | None:
        """A janela e o range que a inclui; ``None`` se algum dos dois falhou."""
        window = self.ranges.get(window_days)
        including = self.ranges.get(including_days)
        if window is None or including is None:
            return None
        return WindowPair(window, including)

    def error_text(self) -> str:
        """Erros resumidos para mensagens (``"21 dias: timeout; 28 dias: 503"``)."""
        return "; ".join(f"{days} dias: {msg}" for days, msg in sorted(self.errors.items()))


async def fetch_theme_ranges(
    client: GobusGraphQLClient,
    days: Iterable[int],
    *,
    now: datetime,
    cache: TTLCache | None = None,
    ttl: float = THEME_RANGE_TTL,
) -> ThemeRangeFetch:
    """Consulta cada range de ``days`` em paralelo. ``now`` é o instante registrado da
    consulta (injetável nos testes)."""
    wanted = sorted(set(days))

    async def one(d: int) -> tuple[datetime, dict]:
        async def load() -> tuple[datetime, dict]:
            data = await client.execute(_THEME_RANGE_QUERY, {"days": d})
            return now, data

        if cache is None:
            return await load()
        return await cache.get_or_load(("theme_range", d), load, ttl)

    results = await asyncio.gather(*(one(d) for d in wanted), return_exceptions=True)
    ranges: dict[int, ThemeRange] = {}
    errors: dict[int, str] = {}
    stamps: list[datetime] = []
    for d, result in zip(wanted, results, strict=True):
        if isinstance(result, BaseException):
            errors[d] = str(result) or type(result).__name__
            continue
        fetched_at, data = result
        ranges[d] = ThemeRange.from_response(d, data or {})
        stamps.append(fetched_at)
    return ThemeRangeFetch(ranges=ranges, errors=errors, as_of=min(stamps) if stamps else now)
