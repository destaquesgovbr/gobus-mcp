"""Entidades genéricas: ocultas por padrão na rede de entidades e nas relacionadas do perfil.

São entidades que co-ocorrem com quase tudo no acervo e por isso dominam os pesos de
co-menção sem dizer nada sobre o foco: o país, a dateline/sede do governo, o próprio
emissor e o boilerplate de serviço ou de publicação (o DOU). Critério para entrar: volume
alto e lift ≤ 1 (co-menção não acima do acaso, ``weight / (n_foco · n_genérica / total)``)
nas entidades conferidas. Ocultar não perde informação: a linha "Ocultas como genéricas"
mostra cada uma com o peso, e ``include_generic=true`` traz de volta.

Continuam visíveis: as UFs (inclusive o Distrito Federal, ``Q119158``), as demais
capitais, os ministérios (pelo QID ou pela entidade da própria agência, ``dgb_{code}``:
Secretaria-Geral, Fazenda, Casa Civil… são vizinhos com sentido) e as pessoas. A exclusão
das ``dgb_{code}`` fica só na coerência (``coherence.excluded_entities``). A lista é curada
à mão; as contagens no ``reason`` são o ``entitySearch.articleCount`` conferido em
21/10/2026.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

GenericKind = Literal["country", "dateline", "issuer", "boilerplate"]


@dataclass(frozen=True)
class GenericEntity:
    """Entidade genérica curada. ``review`` = classificação ainda em revisão."""

    entity_id: str
    name: str
    kind: GenericKind
    reason: str
    review: bool = False


GENERIC_ENTITIES: tuple[GenericEntity, ...] = (
    GenericEntity(
        "Q155",
        "Brasil",
        "country",
        "o país do acervo inteiro: 63.871 artigos (conferido em 21/10/2026)",
    ),
    GenericEntity(
        "Q2844",
        "Brasília",
        "dateline",
        "dateline e sede do governo (alias 'brasilia - df'): 33.284 artigos "
        "(conferido em 21/10/2026)",
    ),
    GenericEntity(
        "Q5440531",
        "Governo Federal",
        "issuer",
        "o próprio emissor (aliases União, Governo do Brasil): 12.952 artigos "
        "(conferido em 21/10/2026)",
    ),
    GenericEntity(
        "dgb_portal-gov-br",
        "Portal Gov.br",
        "boilerplate",
        "boilerplate de serviço ('acesse o gov.br'): 2.099 artigos (conferido em "
        "21/10/2026); revisar — às vezes é o serviço de fato",
        review=True,
    ),
    GenericEntity(
        "Q3712237",
        "Diário Oficial da União (DOU)",
        "boilerplate",
        "boilerplate de ato publicado ('publicado no DOU'): 11.824 artigos (conferido em "
        "21/10/2026); co-menção abaixo do esperado ao acaso (lift 0,49 com Bolsa Família, "
        "0,90 com INSS, 0,92 com MEC; fora dos 60 vizinhos do Pé-de-Meia)",
    ),
)

STATIC_GENERIC_IDS: frozenset[str] = frozenset(g.entity_id for g in GENERIC_ENTITIES)


def generic_ids() -> frozenset[str]:
    """Ids ocultos por padrão na rede e nas relacionadas do perfil: só a lista curada."""
    return STATIC_GENERIC_IDS


def _entity_id(row: dict) -> str | None:
    return row.get("canonicalId") or row.get("entityId")


def split_generic(rows: Sequence[dict], ids: frozenset[str]) -> tuple[list[dict], list[dict]]:
    """``(mantidas, ocultas)`` pela chave ``canonicalId`` (ou ``entityId``), na ordem."""
    kept: list[dict] = []
    hidden: list[dict] = []
    for row in rows:
        (hidden if _entity_id(row) in ids else kept).append(row)
    return kept, hidden
