"""Domínios de política pública: os 7 valores de ``policies.domain`` mais ``OTHER``.

Usados pelo ``domain_filter`` do ``gobus_detect_anomalies`` e pelos gauges do app
``ui://anomaly-radar`` (um por domínio, em ``DOMAIN_ORDER``).

Atribuição (integration.md §1.1; verificação B8):
- tema: ``THEME_DOMAIN`` (as 25 labels L1 vivas); sem equivalente → ``OTHER``;
- entidade POLICY: ``policyDetails.domain`` (983 de 2.441 vêm nulos);
- demais entidades, ou POLICY sem domínio: o mapa da agência dona (``AGENCY_DOMAIN``,
  curado e **parcial**); sem dona ou sem mapa → ``OTHER``.

Enums em inglês ASCII; rótulos PT só em texto (``DOMAIN_LABELS``).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from enum import StrEnum


class Domain(StrEnum):
    HEALTH = "HEALTH"
    EDUCATION = "EDUCATION"
    SOCIAL = "SOCIAL"
    ECONOMIC = "ECONOMIC"
    SECURITY = "SECURITY"
    ENVIRONMENT = "ENVIRONMENT"
    GOVERNANCE = "GOVERNANCE"
    OTHER = "OTHER"


# Ordem fixa dos gauges (``AnomalyReport.domains``).
DOMAIN_ORDER: tuple[Domain, ...] = (
    Domain.HEALTH,
    Domain.EDUCATION,
    Domain.SOCIAL,
    Domain.ECONOMIC,
    Domain.SECURITY,
    Domain.ENVIRONMENT,
    Domain.GOVERNANCE,
    Domain.OTHER,
)

DOMAIN_LABELS: Mapping[Domain, str] = {
    Domain.HEALTH: "Saúde",
    Domain.EDUCATION: "Educação",
    Domain.SOCIAL: "Social",
    Domain.ECONOMIC: "Economia",
    Domain.SECURITY: "Segurança",
    Domain.ENVIRONMENT: "Meio ambiente",
    Domain.GOVERNANCE: "Governança",
    Domain.OTHER: "Outros",
}

# Aliases (normalizados: minúsculas, sem acento, "_" no lugar de espaço e hífen).
_ALIASES: Mapping[str, Domain] = {
    "saude": Domain.HEALTH,
    "educacao": Domain.EDUCATION,
    "ensino": Domain.EDUCATION,
    "social": Domain.SOCIAL,
    "assistencia_social": Domain.SOCIAL,
    "desenvolvimento_social": Domain.SOCIAL,
    "economia": Domain.ECONOMIC,
    "economico": Domain.ECONOMIC,
    "economica": Domain.ECONOMIC,
    "seguranca": Domain.SECURITY,
    "seguranca_publica": Domain.SECURITY,
    "defesa": Domain.SECURITY,
    "meio_ambiente": Domain.ENVIRONMENT,
    "ambiente": Domain.ENVIRONMENT,
    "ambiental": Domain.ENVIRONMENT,
    "governanca": Domain.GOVERNANCE,
    "governo": Domain.GOVERNANCE,
    "gestao": Domain.GOVERNANCE,
    "outros": Domain.OTHER,
    "outro": Domain.OTHER,
}

# As 25 labels L1 da taxonomia (``themes`` em 05/10/2026). Sem equivalente nos domínios de
# política: Cultura, Ciência e Tecnologia, Comunicações e Relações Internacionais (→ OTHER).
THEME_DOMAIN: Mapping[str, Domain] = {
    "Saúde": Domain.HEALTH,
    "Educação": Domain.EDUCATION,
    "Desenvolvimento Social": Domain.SOCIAL,
    "Trabalho e Emprego": Domain.SOCIAL,
    "Minorias e Grupos Especiais": Domain.SOCIAL,
    "Justiça e Direitos Humanos": Domain.SOCIAL,
    "Habitação e Urbanismo": Domain.SOCIAL,
    "Esportes e Lazer": Domain.SOCIAL,
    "Economia e Finanças": Domain.ECONOMIC,
    "Política Econômica": Domain.ECONOMIC,
    "Agricultura, Pecuária e Abastecimento": Domain.ECONOMIC,
    "Indústria e Comércio": Domain.ECONOMIC,
    "Infraestrutura e Transportes": Domain.ECONOMIC,
    "Energia e Recursos Minerais": Domain.ECONOMIC,
    "Turismo": Domain.ECONOMIC,
    "Fiscalização e Tributação": Domain.ECONOMIC,
    "Segurança Pública": Domain.SECURITY,
    "Defesa e Forças Armadas": Domain.SECURITY,
    "Meio Ambiente e Sustentabilidade": Domain.ENVIRONMENT,
    "Políticas Públicas e Governança": Domain.GOVERNANCE,
    "Legislação e Regulamentação": Domain.GOVERNANCE,
}


def _agencies(domain: Domain, *codes: str) -> dict[str, Domain]:
    return dict.fromkeys(codes, domain)


# Mapa curado agência → domínio (códigos do catálogo em 05/10/2026). Parcial de propósito:
# cultura, ciência e tecnologia, comunicação (inclusive as republicadoras) e relações
# exteriores ficam sem domínio (→ OTHER).
AGENCY_DOMAIN: Mapping[str, Domain] = {
    **_agencies(
        Domain.HEALTH,
        "saude",
        "anvisa",
        "ans",
        "ebserh",
        "inca",
        "aids",
        "conitec",
        "conselho-nacional-de-saude",
        "hfa",
    ),
    **_agencies(Domain.EDUCATION, "mec", "inep", "fnde", "capes", "ines", "ibc"),
    **_agencies(
        Domain.SOCIAL,
        "mds",
        "inss",
        "previdencia",
        "mdh",
        "mulheres",
        "igualdaderacial",
        "funai",
        "palmares",
        "trabalho-e-emprego",
        "fundacentro",
        "cidades",
        "incra",
        "esporte",
    ),
    **_agencies(
        Domain.ECONOMIC,
        "fazenda",
        "receitafederal",
        "tesouronacional",
        "pgfn",
        "cvm",
        "susep",
        "previc",
        "coaf",
        "cade",
        "mdic",
        "empresas-e-negocios",
        "memp",
        "planejamento",
        "agricultura",
        "mda",
        "mpa",
        "mme",
        "aneel",
        "anp",
        "anm",
        "inmetro",
        "inpi",
        "propriedade-intelectual",
        "suframa",
        "sudam",
        "sudene",
        "sudeco",
        "mdr",
        "transportes",
        "portos-e-aeroportos",
        "antt",
        "antaq",
        "anac",
        "dnit",
        "turismo",
        "nfse",
    ),
    **_agencies(
        Domain.SECURITY,
        "pf",
        "prf",
        "mj",
        "defesa",
        "gsi",
        "abin",
        "senappen",
        "esg",
        "esd",
        "censipam",
    ),
    **_agencies(
        Domain.ENVIRONMENT, "mma", "ibama", "icmbio", "ana", "florestal", "jbrj", "cemaden"
    ),
    **_agencies(
        Domain.GOVERNANCE,
        "gestao",
        "cgu",
        "casacivil",
        "secom",
        "planalto",
        "secretariageral",
        "sri",
        "agu",
        "acessoainformacao",
        "ouvidorias",
        "corregedorias",
        "governodigital",
        "servidor",
        "compras",
        "pncp",
        "transferegov",
        "imprensanacional",
        "servicoscompartilhados",
        "iti",
        "anpd",
    ),
}


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.strip().lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return "_".join(folded.replace("-", " ").split())


def domain_options() -> str:
    """Texto com os valores aceitos (enums e aliases PT principais)."""
    return (
        ", ".join(d.value for d in DOMAIN_ORDER)
        + " (ou em português: saude, educacao, social, economia, seguranca, meio_ambiente, "
        "governanca, outros)"
    )


def parse_domain(value: str | None) -> Domain | None:
    """``domain_filter`` → ``Domain``; vazio = sem filtro (``None``).

    Aceita o enum (qualquer caixa) e aliases PT. Valor inválido levanta ``ValueError`` com
    as opções (a tool devolve a mensagem ao usuário).
    """
    if value is None or not value.strip():
        return None
    key = _normalize(value)
    upper = key.upper()
    if upper in Domain.__members__:
        return Domain[upper]
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError(f"Domínio '{value.strip()}' inválido. Opções: {domain_options()}.")


def theme_domain(label: str) -> Domain:
    """Domínio de uma label L1 de tema (``OTHER`` sem equivalente)."""
    return THEME_DOMAIN.get(label, Domain.OTHER)


def agency_domain(code: str | None) -> Domain | None:
    """Domínio curado da agência; ``None`` se não mapeada."""
    return AGENCY_DOMAIN.get(code) if code else None


def entity_domain(
    entity_type: str | None, policy_domain: str | None, owner_key: str | None
) -> Domain:
    """Domínio de uma entidade: POLICY usa ``policyDetails.domain``; o resto (e POLICY sem
    domínio válido) usa o mapa da agência dona; sem mapa → ``OTHER``."""
    if (entity_type or "").upper() == "POLICY" and policy_domain:
        upper = policy_domain.strip().upper()
        if upper in Domain.__members__:
            return Domain[upper]
    return agency_domain(owner_key) or Domain.OTHER
