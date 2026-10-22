import pytest

from gobus_mcp.tools.search_news import search_news
from tests.conftest import FakeGraphQLClient


def _make_article(i: int, agency_code: str = "mec", agency_name: str = "MEC") -> dict:
    return {
        "uniqueId": f"id{i}",
        "title": f"Artigo {i}",
        "agencyName": agency_name,
        "agency": agency_code,
        "publishedAt": "2026-01-01T00:00:00Z",
        "summary": "Resumo",
        "url": f"https://gov.br/{agency_code}/artigo-{i}",
        "features": {"trendingScore": 0.0, "viewCount": 0},
    }


class TestSearchNews:
    @pytest.mark.asyncio
    async def test_retorna_artigos_formatados(self):
        client = FakeGraphQLClient()
        client.set_response(
            {
                "search": {
                    "articles": [_make_article(1, "mec", "Ministério da Educação")],
                    "found": 1,
                    "page": 1,
                }
            }
        )
        result = await search_news("educação", client)
        assert "Artigo 1" in result
        assert "Ministério da Educação" in result
        assert "id1" in result

    @pytest.mark.asyncio
    async def test_sem_resultados_retorna_mensagem(self):
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("xyz_inexistente", client)
        assert "Nenhum" in result

    @pytest.mark.asyncio
    async def test_campo_agency_code_exibido(self):
        """agency code (ex: 'mec') deve aparecer no Markdown."""
        client = FakeGraphQLClient()
        client.set_response(
            {
                "search": {
                    "articles": [_make_article(1, "saude", "Ministério da Saúde")],
                    "found": 1,
                    "page": 1,
                }
            }
        )
        result = await search_news("saúde", client)
        assert "[saude]" in result

    @pytest.mark.asyncio
    async def test_date_from_passado_no_filter(self):
        """date_from deve ir para filter.startDate."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, date_from="2026-06-01")
        variables = client.execute.call_args[0][1]
        assert variables["filter"]["startDate"] == "2026-06-01T00:00:00-03:00"

    @pytest.mark.asyncio
    async def test_date_to_passado_no_filter(self):
        """date_to deve ir para filter.endDate, incluindo o dia inteiro (BRT)."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news("saúde", client, date_to="2026-06-24")
        variables = client.execute.call_args[0][1]
        assert variables["filter"]["endDate"] == "2026-06-24T23:59:59-03:00"

    @pytest.mark.asyncio
    async def test_date_filter_combinado_com_agency(self):
        """date_from + agency_key devem ir no mesmo filter."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        await search_news(
            "saúde", client, agency_key="saude", date_from="2026-06-01", date_to="2026-06-24"
        )
        variables = client.execute.call_args[0][1]
        assert "saude" in variables["filter"]["agencies"]
        assert variables["filter"]["startDate"] == "2026-06-01T00:00:00-03:00"
        assert variables["filter"]["endDate"] == "2026-06-24T23:59:59-03:00"

    @pytest.mark.asyncio
    async def test_limit_fatia_resultados_cliente(self):
        """limit deve fatiar a lista após receber a resposta do servidor."""
        client = FakeGraphQLClient()
        client.set_response(
            {
                "search": {
                    "articles": [_make_article(i) for i in range(20)],
                    "found": 20,
                    "page": 1,
                }
            }
        )
        result = await search_news("test", client, limit=5)
        assert "Artigo 0" in result
        assert "Artigo 4" in result
        assert "Artigo 5" not in result

    @pytest.mark.asyncio
    async def test_limit_cap_em_50(self):
        """limit > 50 deve ser silenciosamente capado em 50."""
        client = FakeGraphQLClient()
        client.set_response(
            {
                "search": {
                    "articles": [_make_article(i) for i in range(60)],
                    "found": 60,
                    "page": 1,
                }
            }
        )
        result = await search_news("test", client, limit=100)
        assert "Artigo 49" in result
        assert "Artigo 50" not in result

    @pytest.mark.asyncio
    async def test_hint_quando_agency_key_invalida_sem_resultados(self):
        """0 resultados com agency_key → hint para gobus://agencies."""
        client = FakeGraphQLClient()
        client.set_response({"search": {"articles": [], "found": 0, "page": 1}})
        result = await search_news("saúde", client, agency_key="invalida_xyz")
        assert "gobus://agencies" in result


# ── título como link Markdown e números em pt-BR ─────────────────────────────


async def test_titulo_vira_link_markdown_e_mantem_o_id(fake_client):
    fake_client.route(
        "SearchNews",
        {"search": {"articles": [_make_article(1)], "found": 1, "page": 1}},
    )

    result = await search_news("educação", fake_client)

    assert "## [Artigo 1](https://gov.br/mec/artigo-1)" in result
    assert "ID: `id1`" in result
    assert "🔗" not in result


async def test_artigo_sem_url_tem_titulo_em_texto(fake_client):
    article = {**_make_article(1), "url": None}
    fake_client.route("SearchNews", {"search": {"articles": [article], "found": 1, "page": 1}})

    result = await search_news("educação", fake_client)

    assert "## Artigo 1\n" in result


async def test_total_encontrado_com_ponto_de_milhar(fake_client):
    fake_client.route(
        "SearchNews",
        {"search": {"articles": [_make_article(1)], "found": 1234, "page": 1}},
    )

    result = await search_news("educação", fake_client)

    assert "**1.234 artigos encontrados**" in result


# ── datas: dia inteiro em Brasília, validação e query "*" ────────────────────

EMPTY = {"search": {"articles": [], "found": 0, "page": 1}}


async def test_date_from_igual_a_date_to_cobre_o_dia_inteiro(fake_client):
    """O upstream compara published_at <= endDate: só a data (00:00 UTC) perdia o dia."""
    fake_client.route("SearchNews", EMPTY)

    await search_news("*", fake_client, date_from="2026-10-20", date_to="2026-10-20")

    (variables,) = fake_client.calls("SearchNews")
    assert variables["filter"]["startDate"] == "2026-10-20T00:00:00-03:00"
    assert variables["filter"]["endDate"] == "2026-10-20T23:59:59-03:00"


async def test_data_com_hora_passa_sem_conversao(fake_client):
    fake_client.route("SearchNews", EMPTY)

    await search_news(
        "*", fake_client, date_from="2026-10-20T10:00:00-03:00", date_to="2026-10-20T15:00:00Z"
    )

    (variables,) = fake_client.calls("SearchNews")
    assert variables["filter"]["startDate"] == "2026-10-20T10:00:00-03:00"
    assert variables["filter"]["endDate"] == "2026-10-20T15:00:00Z"


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"date_from": "20/10/2026"}, "date_from"),
        ({"date_to": "2026-13-01"}, "date_to"),
        ({"date_to": "ontem"}, "date_to"),
    ],
)
async def test_data_invalida_devolve_mensagem_sem_chamar_a_api(fake_client, kwargs, field):
    fake_client.route("SearchNews", EMPTY)

    result = await search_news("*", fake_client, **kwargs)

    assert f"`{field}`" in result
    assert "AAAA-MM-DD" in result
    assert fake_client.calls("SearchNews") == []


async def test_date_from_depois_de_date_to_devolve_mensagem(fake_client):
    fake_client.route("SearchNews", EMPTY)

    result = await search_news("*", fake_client, date_from="2026-10-21", date_to="2026-10-20")

    assert "date_from" in result and "date_to" in result
    assert fake_client.calls("SearchNews") == []


async def test_query_em_branco_vira_curinga(fake_client):
    """search() rejeita query vazia; "*" lista tudo (com agency_key/datas)."""
    fake_client.route("SearchNews", EMPTY)

    await search_news("  ", fake_client, agency_key="mec")

    assert fake_client.calls("SearchNews")[0]["query"] == "*"


async def test_data_exibida_e_o_dia_de_brasilia(fake_client):
    article = {**_make_article(1), "publishedAt": "2026-10-21T02:30:00+00:00"}
    fake_client.route("SearchNews", {"search": {"articles": [article], "found": 1, "page": 1}})

    result = await search_news("*", fake_client, date_from="2026-10-20", date_to="2026-10-20")

    assert "· 2026-10-20" in result
    assert "2026-10-21" not in result


# ── ajustes do pós-merge do #12: data ISO "basic" e período invertido com hora ──


async def test_data_iso_basic_vira_o_dia_inteiro_em_brasilia(fake_client):
    # "20261020" passava crua: o upstream lia 00:00 UTC e perdia o dia de date_to
    fake_client.route("SearchNews", EMPTY)

    await search_news("*", fake_client, date_from="20261020", date_to="20261020")

    (variables,) = fake_client.calls("SearchNews")
    assert variables["filter"]["startDate"] == "2026-10-20T00:00:00-03:00"
    assert variables["filter"]["endDate"] == "2026-10-20T23:59:59-03:00"


async def test_data_e_hora_iso_basic_viram_o_formato_estendido(fake_client):
    fake_client.route("SearchNews", EMPTY)

    await search_news("*", fake_client, date_from="20261020T100000-0300")

    (variables,) = fake_client.calls("SearchNews")
    assert variables["filter"]["startDate"] == "2026-10-20T10:00:00-03:00"


@pytest.mark.parametrize("value", ["2026102", "202610200", "20261340"])
async def test_data_basic_invalida_devolve_mensagem(fake_client, value):
    fake_client.route("SearchNews", EMPTY)

    result = await search_news("*", fake_client, date_to=value)

    assert "`date_to`" in result and "AAAA-MM-DD" in result
    assert fake_client.calls("SearchNews") == []


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        ("2026-10-20T15:00:00-03:00", "2026-10-20T10:00:00-03:00"),  # datetimes invertidos
        ("2026-10-21", "2026-10-20T23:00:00-03:00"),  # dia inteiro depois da hora final
        ("2026-10-20T12:00:00-03:00", "2026-10-20T14:00:00Z"),  # 15:00Z > 14:00Z
        ("20261021", "20261020"),  # basic invertido
        ("2026-10-20T15:00:00", "2026-10-20T12:00:00Z"),  # sem fuso = UTC (como a API)
    ],
)
async def test_periodo_invertido_com_hora_e_periodo_invalido(fake_client, date_from, date_to):
    fake_client.route("SearchNews", EMPTY)

    result = await search_news("*", fake_client, date_from=date_from, date_to=date_to)

    assert result.startswith("Período inválido")
    assert "Nenhum resultado" not in result
    assert fake_client.calls("SearchNews") == []


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        ("2026-10-20", "2026-10-20T10:00:00-03:00"),
        ("2026-10-20T10:00:00-03:00", "2026-10-20T10:00:00-03:00"),
        ("2026-10-20T09:00:00-03:00", "2026-10-20"),
    ],
)
async def test_periodo_com_hora_na_ordem_consulta(fake_client, date_from, date_to):
    fake_client.route("SearchNews", EMPTY)

    await search_news("*", fake_client, date_from=date_from, date_to=date_to)

    assert len(fake_client.calls("SearchNews")) == 1
