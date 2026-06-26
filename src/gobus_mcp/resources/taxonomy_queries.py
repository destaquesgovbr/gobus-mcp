TAXONOMY_QUERIES: dict[str, list[str]] = {
    "Saúde": ["saúde pública", "SUS", "vacinação", "hospital", "medicamento"],
    "Educação": ["educação", "escola", "universidade", "ENEM", "bolsa estudo"],
    "Meio Ambiente e Sustentabilidade": ["COP30", "clima", "desmatamento", "carbono", "amazônia"],
    "Esportes e Lazer": ["Copa", "Olimpíadas", "atleta", "jogos", "futebol"],
    "Economia e Finanças": ["inflação", "IPCA", "PIB", "juros", "orçamento federal"],
    "Infraestrutura e Transporte": ["obra", "rodovia", "ferrovia", "porto", "PAC"],
    "Segurança Pública": ["segurança pública", "polícia federal", "crime", "violência"],
    "Ciência e Tecnologia": ["pesquisa", "inovação", "CNPq", "CAPES", "startup"],
    "Agricultura e Agronegócio": ["agronegócio", "colheita", "safra", "MAPA", "reforma agrária"],
    "Previdência e Assistência Social": ["INSS", "aposentadoria", "Bolsa Família", "BPC", "previdência"],
    "Trabalho e Emprego": ["emprego", "CAGED", "carteira de trabalho", "salário mínimo", "trabalhador"],
    "Relações Exteriores": ["diplomacia", "acordo bilateral", "Itamaraty", "MERCOSUL", "embaixada"],
    "Minorias e Grupos Especiais": ["indígena", "quilombola", "pessoa com deficiência", "LGBTQIA+", "igualdade racial"],
    "Turismo": ["turismo", "viagem", "hospedagem", "destino turístico", "Embratur"],
    "Defesa Nacional": ["Forças Armadas", "Exército", "Marinha", "Aeronáutica", "defesa nacional"],
}


async def fetch_taxonomy_queries() -> str:
    lines = [
        "# Dicionário de Termos por Categoria Taxonômica\n",
        "Use em `gobus_search_news` para buscar artigos de cada categoria detectada por `gobus_detect_trends`.\n",
    ]
    for category, terms in TAXONOMY_QUERIES.items():
        terms_str = " · ".join(f'`{t}`' for t in terms)
        lines.append(f"## {category}\n{terms_str}\n")
    return "\n".join(lines)
