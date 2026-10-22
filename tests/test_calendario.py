"""Calendário: BRT, defeso eleitoral 2026, recuperação, feriados e janelas.

As datas de fronteira (04/07, 25/10, 29/11, 30/11) são as mesmas fixadas nos testes do
data-platform (D2 do trend_detection) — contrato entre os repos.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from gobus_mcp.calendario import (
    BLACKOUTS,
    BRT,
    CLASSIFIER_CUTOFF,
    HOLIDAYS,
    MIN_ALTERNATIVE_DAYS,
    TAXONOMY_CHANGE_2026,
    TAXONOMY_CHANGE_2026_DEFAULT,
    TAXONOMY_CHANGED_THEMES,
    BlackoutPeriod,
    DateRange,
    agency_analytics_bounds,
    agency_analytics_date_to,
    as_window,
    baseline_for,
    blackout_alternatives,
    brt_bounds,
    brt_day_end,
    brt_day_start,
    calendar_context,
    calendar_notices,
    classifier_changed_within,
    closed_window,
    effective_weekday,
    is_holiday,
    now_brt,
    parse_taxonomy_change,
    phase,
    reference_date,
    rolling_range,
    rolling_window,
    taxonomy_affected,
    taxonomy_changed_within,
    utc_day_bounds,
)
from gobus_mcp.config import settings
from gobus_mcp.domains import THEME_DOMAIN, Domain
from gobus_mcp.payloads.common import CalendarContext, Window

D = date


def test_brt_e_o_fuso_de_sao_paulo():
    assert BRT.key == "America/Sao_Paulo"
    assert datetime(2026, 10, 5, 12, tzinfo=BRT).utcoffset() == timedelta(hours=-3)
    assert now_brt().tzinfo is BRT


def test_defeso_2026_e_recuperacao_ate_29_11():
    (period,) = BLACKOUTS
    assert (period.start, period.end) == (D(2026, 7, 4), D(2026, 10, 25))
    # fim + janela 7 + baseline 28 (integration.md I3)
    assert period.recovery_until == D(2026, 11, 29)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (D(2026, 1, 1), "normal"),
        (D(2026, 7, 3), "normal"),
        (D(2026, 7, 4), "blackout"),
        (D(2026, 10, 5), "blackout"),
        (D(2026, 10, 25), "blackout"),
        (D(2026, 10, 26), "recovery"),
        (D(2026, 11, 29), "recovery"),
        (D(2026, 11, 30), "normal"),
    ],
)
def test_phase_nas_fronteiras(day, expected):
    assert phase(day) == expected


def test_phase_com_periodos_injetados():
    periods = (BlackoutPeriod(D(2030, 1, 10), D(2030, 1, 20), "Teste"),)
    assert phase(D(2030, 1, 9), periods) == "normal"
    assert phase(D(2030, 1, 10), periods) == "blackout"
    assert phase(D(2030, 1, 21), periods) == "recovery"
    assert phase(D(2030, 2, 24), periods) == "recovery"  # 20/01 + 35
    assert phase(D(2030, 2, 25), periods) == "normal"
    assert phase(D(2026, 10, 5), periods) == "normal"


@pytest.mark.parametrize(
    "day", [D(2026, 10, 12), D(2026, 11, 2), D(2026, 11, 15), D(2026, 11, 20), D(2026, 12, 25)]
)
def test_feriados_federais_do_horizonte(day):
    assert day in HOLIDAYS
    assert is_holiday(day)
    assert effective_weekday(day) == 6  # feriado conta como domingo


def test_dia_util_comum_nao_e_feriado():
    assert not is_holiday(D(2026, 10, 13))
    assert effective_weekday(D(2026, 10, 13)) == 1  # terça
    assert effective_weekday(D(2026, 10, 12), holidays=frozenset()) == 0  # segunda


def test_reference_date_e_o_dia_em_brt():
    # 02:00 UTC de 06/10 = 23:00 BRT de 05/10
    assert reference_date(datetime(2026, 10, 6, 2, 0, tzinfo=UTC)) == D(2026, 10, 5)
    assert reference_date(datetime(2026, 10, 6, 3, 0, tzinfo=UTC)) == D(2026, 10, 6)
    with pytest.raises(ValueError):
        reference_date(datetime(2026, 10, 6, 2, 0))  # sem fuso


def test_date_range_inclusivo():
    r = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert r.days == 7
    assert D(2026, 10, 4) in r and D(2026, 10, 5) not in r
    assert list(r)[0] == D(2026, 9, 28) and len(list(r)) == 7
    with pytest.raises(ValueError):
        DateRange(D(2026, 10, 4), D(2026, 9, 28))


def test_closed_window_termina_em_d_menos_1():
    assert closed_window(7, D(2026, 10, 5)) == DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert closed_window(1, D(2026, 10, 5)) == DateRange(D(2026, 10, 4), D(2026, 10, 4))


def test_brt_bounds_com_offset_e_fim_exclusivo():
    r = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert brt_bounds(r) == ("2026-09-28T00:00:00-03:00", "2026-10-05T00:00:00-03:00")


def test_brt_day_start_e_end_cobrem_o_dia_inteiro_em_segundos():
    # search()/articles(): published_at >= startDate e published_at <= endDate (segundos)
    assert brt_day_start(D(2026, 10, 20)) == "2026-10-20T00:00:00-03:00"
    assert brt_day_end(D(2026, 10, 20)) == "2026-10-20T23:59:59-03:00"


def test_utc_day_bounds_fim_exclusivo_ou_inclusivo():
    r = DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert utc_day_bounds(r) == ("2026-09-28", "2026-10-05")  # entityCoverage
    assert utc_day_bounds(r, end_exclusive=False) == ("2026-09-28", "2026-10-04")  # DAY


def test_agency_analytics_bounds_cobre_o_ultimo_dia_em_toda_granularidade():
    # MONTH/WEEK: o resolver faz ``published_at BETWEEN from::timestamptz AND to::timestamptz``
    # e o asyncpg converte a data em 00:00 → dateTo exclusivo na prática; DAY é inclusivo.
    r = DateRange(D(2026, 9, 5), D(2026, 10, 4))
    assert agency_analytics_bounds(r, "MONTH") == ("2026-09-05", "2026-10-05")
    assert agency_analytics_bounds(r, "week") == ("2026-09-05", "2026-10-05")
    assert agency_analytics_bounds(r, "DAY") == ("2026-09-05", "2026-10-04")
    assert agency_analytics_bounds(r) == ("2026-09-05", "2026-10-05")  # padrão: MONTH


def test_agency_analytics_date_to_converte_o_ultimo_dia_inclusivo():
    assert agency_analytics_date_to(D(2026, 9, 30), "MONTH") == "2026-10-01"
    assert agency_analytics_date_to(D(2026, 12, 31), "WEEK") == "2027-01-01"
    assert agency_analytics_date_to(D(2026, 9, 30), "DAY") == "2026-09-30"


def test_as_window_fechada_em_brt():
    w = as_window(DateRange(D(2026, 9, 28), D(2026, 10, 4)), baseline_overlaps_blackout=True)
    assert isinstance(w, Window)
    assert w.kind == "closed" and w.bucket_tz == "America/Sao_Paulo" and w.days == 7
    assert w.start == datetime(2026, 9, 28, 3, tzinfo=UTC)
    assert w.end == datetime(2026, 10, 5, 3, tzinfo=UTC)
    assert w.baseline_overlaps_blackout is True


def test_calendar_context_no_defeso():
    ctx = calendar_context(D(2026, 10, 5), silenced_agencies=39)
    assert isinstance(ctx, CalendarContext)
    assert ctx.phase == "blackout"
    assert ctx.label == "Defeso eleitoral 2026"
    assert (ctx.blackout_start, ctx.blackout_end) == (D(2026, 7, 4), D(2026, 10, 25))
    assert ctx.recovery_until == D(2026, 11, 29)
    assert ctx.days_to_end == 20
    assert ctx.silenced_agencies == 39 and ctx.resumed_agencies is None


def test_calendar_context_na_recuperacao_e_depois():
    ctx = calendar_context(D(2026, 10, 30))
    assert ctx.phase == "recovery"
    assert "Recuperação" in ctx.label
    assert ctx.days_to_end == 30  # até 29/11
    assert ctx.blackout_end == D(2026, 10, 25)

    after = calendar_context(D(2026, 11, 30))
    assert after.phase == "normal"
    assert after.label is None and after.blackout_start is None and after.days_to_end is None


def test_baseline_rolante_fora_do_defeso():
    window = closed_window(7, D(2026, 6, 20))  # 13/06..19/06
    base = baseline_for(window, 28)
    assert base.range == DateRange(D(2026, 5, 16), D(2026, 6, 12))
    assert base.overlaps_blackout is False and base.pre_blackout is False


def test_baseline_no_defeso_e_rolante_e_marca_sobreposicao():
    window = closed_window(7, D(2026, 10, 5))  # 28/09..04/10
    base = baseline_for(window, 28)
    assert base.range == DateRange(D(2026, 8, 31), D(2026, 9, 27))
    assert base.overlaps_blackout is True


@pytest.mark.parametrize("today", [D(2026, 10, 26), D(2026, 11, 10), D(2026, 11, 29)])
def test_baseline_na_recuperacao_e_o_pre_defeso(today):
    base = baseline_for(closed_window(7, today), 28)
    # mesmo intervalo do D2 upstream: [2026-06-06, 2026-07-04)
    assert base.range == DateRange(D(2026, 6, 6), D(2026, 7, 3))
    assert base.pre_blackout is True and base.overlaps_blackout is False


def test_baseline_volta_a_rolar_em_30_11():
    base = baseline_for(closed_window(7, D(2026, 11, 30)), 28)  # janela 23/11..29/11
    assert base.range == DateRange(D(2026, 10, 26), D(2026, 11, 22))
    assert base.pre_blackout is False and base.overlaps_blackout is False


def test_baseline_pre_defeso_respeita_baseline_days():
    base = baseline_for(closed_window(21, D(2026, 11, 1)), 84)
    assert base.range == DateRange(D(2026, 4, 11), D(2026, 7, 3))


def test_classifier_changed_within():
    r = DateRange(D(2026, 9, 1), D(2026, 10, 4))
    assert classifier_changed_within(r, D(2026, 9, 26)) is True
    assert classifier_changed_within(r, D(2026, 9, 1)) is False  # tudo depois do corte
    assert classifier_changed_within(r, D(2026, 10, 5)) is False  # corte no futuro
    assert classifier_changed_within(r, None) is False


def test_corte_do_classificador_vem_da_triagem_f0a():
    # Haiku 3 em EOL: primeira falha em 2026-09-25T17:32Z; dali em diante o tema vem do
    # Haiku 4.5 (INF-1 + B2). Baseline que cruza 25/09 mistura os dois classificadores.
    assert CLASSIFIER_CUTOFF == D(2026, 9, 25)
    assert classifier_changed_within(DateRange(D(2026, 9, 1), D(2026, 10, 4))) is True
    assert classifier_changed_within(DateRange(D(2026, 9, 25), D(2026, 10, 4))) is False


# ── G2: janelas móveis, janela fechada com bucket UTC e avisos de calendário ───


def test_rolling_window_movel_em_utc_ate_agora():
    now = datetime(2026, 10, 5, 15, 30, tzinfo=BRT)
    w = rolling_window(7, now)
    assert w.kind == "rolling" and w.bucket_tz == "UTC" and w.days == 7
    assert w.end == datetime(2026, 10, 5, 18, 30, tzinfo=UTC)
    assert w.start == datetime(2026, 9, 28, 18, 30, tzinfo=UTC)
    assert w.end.tzinfo is not None and w.end.utcoffset() == timedelta(0)


def test_rolling_window_exige_fuso():
    with pytest.raises(ValueError):
        rolling_window(7, datetime(2026, 10, 5, 12))


def test_rolling_range_cobre_os_dias_do_range_days():
    # range:{days: 28} em 05/10 cobre de 07/09 (parcial) até hoje (parcial)
    assert rolling_range(28, D(2026, 10, 5)) == DateRange(D(2026, 9, 7), D(2026, 10, 5))


def test_as_window_fechada_com_bucket_utc():
    # entidades: janela nominal em BRT, contagens do entityCoverage em dias UTC
    w = as_window(DateRange(D(2026, 9, 28), D(2026, 10, 4)), bucket_tz="UTC")
    assert w.kind == "closed" and w.bucket_tz == "UTC"
    assert w.start == datetime(2026, 9, 28, 3, tzinfo=UTC)


def _codes(notices):
    return [n.code for n in notices]


def test_calendar_notices_no_defeso():
    notices = calendar_notices(D(2026, 10, 5), silenced_agencies=39)
    assert _codes(notices) == ["ELECTORAL_BLACKOUT"]
    (n,) = notices
    assert n.severity == "info" and n.since == D(2026, 7, 4)
    assert "25/10/2026" in n.message and "20 dias" in n.message and "39" in n.message


@pytest.mark.parametrize(
    "today", [D(2026, 10, 26), D(2026, 10, 27), D(2026, 11, 3), D(2026, 11, 29)]
)
def test_calendar_notices_na_recuperacao(today):
    notices = calendar_notices(today)
    assert _codes(notices) == ["POST_BLACKOUT_RECOVERY"]
    assert notices[0].since == D(2026, 10, 26)
    assert "29/11/2026" in notices[0].message


@pytest.mark.parametrize("today", [D(2026, 7, 3), D(2026, 11, 30)])
def test_calendar_notices_fora_do_defeso_e_da_recuperacao(today):
    assert calendar_notices(today) == []


def test_calendar_notices_classifier_changed_enquanto_baseline_cruza_o_corte():
    crossing = DateRange(D(2026, 9, 7), D(2026, 10, 5))
    clean = DateRange(D(2026, 9, 26), D(2026, 10, 24))
    notices = calendar_notices(D(2026, 10, 5), baselines=[clean, crossing])
    assert _codes(notices) == ["ELECTORAL_BLACKOUT", "CLASSIFIER_CHANGED"]
    changed = notices[1]
    assert changed.severity == "warn" and changed.since == D(2026, 9, 25)
    assert changed.affects == ["themes"]
    assert "25/09/2026" in changed.message

    assert _codes(calendar_notices(D(2026, 11, 30), baselines=[clean])) == []
    assert calendar_notices(D(2026, 11, 30), baselines=[crossing], cutoff=None) == []


@pytest.mark.parametrize(
    ("today", "codes"),
    [(D(2026, 7, 3), []), (D(2026, 7, 4), ["ELECTORAL_BLACKOUT"]),
     (D(2026, 10, 25), ["ELECTORAL_BLACKOUT"]), (D(2026, 10, 26), ["POST_BLACKOUT_RECOVERY"]),
     (D(2026, 11, 29), ["POST_BLACKOUT_RECOVERY"]), (D(2026, 11, 30), [])],
)  # fmt: skip
def test_calendar_notices_nas_fronteiras_do_contrato_entre_repos(today, codes):
    assert _codes(calendar_notices(today)) == codes
    if today == D(2026, 10, 25):
        assert "faltam 0 dias" in calendar_notices(today)[0].message


# ── virada da taxonomia de temas (tema 26, D0 do TH-1/DP-2) ─────────────────

D0 = D(2026, 11, 10)  # D0 prevista no plano; os testes injetam a data (a constante é provisória)
# Data do código (calendario.TAXONOMY_CHANGE_2026_DEFAULT): os testes do parse comparam com
# ela, então ajustar a D0 muda só a constante e o pin abaixo.
CODE_D0 = TAXONOMY_CHANGE_2026_DEFAULT


def test_virada_da_taxonomia_provisoria_e_configuravel():
    # Pin da data do código, provisória até a D0 real: no dia, mudar a constante em
    # calendario.py e esta linha (o resto da suíte injeta a data ou lê a constante).
    assert TAXONOMY_CHANGE_2026_DEFAULT == D(2026, 10, 22)
    # GOBUS_TAXONOMY_CHANGE_DATE sobrepõe a constante (sem a variável, vale a do código)
    assert TAXONOMY_CHANGE_2026 == parse_taxonomy_change(settings.taxonomy_change_date)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, CODE_D0), ("", CODE_D0), ("  ", CODE_D0),
     ("2026-11-10", D(2026, 11, 10)), (" 2026-11-12 ", D(2026, 11, 12)),
     ("off", None), ("OFF", None), ("none", None), ("desligado", None),
     ("10/11/2026", CODE_D0), ("lixo", CODE_D0)],
)  # fmt: skip
def test_parse_taxonomy_change_nunca_levanta(value, expected):
    # vazio ou inválido cai na data do código: o servidor não pode cair no import
    assert parse_taxonomy_change(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("off", None), ("lixo", None), ("10/11/2026", None),
     ("2026-11-10", D(2026, 11, 10))],
)  # fmt: skip
def test_parse_taxonomy_change_com_default_desligado_nunca_levanta(value, expected):
    # Desligar o aviso pelo código é TAXONOMY_CHANGE_2026_DEFAULT = None (PR de uma linha →
    # deploy automático): a env var não está no Terraform, então não é chave operacional.
    # Mesmo assim, valor inválido nunca derruba o import.
    assert parse_taxonomy_change(value, default=None) == expected


def test_temas_da_virada_sao_os_que_mudam_de_serie():
    # 19.03/19.04 → 26; a reclassificação por LLM tira Defesa Civil também de 04 (MDR em
    # 04.03.01), 05.02.01 e 15.02.03 (atualização de 21–22/10 do plano)
    assert TAXONOMY_CHANGED_THEMES == {
        "04": "Segurança Pública",
        "05": "Meio Ambiente e Sustentabilidade",
        "15": "Desenvolvimento Social",
        "19": "Defesa e Forças Armadas",
        "26": "Defesa Civil e Gestão de Desastres",
    }
    assert set(TAXONOMY_CHANGED_THEMES.values()) <= set(THEME_DOMAIN)
    assert THEME_DOMAIN["Defesa Civil e Gestão de Desastres"] is Domain.SECURITY


def test_taxonomy_affected_na_ordem_dos_codigos_e_so_os_presentes():
    labels = ["Saúde", "Defesa Civil e Gestão de Desastres", "Desenvolvimento Social"]
    assert taxonomy_affected(labels) == [
        "Desenvolvimento Social",
        "Defesa Civil e Gestão de Desastres",
    ]
    assert taxonomy_affected(["Saúde", "Educação"]) == []
    assert taxonomy_affected([]) == []


def test_taxonomy_changed_within_como_o_corte_do_classificador():
    r = DateRange(D(2026, 10, 20), D(2026, 11, 16))
    assert taxonomy_changed_within(r, D0) is True
    assert taxonomy_changed_within(r, D(2026, 10, 20)) is False  # tudo depois da virada
    assert taxonomy_changed_within(r, D(2026, 11, 17)) is False  # virada no futuro
    assert taxonomy_changed_within(r, D(2026, 11, 16)) is True  # só o último dia depois
    assert taxonomy_changed_within(r, None) is False


def test_calendar_notices_taxonomy_changed_so_com_tema_afetado_e_baseline_cruzando():
    crossing = DateRange(D(2026, 10, 20), D(2026, 11, 16))
    clean = DateRange(D(2026, 11, 10), D(2026, 12, 7))
    themes = ["Saúde", "Defesa e Forças Armadas", "Defesa Civil e Gestão de Desastres"]

    notices = calendar_notices(
        D(2026, 12, 7), baselines=[clean, crossing], taxonomy_themes=themes, taxonomy_change=D0
    )
    (changed,) = [n for n in notices if n.code == "TAXONOMY_CHANGED"]
    assert changed.severity == "warn" and changed.since == D0
    assert changed.affects == ["themes"]
    assert "10/11/2026" in changed.message
    assert "Defesa e Forças Armadas" in changed.message
    assert "Defesa Civil e Gestão de Desastres" in changed.message
    assert "Saúde" not in changed.message  # só os temas afetados presentes no relatório

    def codes(**kw):
        return _codes(calendar_notices(D(2026, 12, 7), **{"taxonomy_change": D0, **kw}))

    # sem tema afetado no relatório, sem baseline cruzando, sem data ou sem temas: nada
    assert "TAXONOMY_CHANGED" not in codes(baselines=[crossing], taxonomy_themes=["Saúde"])
    assert "TAXONOMY_CHANGED" not in codes(baselines=[clean], taxonomy_themes=themes)
    assert "TAXONOMY_CHANGED" not in codes(
        baselines=[crossing], taxonomy_themes=themes, taxonomy_change=None
    )
    assert "TAXONOMY_CHANGED" not in codes(baselines=[crossing])


def test_calendar_notices_sem_temas_continua_igual_para_quem_ja_chamava():
    # chamadas antigas (sem taxonomy_themes) não ganham o aviso novo
    crossing = DateRange(D(2026, 10, 20), D(2026, 11, 16))
    assert calendar_notices(D(2026, 12, 7), baselines=[crossing]) == []


# ── alternativas de janela sem o defeso (coerência, A9) ─────────────────────


def test_blackout_alternatives_fora_do_defeso_e_none():
    assert blackout_alternatives(DateRange(D(2026, 6, 1), D(2026, 6, 30)), D(2026, 10, 6)) is None
    assert blackout_alternatives(DateRange(D(2026, 11, 2), D(2026, 11, 8)), D(2026, 11, 9)) is None


def test_blackout_alternatives_no_defeso_pre_com_a_mesma_duracao_e_pos_ainda_sem_dias():
    window = DateRange(D(2026, 9, 22), D(2026, 10, 5))  # 14 dias, dentro do defeso
    alt = blackout_alternatives(window, D(2026, 10, 6))

    assert alt is not None and alt.period == BLACKOUTS[0]
    assert alt.pre == DateRange(D(2026, 6, 20), D(2026, 7, 3))  # véspera do defeso, 14 dias
    assert alt.pre_clamped is False
    assert alt.post is None  # 26/10 ainda não chegou
    assert alt.post_from == D(2026, 10, 26)
    assert alt.post_ready_on == D(2026, 10, 26) + timedelta(days=MIN_ALTERNATIVE_DAYS)


def test_blackout_alternatives_pre_respeita_o_inicio_minimo():
    # caminho por entidade: o índice de busca só marca entidades desde 20/05/2026
    window = DateRange(D(2026, 8, 1), D(2026, 9, 30))  # 61 dias
    alt = blackout_alternatives(window, D(2026, 10, 6), earliest=D(2026, 5, 20))

    assert alt.pre == DateRange(D(2026, 5, 20), D(2026, 7, 3))
    assert alt.pre_clamped is True


def test_blackout_alternatives_pre_curto_demais_fica_none():
    window = DateRange(D(2026, 8, 1), D(2026, 8, 14))
    alt = blackout_alternatives(window, D(2026, 10, 6), earliest=D(2026, 7, 1))
    assert alt.pre is None  # 01–03/07 = 3 dias < mínimo


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (D(2026, 11, 1), None),  # 26–31/10 = 6 dias fechados < 7
        (D(2026, 11, 2), DateRange(D(2026, 10, 26), D(2026, 11, 1))),  # 7 dias (mínimo)
        (D(2026, 11, 12), DateRange(D(2026, 10, 26), D(2026, 11, 8))),  # a mesma duração (14)
    ],
)
def test_blackout_alternatives_pos_defeso_ate_ontem_no_maximo_com_a_mesma_duracao(today, expected):
    window = DateRange(D(2026, 10, 12), D(2026, 10, 25))  # 14 dias
    alt = blackout_alternatives(window, today)
    assert alt.post == expected
    assert alt.post_ready_on == D(2026, 11, 2)


def test_blackout_alternatives_janela_curta_aceita_a_mesma_duracao():
    window = DateRange(D(2026, 10, 20), D(2026, 10, 22))  # 3 dias
    alt = blackout_alternatives(window, D(2026, 10, 30))
    assert alt.pre == DateRange(D(2026, 7, 1), D(2026, 7, 3))
    assert alt.post == DateRange(D(2026, 10, 26), D(2026, 10, 28))
    assert alt.post_ready_on == D(2026, 10, 29)
