"""Entidades genéricas: ocultas por padrão na rede e nas relacionadas do perfil."""

import dataclasses

import pytest

from gobus_mcp.analytics.generic_entities import (
    GENERIC_ENTITIES,
    GenericEntity,
    generic_ids,
    split_generic,
)


def test_lista_curada_cobre_pais_dateline_emissor_e_boilerplate():
    by_id = {g.entity_id: g for g in GENERIC_ENTITIES}
    assert set(by_id) == {"Q155", "Q2844", "Q5440531", "dgb_portal-gov-br"}
    assert by_id["Q155"].kind == "country"
    assert by_id["Q2844"].kind == "dateline"
    assert by_id["Q5440531"].kind == "issuer"
    assert by_id["dgb_portal-gov-br"].kind == "boilerplate"


def test_motivo_traz_contagem_e_data_da_conferencia():
    for generic in GENERIC_ENTITIES:
        assert "21/10/2026" in generic.reason, generic.entity_id
        assert any(ch.isdigit() for ch in generic.reason.replace("21/10/2026", ""))
    by_id = {g.entity_id: g for g in GENERIC_ENTITIES}
    assert "63.871" in by_id["Q155"].reason


def test_portal_gov_br_fica_marcado_para_revisao():
    by_id = {g.entity_id: g for g in GENERIC_ENTITIES}
    assert by_id["dgb_portal-gov-br"].review is True
    assert not by_id["Q155"].review


def test_generic_entity_e_imutavel():
    generic = GENERIC_ENTITIES[0]
    assert isinstance(generic, GenericEntity)
    with pytest.raises(dataclasses.FrozenInstanceError):
        generic.name = "outro"  # type: ignore[misc]


def test_generic_ids_e_so_a_lista_curada():
    assert generic_ids() == frozenset({"Q155", "Q2844", "Q5440531", "dgb_portal-gov-br"})


def test_entidades_das_agencias_nao_sao_genericas():
    """Ministérios e secretarias (``dgb_{code}``) são vizinhos com sentido na rede e no
    perfil; a exclusão deles só vale na coerência (``coherence.excluded_entities``)."""
    ids = generic_ids()
    for agency_self in ("dgb_saude", "dgb_secretariageral", "dgb_fazenda", "dgb_planalto"):
        assert agency_self not in ids


def test_generic_ids_mantem_ufs_capitais_ministerios_e_pessoas():
    ids = generic_ids()
    assert "dgb_pe-de-meia" not in ids
    assert "dgb_ceara" not in ids  # UF sem QID continua visível
    assert "Q119158" not in ids  # Distrito Federal (UF)
    assert "Q4294522" not in ids  # MEC (QID do ministério)
    assert "Q37181" not in ids  # pessoas


def test_split_generic_separa_preservando_a_ordem():
    rows = [
        {"canonicalId": "Q4294522", "weight": 650},
        {"canonicalId": "Q155", "weight": 341},
        {"canonicalId": "Q5419278", "weight": 306},
        {"canonicalId": "dgb_portal-gov-br", "weight": 139},
    ]
    kept, hidden = split_generic(rows, generic_ids())
    assert [r["canonicalId"] for r in kept] == ["Q4294522", "Q5419278"]
    assert [r["canonicalId"] for r in hidden] == ["Q155", "dgb_portal-gov-br"]


def test_split_generic_aceita_entity_id():
    rows = [{"entityId": "Q2844"}, {"entityId": "Q1"}]
    kept, hidden = split_generic(rows, generic_ids())
    assert kept == [{"entityId": "Q1"}]
    assert hidden == [{"entityId": "Q2844"}]
