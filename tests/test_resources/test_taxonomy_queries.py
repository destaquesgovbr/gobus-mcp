import pytest
from gobus_mcp.resources.taxonomy_queries import fetch_taxonomy_queries, TAXONOMY_QUERIES


class TestTaxonomyQueries:
    @pytest.mark.asyncio
    async def test_retorna_markdown(self):
        result = await fetch_taxonomy_queries()
        assert isinstance(result, str)
        assert "##" in result

    def test_categorias_tem_pelo_menos_3_termos(self):
        for cat, terms in TAXONOMY_QUERIES.items():
            assert len(terms) >= 3, f"Categoria '{cat}' tem menos de 3 termos"

    def test_saude_e_educacao_presentes(self):
        assert "Saúde" in TAXONOMY_QUERIES
        assert "Educação" in TAXONOMY_QUERIES

    @pytest.mark.asyncio
    async def test_output_contem_saude(self):
        result = await fetch_taxonomy_queries()
        assert "Saúde" in result
