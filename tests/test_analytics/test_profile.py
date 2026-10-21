"""Perfil de entidade: série mensal (próprias × republicações), totais e agências."""

from datetime import date

from gobus_mcp.analytics.profile import (
    coverage_table,
    coverage_totals,
    monthly_series,
    top_agencies,
)

REPUBLISHERS = frozenset({"agencia_brasil", "tvbrasil"})


def _row(period: str, agency: str, count: int, mentions: int | None = None, name=None) -> dict:
    return {
        "period": period,
        "agencyKey": agency,
        "agencyName": name,
        "articleCount": count,
        "totalMentions": mentions if mentions is not None else count,
        "avgSentimentScore": None,
    }


ROWS = [
    _row("2026-01-01 00:00:00+00", "mec", 3, 5, "Ministério da Educação"),
    _row("2026-01-01 00:00:00+00", "saude", 1, 1, "Ministério da Saúde"),
    _row("2026-01-01 00:00:00+00", "agencia_brasil", 2, 2, "Agência Brasil"),
    _row("2026-04-01 00:00:00+00", "mec", 7, 9, "Ministério da Educação"),
    _row("2026-04-01 00:00:00+00", "tvbrasil", 1, 1, "TV Brasil"),
]


def test_soma_as_agencias_e_separa_republicacoes():
    series = monthly_series(ROWS, date(2026, 1, 1), date(2026, 4, 30), REPUBLISHERS)
    jan = series[0]
    assert jan.month == date(2026, 1, 1)
    assert (jan.own, jan.republished, jan.total) == (4, 2, 6)
    apr = series[-1]
    assert (apr.own, apr.republished) == (7, 1)


def test_preenche_com_zero_todos_os_meses():
    series = monthly_series(ROWS, date(2026, 1, 1), date(2026, 4, 30), REPUBLISHERS)
    assert [p.label for p in series] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert [p.total for p in series] == [6, 0, 0, 8]
    assert not any(p.partial for p in series)


def test_mes_cortado_pela_janela_ou_corrente_fica_parcial():
    rows = [_row("2026-10-01 00:00:00+00", "mec", 2)]
    series = monthly_series(
        rows, date(2026, 1, 15), date(2026, 10, 20), REPUBLISHERS, today=date(2026, 10, 21)
    )
    assert len(series) == 10
    assert series[0].partial  # janela começa em 15/01
    assert series[-1].partial  # janela termina em 20/10
    assert series[-1].table_label == "2026-10 (parcial)"
    assert not any(p.partial for p in series[1:-1])

    current = monthly_series(rows, date(2026, 9, 1), date(2026, 10, 31), REPUBLISHERS,
                             today=date(2026, 10, 21))  # fmt: skip
    assert [p.partial for p in current] == [False, True]  # outubro ainda em curso


def test_linha_fora_da_janela_estende_a_serie_e_nao_some_do_total():
    rows = [*ROWS, _row("2025-12-01 00:00:00+00", "mec", 5)]
    series = monthly_series(rows, date(2026, 1, 1), date(2026, 4, 30), REPUBLISHERS)
    assert series[0].label == "2025-12"
    assert sum(p.total for p in series) == sum(r["articleCount"] for r in rows)


def test_aceita_periodo_curto_e_ignora_periodo_invalido():
    rows = [_row("2026-07", "mec", 2), _row("lixo", "mec", 99), _row("", "mec", 99)]
    series = monthly_series(rows, date(2026, 7, 1), date(2026, 7, 31), REPUBLISHERS)
    assert [p.total for p in series] == [2]
    assert coverage_totals(rows, REPUBLISHERS).own == 2


def test_sem_linhas_devolve_meses_zerados():
    series = monthly_series([], date(2026, 1, 1), date(2026, 3, 31), REPUBLISHERS)
    assert [p.total for p in series] == [0, 0, 0]


def test_totais_do_cabecalho():
    totals = coverage_totals(ROWS, REPUBLISHERS)
    assert totals.own == 11
    assert totals.republished == 3
    assert totals.total == 14
    assert totals.agencies == 2  # mec e saude (republicadoras à parte)
    assert totals.mentions == 18
    series = monthly_series(ROWS, date(2026, 1, 1), date(2026, 4, 30), REPUBLISHERS)
    assert totals.total == sum(p.total for p in series)


def test_top_agencies_sem_republicadoras_por_artigos():
    rows = [
        *ROWS,
        _row("2026-02-01 00:00:00+00", "cgu", 4, name=None),
        _row("2026-03-01 00:00:00+00", "agencia_brasil", 50, name="Agência Brasil"),
    ]
    top = top_agencies(rows, REPUBLISHERS, n=2)
    assert [(a.agency_key, a.name, a.articles) for a in top] == [
        ("mec", "Ministério da Educação", 10),
        ("cgu", "cgu", 4),  # sem agencyName: o código
    ]


def test_top_agencies_desempata_pelo_codigo():
    rows = [_row("2026-01", "b", 2), _row("2026-01", "a", 2)]
    assert [a.agency_key for a in top_agencies(rows, REPUBLISHERS)] == ["a", "b"]


def test_tabela_ate_24_meses_e_anos_anteriores_agregados():
    rows = [_row(f"{y}-{m:02d}-01 00:00:00+00", "mec", 1) for y in (2024, 2025, 2026)
            for m in range(1, 13) if (y, m) <= (2026, 10)]  # fmt: skip
    rows.append(_row("2024-03-01 00:00:00+00", "agencia_brasil", 4))
    series = monthly_series(rows, date(2024, 1, 1), date(2026, 10, 20), REPUBLISHERS)
    assert len(series) == 34
    table = coverage_table(series, max_months=24)
    assert [r.label for r in table[:1]] == ["2024 (jan–out)"]
    assert (table[0].own, table[0].republished) == (10, 4)
    assert table[1].label == "2024-11"
    assert table[-1].label == "2026-10 (parcial)"
    assert len(table) == 1 + 24
    assert sum(r.own + r.republished for r in table) == sum(p.total for p in series)


def test_tabela_com_ano_inteiro_antigo_usa_so_o_ano():
    series = monthly_series([], date(2023, 1, 1), date(2026, 10, 31), REPUBLISHERS)
    labels = [r.label for r in coverage_table(series, max_months=24)]
    assert labels[:3] == ["2023", "2024 (jan–out)", "2024-11"]
