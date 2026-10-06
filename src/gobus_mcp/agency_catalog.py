"""Catálogo de agências (integration.md §1.6): códigos, nomes, republicadoras e validação.

Fontes (graphql-api):
- ``agencies { code isRepublisher }`` — o ``label`` da API é igual ao código (156/156);
- nomes humanos via ``agencyAnalytics(todas, dateFrom = dateTo = D−1, DAY)`` — o CTE de
  nomes lê o histórico inteiro, então um único dia traz os 156 nomes em ~1 s;
- ``topAgencies(range:{days}, limit)`` para as agências mais ativas.

Cache de 24 h (single-flight). Se a busca de nomes falhar, o catálogo segue com o código
como nome e tenta de novo na próxima chamada (a falha não é cacheada).

Consumidores: F5 exclui ``dgb_{code}`` com ``code ∈ codes()``; F3 usa ``republishers()``
e ``codes()``; F4 usa ``name()`` e ``is_republisher``.
"""

from __future__ import annotations

import difflib
import logging
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from gobus_mcp.cache import TTLCache
from gobus_mcp.calendario import reference_date
from gobus_mcp.client import GobusGraphQLClient

logger = logging.getLogger(__name__)

_AGENCIES_QUERY = """
query CatalogAgencies {
  agencies {
    code
    isRepublisher
  }
}
"""

_AGENCY_NAMES_QUERY = """
query CatalogAgencyNames($agencies: [String!]!, $date: String!) {
  agencyAnalytics(agencies: $agencies, dateFrom: $date, dateTo: $date, granularity: DAY) {
    agencyKey
    agencyName
  }
}
"""

_TOP_AGENCIES_QUERY = """
query CatalogTopAgencies($days: Int!, $limit: Int!) {
  topAgencies(range: {days: $days}, limit: $limit) {
    name
    count
  }
}
"""

# Republicadoras que não vêm marcadas em ``isRepublisher``.
EXTRA_REPUBLISHERS: frozenset[str] = frozenset({"radioagencia_nacional"})

# Aliases curados, aplicados ANTES do difflib (que erra: ms→mds/mast, tcu→cgu, …).
# Valor None = órgão conhecido que não faz parte do catálogo.
ALIASES: Mapping[str, str | None] = {
    "ms": "saude",
    "trabalho": "trabalho-e-emprego",
    "mte": "trabalho-e-emprego",
    "tcu": None,
    "camara": None,
    "senado": None,
    "ibge": None,
}

OUT_OF_CATALOG_NAMES: Mapping[str, str] = {
    "tcu": "Tribunal de Contas da União",
    "camara": "Câmara dos Deputados",
    "senado": "Senado Federal",
    "ibge": "IBGE",
}

DEFAULT_TTL = 86_400.0  # 24 h
ACTIVE_TTL = 3_600.0  # 1 h


@dataclass(frozen=True)
class Agency:
    code: str
    name: str
    is_republisher: bool


@dataclass(frozen=True)
class AgencyCheck:
    """Resultado de ``validate``: ``code`` é a entrada normalizada."""

    ok: bool
    code: str
    suggestions: tuple[str, ...] = ()
    out_of_catalog: bool = False
    message: str = ""


def normalize_code(code: str) -> str:
    """Minúsculas, sem acento e com hífen no lugar de espaços (``"Saúde" → "saude"``)."""
    text = unicodedata.normalize("NFKD", code.strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "-".join(text.split())


class AgencyCatalog:
    """Catálogo de agências com cache de 24 h. ``today`` injetável (padrão: D em BRT)."""

    def __init__(
        self,
        client: GobusGraphQLClient,
        *,
        cache: TTLCache | None = None,
        ttl: float = DEFAULT_TTL,
        active_ttl: float = ACTIVE_TTL,
        today: Callable[[], date] = reference_date,
    ) -> None:
        self._client = client
        self._cache = cache or TTLCache()
        self._ttl = ttl
        self._active_ttl = active_ttl
        self._today = today

    # ── carga ────────────────────────────────────────────────────────────────

    async def _agency_rows(self) -> list[dict]:
        async def load() -> list[dict]:
            data = await self._client.execute(_AGENCIES_QUERY)
            return [a for a in data.get("agencies") or [] if a.get("code")]

        return await self._cache.get_or_load(("catalog", "agencies"), load, self._ttl)

    async def _names(self, codes: list[str]) -> dict[str, str]:
        async def load() -> dict[str, str]:
            day = (self._today() - timedelta(days=1)).isoformat()
            data = await self._client.execute(_AGENCY_NAMES_QUERY, {"agencies": codes, "date": day})
            return {
                row["agencyKey"]: row["agencyName"]
                for row in data.get("agencyAnalytics") or []
                if row.get("agencyKey") and row.get("agencyName")
            }

        try:
            return await self._cache.get_or_load(("catalog", "names"), load, self._ttl)
        except Exception as exc:  # degrada: nome = código, sem cachear a falha
            logger.warning("catálogo: nomes de agências indisponíveis (%s)", exc)
            return {}

    # ── consulta ─────────────────────────────────────────────────────────────

    async def all(self) -> list[Agency]:
        """Todas as agências do catálogo, ordenadas por código."""
        rows = await self._agency_rows()
        names = await self._names([r["code"] for r in rows])
        return sorted(
            (
                Agency(
                    code=r["code"],
                    name=names.get(r["code"]) or r["code"],
                    is_republisher=bool(r.get("isRepublisher")),
                )
                for r in rows
            ),
            key=lambda a: a.code,
        )

    async def get(self, code: str) -> Agency | None:
        return next((a for a in await self.all() if a.code == code), None)

    async def name(self, code: str) -> str:
        """Nome humano; o próprio código se desconhecido."""
        agency = await self.get(code)
        return agency.name if agency else code

    async def display_names(self) -> dict[str, str]:
        """``{código: nome}`` das agências com nome no catálogo; ``{}`` se o catálogo está
        fora do ar (**nunca levanta**).

        Para exibir muitas linhas, resolva o mapa uma vez e use
        ``names.get(code) or fallback or code``: a falha do catálogo não é cacheada, e
        resolver linha a linha repetiria a consulta (e o timeout) a cada linha.
        """
        try:
            agencies = await self.all()
        except Exception as exc:  # exibição não pode derrubar a tool
            logger.warning("catálogo indisponível para nomes de exibição (%s)", exc)
            return {}
        return {a.code: a.name for a in agencies if a.name != a.code}

    async def display_name(self, code: str | None, fallback: str | None = None) -> str:
        """Nome para exibição que **nunca levanta**: o do catálogo; se o catálogo não tem
        nome (ou está fora do ar), ``fallback`` (ex.: ``agencyName`` da API); senão o código.
        """
        if not code:
            return fallback or ""
        return (await self.display_names()).get(code) or fallback or code

    async def codes(self) -> frozenset[str]:
        return frozenset(r["code"] for r in await self._agency_rows())

    async def republishers(self) -> frozenset[str]:
        """``isRepublisher`` ∪ ``EXTRA_REPUBLISHERS``."""
        rows = await self._agency_rows()
        return frozenset(r["code"] for r in rows if r.get("isRepublisher")) | EXTRA_REPUBLISHERS

    async def validate(self, code: str) -> AgencyCheck:
        """Confere o código: aliases curados primeiro, depois ``difflib``."""
        normalized = normalize_code(code)
        codes = await self.codes()
        if normalized in codes:
            return AgencyCheck(ok=True, code=normalized)

        if normalized in ALIASES:
            target = ALIASES[normalized]
            if target is None:
                label = OUT_OF_CATALOG_NAMES.get(normalized, normalized)
                return AgencyCheck(
                    ok=False,
                    code=normalized,
                    out_of_catalog=True,
                    message=(
                        f"'{normalized}' ({label}) está fora do catálogo do Destaques Gov.BR, "
                        "que reúne as notícias dos órgãos publicadas no gov.br."
                    ),
                )
            if target in codes:
                return AgencyCheck(
                    ok=False,
                    code=normalized,
                    suggestions=(target,),
                    message=f"Agência '{normalized}' não encontrada. Você quis dizer '{target}'?",
                )

        suggestions = tuple(difflib.get_close_matches(normalized, sorted(codes), n=3, cutoff=0.6))
        if suggestions:
            options = ", ".join(f"'{s}'" for s in suggestions)
            message = f"Agência '{normalized}' não encontrada. Você quis dizer {options}?"
        else:
            message = (
                f"Agência '{normalized}' não encontrada. Consulte gobus://agencies "
                "para a lista de códigos."
            )
        return AgencyCheck(ok=False, code=normalized, suggestions=suggestions, message=message)

    async def active(
        self, days: int = 90, limit: int = 20, *, include_republishers: bool = True
    ) -> list[str]:
        """Códigos das agências com mais artigos nos últimos ``days`` dias."""
        republishers = frozenset() if include_republishers else await self.republishers()
        fetch_limit = limit + len(republishers)

        async def load() -> list[dict]:
            data = await self._client.execute(
                _TOP_AGENCIES_QUERY, {"days": days, "limit": fetch_limit}
            )
            return data.get("topAgencies") or []

        rows = await self._cache.get_or_load(
            ("catalog", "active", days, fetch_limit), load, self._active_ttl
        )
        keys = [r["name"] for r in rows if r.get("name") and r["name"] not in republishers]
        return keys[:limit]
