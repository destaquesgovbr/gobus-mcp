"""Formatação compartilhada do Markdown das tools: link, rótulo de agência, inteiro, plural,
datas e texto de erro."""

from datetime import date

import pytest

from gobus_mcp.formatting import (
    FOLLOW_UPS_MAX,
    FOLLOW_UPS_MAX_BYTES,
    agency_label,
    article_ref,
    brt_day,
    error_text,
    fmt_date,
    fmt_decimal,
    fmt_int,
    follow_ups,
    md_link,
    plural,
    tool_call,
    with_follow_ups,
)

URL = "https://www.gov.br/mec/pt-br/assuntos/noticias/x"


class TestMdLink:
    def test_link_markdown(self):
        assert md_link("Título", URL) == f"[Título]({URL})"

    def test_escapa_colchetes_e_barra_invertida_do_texto(self):
        assert md_link("A [b] c\\", URL) == f"[A \\[b\\] c\\\\]({URL})"

    def test_normaliza_quebras_de_linha_do_texto(self):
        assert md_link("Linha\n  quebrada ", URL) == f"[Linha quebrada]({URL})"

    @pytest.mark.parametrize("url", [None, "", "   "])
    def test_sem_url_devolve_texto_puro(self, url):
        assert md_link("Título [vídeo]", url) == "Título [vídeo]"

    @pytest.mark.parametrize(
        "url",
        ["javascript:alert(1)", "ftp://gov.br/x", "data:text/html,oi", "/relativo", "gov.br/x"],
    )
    def test_so_aceita_http_e_https(self, url):
        assert md_link("Título", url) == "Título"

    def test_aceita_esquema_em_maiusculas(self):
        assert md_link("T", "HTTPS://gov.br/x") == "[T](HTTPS://gov.br/x)"

    @pytest.mark.parametrize(
        "url", ["https://gov.br/a b", "https://gov.br/lei_(2026)", "https://gov.br/a)b"]
    )
    def test_url_com_espaco_ou_parenteses_vai_entre_sinais_de_menor_e_maior(self, url):
        assert md_link("T", url) == f"[T](<{url}>)"

    def test_codifica_sinais_de_menor_e_maior_da_url(self):
        assert md_link("T", "https://gov.br/a<b>") == "[T](https://gov.br/a%3Cb%3E)"

    def test_url_com_quebra_de_linha_vira_texto(self):
        assert md_link("T", "https://gov.br/a\nb") == "T"

    def test_texto_vazio_usa_a_url(self):
        assert md_link("", URL) == f"[{URL}]({URL})"


@pytest.mark.parametrize(
    ("code", "name", "expected"),
    [
        ("mec", "Ministério da Educação", "[mec] Ministério da Educação"),
        ("mec", None, "[mec]"),
        ("mec", "", "[mec]"),
        (None, "MEC", "MEC"),
        ("", "", ""),
        (None, None, ""),
    ],
)
def test_agency_label(code, name, expected):
    assert agency_label(code, name) == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, "0"), (999, "999"), (1234, "1.234"), (1234567, "1.234.567"), (-1500, "-1.500")],
)
def test_fmt_int_usa_ponto_de_milhar(n, expected):
    assert fmt_int(n) == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 artigos"), (1, "1 artigo"), (2, "2 artigos"), (1234, "1.234 artigos")],
)
def test_plural_concorda_e_usa_ponto_de_milhar(count, expected):
    assert plural(count, "artigo", "artigos") == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [(date(2026, 5, 20), "20/05/2026"), (date(2026, 1, 1), "01/01/2026")],
)
def test_fmt_date_dia_mes_ano(day, expected):
    assert fmt_date(day) == expected


class TestErrorText:
    def test_usa_a_mensagem(self):
        assert error_text(RuntimeError("timeout da API")) == "timeout da API"

    def test_sem_mensagem_usa_o_nome_da_classe(self):
        assert error_text(TimeoutError()) == "TimeoutError"


@pytest.mark.parametrize(
    ("published_at", "expected"),
    [
        ("2026-10-20T22:48:56+00:00", "2026-10-20"),
        ("2026-10-21T02:30:00+00:00", "2026-10-20"),  # 23:30 em Brasília
        ("2026-10-21T02:30:00Z", "2026-10-20"),
        ("2026-10-21T03:00:00+00:00", "2026-10-21"),
        ("2026-10-20", "2026-10-20"),
        ("2026-10-20T10:00:00", "2026-10-20"),  # sem fuso: sem conversão
        ("lixo", "lixo"),
        (None, ""),
        ("", ""),
    ],
)
def test_brt_day_converte_publicacao_para_o_dia_de_brasilia(published_at, expected):
    assert brt_day(published_at) == expected


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (4.14, 1, "4,1"),
        (14.58, 1, "14,6"),
        (1234.5, 1, "1.234,5"),
        (2.0, 0, "2"),
        (-0.25, 2, "-0,25"),
    ],
)
def test_fmt_decimal_usa_virgula_e_ponto_de_milhar(value, digits, expected):
    assert fmt_decimal(value, digits) == expected


class TestToolCall:
    def test_argumentos_em_json(self):
        assert (
            tool_call("gobus_get_entity_network", entity_id="Q155", depth=2, include_generic=True)
            == 'gobus_get_entity_network(entity_id="Q155", depth=2, include_generic=true)'
        )

    def test_omite_none_e_vazio(self):
        assert tool_call("gobus_search_news", query="x", agency_key=None, date_from="") == (
            'gobus_search_news(query="x")'
        )

    def test_lista_e_acentos(self):
        assert tool_call(
            "gobus_get_agency_analytics", agencies=["saude"], date_from="2026-10-01"
        ) == ('gobus_get_agency_analytics(agencies=["saude"], date_from="2026-10-01")')
        assert tool_call("gobus_search_news", query="Pé-de-Meia") == (
            'gobus_search_news(query="Pé-de-Meia")'
        )

    def test_crase_no_valor_nao_quebra_o_codigo_inline(self):
        assert "`" not in tool_call("gobus_search_news", query="a `b` c")


class TestFollowUps:
    def test_rodape_com_ate_3_chamadas(self):
        items = [(f'gobus_get_article(unique_id="a{i}")', f"artigo {i}") for i in range(5)]

        footer = follow_ups(items)

        lines = footer.splitlines()
        assert lines[0] == "**Para explorar:**"
        assert lines[1] == '- `gobus_get_article(unique_id="a0")` — artigo 0'
        assert len(lines) == 1 + FOLLOW_UPS_MAX == 4

    def test_no_maximo_400_bytes(self):
        long_why = "explicação " * 12
        items = [(f'gobus_get_article(unique_id="{i:040d}")', long_why) for i in range(3)]

        footer = follow_ups(items)

        assert 0 < len(footer.encode()) <= FOLLOW_UPS_MAX_BYTES == 400
        assert footer.count("\n- ") < 3  # o que não cabe fica de fora

    def test_item_grande_e_pulado_e_o_seguinte_entra(self):
        items = [
            ('gobus_search_news(query="' + "x" * 500 + '")', "grande"),
            ('gobus_get_article(unique_id="a1")', "cabe"),
        ]
        footer = follow_ups(items)
        assert "x" * 10 not in footer
        assert 'unique_id="a1"' in footer

    def test_sem_repeticao_e_sem_itens_vazios(self):
        footer = follow_ups(
            [
                ('gobus_get_article(unique_id="a1")', "um"),
                ('gobus_get_article(unique_id="a1")', "de novo"),
                ("", "sem chamada"),
                None,
            ]
        )
        assert footer.count("gobus_get_article") == 1
        assert "sem chamada" not in footer

    def test_sem_itens_devolve_vazio(self):
        assert follow_ups([]) == ""
        assert follow_ups([None, ("", "x")]) == ""

    def test_with_follow_ups_anexa_depois_de_linha_em_branco(self):
        md = with_follow_ups("# Título", [('gobus_get_article(unique_id="a1")', "ler")])
        assert md.startswith("# Título\n\n**Para explorar:**\n- `gobus_get_article")

    def test_with_follow_ups_sem_itens_nao_muda_o_texto(self):
        assert with_follow_ups("# Título", []) == "# Título"


class TestArticleRef:
    def test_link_e_id(self):
        art = {"uniqueId": "a1", "title": "Título", "url": URL}
        assert article_ref(art) == f"[Título]({URL}) · `a1`"

    def test_sem_url_so_titulo_e_id(self):
        assert article_ref({"uniqueId": "a1", "title": "Título"}) == "Título · `a1`"

    def test_corta_o_titulo(self):
        assert article_ref({"title": "abcdef"}, 3) == "abc"
