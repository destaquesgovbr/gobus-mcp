"""Formatação compartilhada do Markdown das tools: link, rótulo de agência, inteiro e dia."""

import pytest

from gobus_mcp.formatting import agency_label, brt_day, fmt_int, md_link

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
