"""Compatibilidade com versões da graphql-api que ainda não têm um campo novo.

O gobus pode ir para produção antes do PR da graphql-api que cria os campos que ele usa
(ou a API pode voltar para uma revisão anterior). Cada uso de campo novo fica atrás de
uma **feature** com duas queries: a nova e a antiga (``*_LEGACY_QUERY``, nome de operação
com o sufixo ``Legacy``). ``execute_compatible`` tenta a nova; se a API responde com erro de
schema ("Cannot query field", argumento, tipo ou valor de enum desconhecido), a feature
fica marcada como ausente por ``FEATURE_TTL`` (1 h) e a antiga responde. Durante essa hora
as chamadas vão direto para a antiga; depois, a nova é tentada de novo (o deploy da API
pode ter entrado).

Outros erros propagam sem marcar nada. O estado é por processo (``COMPAT``), como o
cache: o Cloud Run roda uma instância por vez.

Features em uso (GQL-1, graphql-api#32):

- ``ARTICLE_SUMMARY_URL``: ``ArticleSummary.url`` (links nos top artigos dos temas);
- ``RELATED_LIFT``: ``relatedEntities(orderBy:, minWeight:)`` com ``lift``/``articleCount``;
- ``FLESCH_PTBR``: ``readabilityFleschPtbr``, ``avgReadabilityFleschPtbr`` e
  ``readabilityFleschPtbrCount``.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

from gobus_mcp.client import GobusGraphQLClient, GobusGraphQLError

logger = logging.getLogger(__name__)

FEATURE_TTL = 3_600.0  # 1 h

ARTICLE_SUMMARY_URL = "article_summary_url"
RELATED_LIFT = "related_lift"
FLESCH_PTBR = "flesch_ptbr"

# Mensagens de validação do graphql-core quando o documento cita algo que o schema não tem.
_MISMATCH_RE = re.compile(
    r"Cannot query field|Unknown argument|Unknown type|does not exist in '\w+' enum"
    r"|Enum '\w+' cannot represent",
)


def is_schema_mismatch(exc: BaseException) -> bool:
    """Erro da GraphQL causado por campo, argumento, tipo ou valor de enum desconhecido."""
    if not isinstance(exc, GobusGraphQLError):
        return False
    return any(_MISMATCH_RE.search(str(e.get("message") or e)) for e in exc.errors)


class SchemaCompat:
    """Features ausentes na graphql-api, cada uma por ``ttl`` segundos (relógio injetável)."""

    def __init__(
        self, *, ttl: float = FEATURE_TTL, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._absent_until: dict[str, float] = {}

    def available(self, feature: str) -> bool:
        """``False`` enquanto a feature estiver marcada como ausente."""
        until = self._absent_until.get(feature)
        if until is None:
            return True
        if until <= self._clock():
            del self._absent_until[feature]
            return True
        return False

    def mark_absent(self, feature: str) -> None:
        self._absent_until[feature] = self._clock() + self._ttl

    def reset(self) -> None:
        """Esquece as ausências (testes)."""
        self._absent_until.clear()


COMPAT = SchemaCompat()


async def execute_compatible(
    client: GobusGraphQLClient,
    feature: str,
    query: str,
    legacy_query: str,
    variables: dict | None = None,
    *,
    compat: SchemaCompat | None = None,
    legacy_variables: dict | None = None,
    timeout: float | None = None,
) -> tuple[dict, bool]:
    """``(data, True)`` com a query nova ou ``(data, False)`` com a antiga.

    ``legacy_variables`` substitui ``variables`` na antiga (quando a nova tem variáveis que
    a antiga não declara). Erro que não é de schema propaga.
    """
    compat = compat or COMPAT
    kwargs = {"timeout": timeout} if timeout is not None else {}
    if compat.available(feature):
        try:
            return await client.execute(query, variables, **kwargs), True
        except GobusGraphQLError as exc:
            if not is_schema_mismatch(exc):
                raise
            compat.mark_absent(feature)
            logger.warning(
                "graphql-api sem a feature %s (%s): query antiga por %.0f s",
                feature,
                exc,
                FEATURE_TTL,
            )
    old_vars = variables if legacy_variables is None else legacy_variables
    return await client.execute(legacy_query, old_vars, **kwargs), False
