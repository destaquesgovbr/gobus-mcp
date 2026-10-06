"""Catálogo de agências: códigos, nomes humanos, republicadoras, validação e ativas."""

from datetime import date

import pytest

from gobus_mcp.agency_catalog import Agency, AgencyCatalog
from gobus_mcp.cache import TTLCache
from tests.conftest import FakeGraphQLClient

TODAY = date(2026, 10, 5)

_CATALOG = [
    ("saude", False, "Ministério da Saúde"),
    ("mec", False, "Ministério da Educação"),
    ("trabalho-e-emprego", False, "Ministério do Trabalho e Emprego"),
    ("mds", False, "Ministério do Desenvolvimento e Assistência Social"),
    ("mast", False, "Museu de Astronomia e Ciências Afins"),
    ("cgu", False, "Controladoria-Geral da União"),
    ("pf", False, "Polícia Federal"),
    ("susep", False, None),  # sem nome no analytics → cai no código
    ("agencia_brasil", True, "Agência Brasil"),
    ("tvbrasil", True, "TV Brasil"),
    ("ebc", True, "EBC"),
]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _client(*, names_error: Exception | None = None) -> FakeGraphQLClient:
    client = FakeGraphQLClient()
    client.route(
        "CatalogAgencies",
        {"agencies": [{"code": c, "isRepublisher": r} for c, r, _ in _CATALOG]},
    )
    client.route(
        "CatalogAgencyNames",
        names_error
        or (
            lambda v: {
                "agencyAnalytics": [
                    {"agencyKey": c, "agencyName": n}
                    for c, _, n in _CATALOG
                    if c in v["agencies"] and c != "susep"
                ]
                + [{"agencyKey": "susep", "agencyName": None}]
            }
        ),
    )
    client.route(
        "CatalogTopAgencies",
        lambda v: {
            "topAgencies": [
                {"name": n, "count": 100 - i}
                for i, n in enumerate(["agencia_brasil", "pf", "tvbrasil", "mdr", "mec", "saude"])
            ][: v["limit"]]
        },
    )
    return client


def _catalog(client, clock=None) -> AgencyCatalog:
    cache = TTLCache(clock=clock or Clock())
    return AgencyCatalog(client, cache=cache, today=lambda: TODAY)


async def test_all_traz_codigos_nomes_e_republicadoras():
    catalog = _catalog(_client())
    agencies = await catalog.all()
    assert Agency("saude", "Ministério da Saúde", False) in agencies
    assert Agency("agencia_brasil", "Agência Brasil", True) in agencies
    assert Agency("susep", "susep", False) in agencies  # nome nulo → código
    assert len(agencies) == len(_CATALOG)


async def test_nomes_vem_do_agency_analytics_de_um_dia_d_menos_1():
    client = _client()
    await _catalog(client).all()
    (variables,) = client.calls("CatalogAgencyNames")
    assert variables["date"] == "2026-10-04"
    assert sorted(variables["agencies"]) == sorted(c for c, _, _ in _CATALOG)


async def test_cache_de_24h_com_uma_busca_e_refresh_depois():
    clock = Clock()
    client = _client()
    catalog = _catalog(client, clock)

    await catalog.all()
    await catalog.name("saude")
    await catalog.republishers()
    assert len(client.calls("CatalogAgencies")) == 1
    assert len(client.calls("CatalogAgencyNames")) == 1

    clock.now += 86_400 + 1
    await catalog.all()
    assert len(client.calls("CatalogAgencies")) == 2
    assert len(client.calls("CatalogAgencyNames")) == 2


async def test_falha_nos_nomes_degrada_para_o_codigo_sem_cachear():
    client = _client(names_error=RuntimeError("timeout"))
    catalog = _catalog(client)

    assert await catalog.name("saude") == "saude"
    assert {a.code for a in await catalog.all()} == {c for c, _, _ in _CATALOG}
    assert len(client.calls("CatalogAgencyNames")) == 2  # tenta de novo na próxima


async def test_name_get_e_codes():
    catalog = _catalog(_client())
    assert await catalog.name("pf") == "Polícia Federal"
    assert await catalog.name("nao-existe") == "nao-existe"
    assert (await catalog.get("mec")).name == "Ministério da Educação"
    assert await catalog.get("nao-existe") is None
    assert "saude" in await catalog.codes()


async def test_republicadoras_incluem_radioagencia_nacional():
    catalog = _catalog(_client())
    assert await catalog.republishers() == frozenset(
        {"agencia_brasil", "tvbrasil", "ebc", "radioagencia_nacional"}
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [("saude", "saude"), (" Saude ", "saude"), ("SAÚDE", "saude"),
     ("trabalho e emprego", "trabalho-e-emprego")],
)  # fmt: skip
async def test_validate_codigo_existente_normalizado(code, expected):
    check = await _catalog(_client()).validate(code)
    assert check.ok and check.code == expected
    assert check.suggestions == () and not check.out_of_catalog


@pytest.mark.parametrize(
    ("code", "suggestion"),
    [("ms", "saude"), ("trabalho", "trabalho-e-emprego"), ("mte", "trabalho-e-emprego")],
)  # fmt: skip
async def test_validate_aliases_curados_antes_do_difflib(code, suggestion):
    check = await _catalog(_client()).validate(code)
    assert not check.ok
    assert check.suggestions == (suggestion,)
    assert suggestion in check.message


@pytest.mark.parametrize("code", ["tcu", "camara", "senado", "ibge"])
async def test_validate_fora_do_catalogo(code):
    check = await _catalog(_client()).validate(code)
    assert not check.ok and check.out_of_catalog
    assert check.suggestions == ()
    assert "fora do catálogo" in check.message


async def test_validate_difflib_e_sem_sugestao():
    catalog = _catalog(_client())
    assert (await catalog.validate("sauder")).suggestions[0] == "saude"
    check = await catalog.validate("xyzxyz")
    assert not check.ok and check.suggestions == () and not check.out_of_catalog
    assert "gobus://agencies" in check.message


async def test_active_usa_top_agencies():
    client = _client()
    catalog = _catalog(client)
    assert await catalog.active(days=90, limit=3) == ["agencia_brasil", "pf", "tvbrasil"]
    assert client.calls("CatalogTopAgencies") == [{"days": 90, "limit": 3}]


async def test_active_sem_republicadoras_completa_o_limite():
    catalog = _catalog(_client())
    assert await catalog.active(days=30, limit=3, include_republishers=False) == [
        "pf",
        "mdr",
        "mec",
    ]


async def test_display_name_prefere_o_catalogo_e_nunca_levanta():
    catalog = _catalog(_client())
    assert await catalog.display_name("pf", "pf") == "Polícia Federal"
    assert await catalog.display_name("susep", "Superintendência de Seguros") == (
        "Superintendência de Seguros"  # catálogo sem nome → nome da API
    )
    assert await catalog.display_name("nao-existe") == "nao-existe"
    assert await catalog.display_name("", "Sem código") == "Sem código"

    broken = FakeGraphQLClient()
    broken.route("CatalogAgencies", RuntimeError("graphql fora do ar"))
    fallback = _catalog(broken)
    assert await fallback.display_name("pf", "Polícia Federal (API)") == "Polícia Federal (API)"
    assert await fallback.display_name("pf") == "pf"


async def test_display_names_resolve_o_mapa_uma_vez_e_nunca_levanta():
    catalog = _catalog(_client())
    names = await catalog.display_names()
    assert names["pf"] == "Polícia Federal"
    assert "susep" not in names  # sem nome no catálogo: quem exibe usa o fallback

    broken = FakeGraphQLClient()
    broken.route("CatalogAgencies", RuntimeError("graphql fora do ar"))
    assert await _catalog(broken).display_names() == {}
