"""Domínios de política (os 7 de ``policies.domain`` + OTHER), aliases PT e mapas curados."""

import pytest

from gobus_mcp.domains import (
    AGENCY_DOMAIN,
    DOMAIN_LABELS,
    DOMAIN_ORDER,
    THEME_DOMAIN,
    Domain,
    agency_domain,
    domain_options,
    entity_domain,
    parse_domain,
    theme_domain,
)

# As 25 labels L1 vivas (``themes`` da graphql-api em 05/10/2026).
L1_LABELS = [
    "Economia e Finanças",
    "Segurança Pública",
    "Meio Ambiente e Sustentabilidade",
    "Saúde",
    "Educação",
    "Cultura, Artes e Patrimônio",
    "Políticas Públicas e Governança",
    "Ciência, Tecnologia e Inovação",
    "Infraestrutura e Transportes",
    "Desenvolvimento Social",
    "Justiça e Direitos Humanos",
    "Agricultura, Pecuária e Abastecimento",
    "Trabalho e Emprego",
    "Esportes e Lazer",
    "Relações Internacionais e Diplomacia",
    "Comunicações e Mídia",
    "Energia e Recursos Minerais",
    "Minorias e Grupos Especiais",
    "Turismo",
    "Habitação e Urbanismo",
    "Legislação e Regulamentação",
    "Indústria e Comércio",
    "Defesa e Forças Armadas",
    "Fiscalização e Tributação",
    "Política Econômica",
]


def test_os_7_dominios_de_policies_mais_other_em_ordem_fixa():
    # valores vivos de policies.domain (2.441 políticas em 05/10)
    assert {d.value for d in Domain} == {
        "ECONOMIC",
        "SOCIAL",
        "EDUCATION",
        "ENVIRONMENT",
        "GOVERNANCE",
        "HEALTH",
        "SECURITY",
        "OTHER",
    }
    # ordem dos gauges do anomaly-radar (integration.md §1.4)
    assert [d.value for d in DOMAIN_ORDER] == [
        "HEALTH",
        "EDUCATION",
        "SOCIAL",
        "ECONOMIC",
        "SECURITY",
        "ENVIRONMENT",
        "GOVERNANCE",
        "OTHER",
    ]
    assert set(DOMAIN_LABELS) == set(Domain)
    assert DOMAIN_LABELS[Domain.HEALTH] == "Saúde"


@pytest.mark.parametrize("empty", ["", "  ", None])
def test_parse_domain_vazio_e_sem_filtro(empty):
    assert parse_domain(empty) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("HEALTH", Domain.HEALTH),
        ("health", Domain.HEALTH),
        ("saude", Domain.HEALTH),
        ("Saúde", Domain.HEALTH),
        ("educação", Domain.EDUCATION),
        ("educacao", Domain.EDUCATION),
        ("social", Domain.SOCIAL),
        ("economia", Domain.ECONOMIC),
        ("econômico", Domain.ECONOMIC),
        ("segurança", Domain.SECURITY),
        ("seguranca_publica", Domain.SECURITY),
        ("meio ambiente", Domain.ENVIRONMENT),
        ("meio_ambiente", Domain.ENVIRONMENT),
        ("meio-ambiente", Domain.ENVIRONMENT),
        ("governança", Domain.GOVERNANCE),
        ("governo", Domain.GOVERNANCE),
        ("outros", Domain.OTHER),
        ("other", Domain.OTHER),
    ],
)
def test_parse_domain_com_aliases_pt(text, expected):
    assert parse_domain(text) is expected


def test_parse_domain_invalido_lista_as_opcoes():
    with pytest.raises(ValueError) as exc:
        parse_domain("astronomia")
    message = str(exc.value)
    assert "astronomia" in message
    for d in Domain:
        assert d.value in message
    assert "saude" in domain_options()


def test_theme_domain_cobre_as_25_labels_l1():
    assert set(THEME_DOMAIN) <= set(L1_LABELS)
    assert theme_domain("Saúde") is Domain.HEALTH
    assert theme_domain("Segurança Pública") is Domain.SECURITY
    assert theme_domain("Política Econômica") is Domain.ECONOMIC
    assert theme_domain("Meio Ambiente e Sustentabilidade") is Domain.ENVIRONMENT
    assert theme_domain("Políticas Públicas e Governança") is Domain.GOVERNANCE
    assert theme_domain("Desenvolvimento Social") is Domain.SOCIAL
    assert theme_domain("Educação") is Domain.EDUCATION
    # sem domínio de política equivalente
    assert theme_domain("Cultura, Artes e Patrimônio") is Domain.OTHER
    assert theme_domain("tema que não existe") is Domain.OTHER
    for label in L1_LABELS:
        assert isinstance(theme_domain(label), Domain)


def test_agency_domain_curado():
    assert agency_domain("saude") is Domain.HEALTH
    assert agency_domain("anvisa") is Domain.HEALTH
    assert agency_domain("mec") is Domain.EDUCATION
    assert agency_domain("inep") is Domain.EDUCATION
    assert agency_domain("pf") is Domain.SECURITY
    assert agency_domain("fazenda") is Domain.ECONOMIC
    assert agency_domain("ibama") is Domain.ENVIRONMENT
    assert agency_domain("mds") is Domain.SOCIAL
    assert agency_domain("cgu") is Domain.GOVERNANCE
    assert agency_domain("agencia_brasil") is None  # republicadora: sem domínio
    assert agency_domain("nao-existe") is None
    assert agency_domain(None) is None
    assert all(isinstance(d, Domain) and d is not Domain.OTHER for d in AGENCY_DOMAIN.values())


def test_entity_domain_policy_usa_o_dominio_da_ontologia():
    assert entity_domain("POLICY", "HEALTH", "mec") is Domain.HEALTH
    assert entity_domain("POLICY", "education", None) is Domain.EDUCATION


def test_entity_domain_policy_sem_dominio_cai_no_mapa_da_dona():
    # 983 de 2.441 políticas têm domain nulo (B8)
    assert entity_domain("POLICY", None, "saude") is Domain.HEALTH
    assert entity_domain("POLICY", "valor-desconhecido", "mec") is Domain.EDUCATION


def test_entity_domain_outros_tipos_usam_a_dona_e_o_resto_vai_para_other():
    assert entity_domain("ORG", None, "pf") is Domain.SECURITY
    assert entity_domain("EVENT", "HEALTH", "mec") is Domain.EDUCATION  # só POLICY usa domain
    assert entity_domain("PER", None, None) is Domain.OTHER
    assert entity_domain("LOC", None, "agencia_brasil") is Domain.OTHER
