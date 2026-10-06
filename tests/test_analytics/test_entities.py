"""Entidades: cobertura sem republicadoras, agência dona, silêncio e precedência das classes."""

from datetime import UTC, date, datetime, timedelta

import pytest

from gobus_mcp.agency_activity import summarize_activity
from gobus_mcp.analytics.entities import (
    BURST_DAY_SHARE,
    CandidateSelection,
    coverage_stats,
    entity_signal,
    entity_windows,
    owner_agency,
    select_candidates,
    selection_notices,
    silence_score,
)
from gobus_mcp.analytics.entities import classify_entity as _classify
from gobus_mcp.analytics.themes import SENSITIVITY
from gobus_mcp.calendario import DateRange
from gobus_mcp.domains import Domain
from gobus_mcp.payloads.anomalies import EntitySignal, OwnerInfo

D = date
MEDIUM = SENSITIVITY["medium"]
REPUBLISHERS = frozenset({"agencia_brasil", "tvbrasil", "radioagencia_nacional"})
NORMAL_DAY = D(2026, 12, 15)  # fase normal; janela 08–14/12, baseline 10/11–07/12
BLACKOUT_DAY = D(2026, 10, 5)  # defeso; janela 28/09–04/10, baseline 31/08–27/09
RECOVERY_DAY = D(2026, 10, 30)  # recuperação; janela 23–29/10, baseline 06/06–03/07


def _cov(agency: str, counts: dict[date, int]) -> list[dict]:
    return [
        {
            "period": f"{day.isoformat()} 00:00:00+00",
            "agencyKey": agency,
            "agencyName": agency.upper(),
            "articleCount": n,
            "totalMentions": n * 2,
        }
        for day, n in sorted(counts.items())
        if n
    ]


def _spread(r: DateRange, total: int) -> dict[date, int]:
    """``total`` artigos distribuídos nos dias de ``r`` (round-robin)."""
    days = list(r)
    out: dict[date, int] = {}
    for i in range(total):
        out[days[i % len(days)]] = out.get(days[i % len(days)], 0) + 1
    return out


def _stats(rows, today=NORMAL_DAY):
    w = entity_windows(today)
    return coverage_stats(
        rows,
        window=w.window,
        baseline=w.baseline,
        owner_period=w.owner_period,
        republishers=REPUBLISHERS,
    )


def classify(stats, owner=None, *, today=NORMAL_DAY, activity=None, silenced=False,
             resumed=frozenset(), phase="normal"):  # fmt: skip
    return _classify(
        stats,
        owner,
        owner_activity_ratio=activity,
        owner_silenced=silenced,
        resumed=resumed,
        phase=phase,
        sens=MEDIUM,
    )


def _owner(key="saude", method="agency_key"):
    return OwnerInfo(agency_key=key, agency_name=None, method=method, share=None)


# ── janelas ─────────────────────────────────────────────────────────────────


def test_janelas_no_defeso():
    w = entity_windows(BLACKOUT_DAY)
    assert w.window == DateRange(D(2026, 9, 28), D(2026, 10, 4))
    assert w.baseline == DateRange(D(2026, 8, 31), D(2026, 9, 27))
    assert w.owner_period == DateRange(D(2026, 7, 7), D(2026, 9, 27))  # [D−90, D−8]
    assert w.sparkline == DateRange(D(2026, 9, 7), D(2026, 10, 4))  # 28 dias até D−1
    assert w.baseline_overlaps_blackout is True and w.pre_blackout is False
    assert w.coverage_range == DateRange(D(2026, 7, 7), D(2026, 10, 4))


def test_janelas_na_recuperacao_usam_o_baseline_pre_defeso():
    w = entity_windows(RECOVERY_DAY)
    assert w.baseline == DateRange(D(2026, 6, 6), D(2026, 7, 3))
    assert w.pre_blackout is True and w.baseline_overlaps_blackout is False
    assert w.coverage_range.start == D(2026, 6, 6)


# ── cobertura ───────────────────────────────────────────────────────────────


def test_coverage_stats_sem_republicadoras():
    w = entity_windows(NORMAL_DAY)
    rows = [
        *_cov("saude", {D(2026, 12, 8): 2, D(2026, 12, 10): 3, D(2026, 11, 20): 4}),
        *_cov("mec", {D(2026, 12, 10): 1}),
        *_cov("agencia_brasil", {D(2026, 12, 10): 7, D(2026, 11, 1): 9}),
        *_cov("saude", {D(2026, 12, 15): 50}),  # D (parcial): fora
    ]
    rows.append(dict(rows[0]))  # duplicata: conta uma vez
    s = _stats(rows)
    assert s.window_count == 6 and s.by_agency_window == {"saude": 5, "mec": 1}
    assert s.baseline_count == 4 and s.by_agency_baseline == {"saude": 4}
    assert s.window_agencies == 2 and s.distinct_days == 2
    assert s.max_day_share == pytest.approx(4 / 6)
    assert s.republisher_window_count == 7
    assert s.by_agency_owner_period == {"saude": 4}  # agencia_brasil fora
    assert s.agency_count("agencia_brasil", w.window) == 7  # consulta direta inclui
    assert s.daily(w.window) == [2, 0, 4, 0, 0, 0, 0]
    assert s.daily(w.window, "mec") == [0, 0, 1, 0, 0, 0, 0]


def test_coverage_stats_vazia():
    s = _stats([])
    assert (s.window_count, s.baseline_count, s.window_agencies, s.distinct_days) == (0, 0, 0, 0)
    assert s.max_day_share == 0.0


# ── dona ────────────────────────────────────────────────────────────────────


def test_dona_pelo_agency_key_da_entidade():
    w = entity_windows(NORMAL_DAY)
    s = _stats(_cov("mec", _spread(w.owner_period, 10)) + _cov("saude", _spread(w.owner_period, 5)))
    owner = owner_agency("saude", s, names={"saude": "Ministério da Saúde"})
    assert owner.agency_key == "saude" and owner.method == "agency_key"
    assert owner.agency_name == "Ministério da Saúde"
    assert owner.share == pytest.approx(5 / 15, abs=1e-3)


def test_dona_pela_cobertura_excluindo_republicadoras():
    w = entity_windows(NORMAL_DAY)
    rows = (
        _cov("agencia_brasil", _spread(w.owner_period, 40))
        + _cov("saude", _spread(w.owner_period, 6))
        + _cov("mec", _spread(w.owner_period, 4))
    )
    owner = owner_agency(None, _stats(rows))
    assert owner.agency_key == "saude" and owner.method == "coverage"
    assert owner.share == pytest.approx(0.6)


@pytest.mark.parametrize(
    "counts",
    [{"saude": 2}, {"saude": 3, "mec": 3, "pf": 3, "cgu": 3}],  # <3 artigos; share <0,3
)
def test_sem_dona_sem_volume_ou_sem_dominancia(counts):
    w = entity_windows(NORMAL_DAY)
    rows = [row for a, n in counts.items() for row in _cov(a, _spread(w.owner_period, n))]
    assert owner_agency(None, _stats(rows)) is None


def test_silence_score():
    # outras 3× acima; dona a 0,25× do próprio normal com produção total normal (1,0)
    assert silence_score(3.0, 0.25, 1.0) == pytest.approx(12.0)
    # dona com produção total em queda (0,5): a queda da entidade pesa menos
    assert silence_score(3.0, 0.25, 0.5) == pytest.approx(6.0)
    # atividade desconhecida conta como 1; pisos evitam divisão por ~0
    assert silence_score(3.0, 0.25, None) == pytest.approx(12.0)
    assert silence_score(3.0, 0.0, 1.0) == pytest.approx(30.0)


# ── precedência das classes ─────────────────────────────────────────────────


def test_burst_caso_censo_57_de_60_no_mesmo_dia():
    w = entity_windows(NORMAL_DAY)
    day = w.window.start + timedelta(days=2)
    rows = _cov("inep", {day: 57, day + timedelta(days=1): 3}) + _cov("mec", {D(2026, 11, 20): 2})
    s = _stats(rows)
    assert s.max_day_share >= BURST_DAY_SHARE
    a = classify(s)
    assert a.kind == "burst"
    # rajada vem antes de entidade nova (baseline zero)
    s0 = _stats(_cov("inep", {day: 57, day + timedelta(days=1): 3}))
    assert s0.baseline_count == 0 and classify(s0).kind == "burst"


def test_entidade_nova_com_baseline_zero():
    w = entity_windows(NORMAL_DAY)
    s = _stats(_cov("saude", _spread(w.window, 12)) + _cov("mec", _spread(w.window, 4)))
    a = classify(s, _owner())
    assert a.kind == "new_entity"
    assert a.ratio == pytest.approx(((16 + 1) / 7) / (1 / 28))


def _silence_rows(w, *, owner_w=0, owner_b=8, others_w=12, others_b=4, others=("mec", "pf")):
    rows = _cov("saude", _spread(w.window, owner_w)) + _cov("saude", _spread(w.baseline, owner_b))
    for agency in others:
        rows += _cov(agency, _spread(w.window, others_w // len(others)))
        rows += _cov(agency, _spread(w.baseline, others_b // len(others)))
    return rows


def test_silencio_coordenado():
    w = entity_windows(NORMAL_DAY)
    s = _stats(_silence_rows(w))
    a = classify(s, _owner(), activity=0.9)
    assert a.kind == "coordinated_silence"
    assert a.owner_window_count == 0 and a.owner_baseline_count == 8
    assert a.others_ratio >= MEDIUM.silence_ratio
    expected = silence_score(a.others_ratio, a.owner_entity_ratio, 0.9)
    assert a.silence_score == pytest.approx(expected, rel=1e-2)  # campos arredondados
    assert a.severity >= 1 / 3
    assert "saude" in a.explanation or "dona" in a.explanation


def test_silencio_exige_dona_ativa_no_geral_e_baseline_da_dona():
    w = entity_windows(NORMAL_DAY)
    s = _stats(_silence_rows(w))
    assert classify(s, _owner(), activity=0.3).kind != "coordinated_silence"
    small = _stats(_silence_rows(w, owner_b=2))
    assert classify(small, _owner(), activity=0.9).kind != "coordinated_silence"
    # dona ainda cobrindo no ritmo normal: não é silêncio
    covering = _stats(_silence_rows(w, owner_w=2, owner_b=8))
    assert classify(covering, _owner(), activity=0.9).kind != "coordinated_silence"


def test_silencio_com_atividade_desconhecida_marca_flag_e_rebaixa_confianca():
    w = entity_windows(NORMAL_DAY)
    s = _stats(_silence_rows(w, others_w=30, others_b=4))
    known = classify(s, _owner(), activity=1.0)
    unknown = classify(s, _owner(), activity=None)
    assert unknown.kind == "coordinated_silence"
    assert "owner_activity_unknown" in unknown.flags
    order = ["low", "medium", "high"]
    assert order.index(unknown.confidence) == order.index(known.confidence) - 1


def test_dona_silenciada_no_defeso_e_explicado_pelo_calendario():
    w = entity_windows(BLACKOUT_DAY)
    s = _stats(_silence_rows(w), today=BLACKOUT_DAY)
    a = classify(s, _owner(), today=BLACKOUT_DAY, activity=0.0, silenced=True, phase="blackout")
    assert a.kind == "calendar_explained"
    assert "owner_silenced" in a.flags
    # fora do defeso, a mesma configuração (dona ativa) é silêncio coordenado
    assert classify(s, _owner(), activity=0.9, phase="blackout").kind == "coordinated_silence"


def test_cobertura_concentrada():
    w = entity_windows(NORMAL_DAY)
    rows = _cov("saude", _spread(w.window, 10)) + _cov("saude", _spread(w.baseline, 4))
    a = classify(_stats(rows), _owner(), activity=1.0)
    assert a.kind == "concentrated_coverage"
    assert a.ratio >= MEDIUM.ratio


def test_normal_quando_a_cobertura_e_ampla():
    w = entity_windows(NORMAL_DAY)
    rows = []
    for agency in ("saude", "mec", "pf", "cgu", "mds", "defesa"):
        rows += _cov(agency, _spread(w.window, 3)) + _cov(agency, _spread(w.baseline, 2))
    a = classify(_stats(rows), _owner(), activity=1.0)
    assert a.kind == "normal"


def test_recuperacao_dominada_por_retomadas_e_calendario():
    w = entity_windows(RECOVERY_DAY)
    rows = (
        _cov("secom", _spread(w.window, 9))  # retomou após o defeso
        + _cov("saude", _spread(w.window, 3))
        + _cov("saude", _spread(w.baseline, 12))
    )
    s = _stats(rows, today=RECOVERY_DAY)
    a = classify(s, _owner(), today=RECOVERY_DAY, activity=1.0, resumed=frozenset({"secom"}),
                 phase="recovery")  # fmt: skip
    assert a.kind == "calendar_explained"
    assert "recovery" in a.flags


def test_recuperacao_com_sinal_que_se_sustenta_sem_as_retomadas_fica_com_flag():
    w = entity_windows(RECOVERY_DAY)
    rows = (
        _cov("secom", _spread(w.window, 30))
        + _cov("saude", _spread(w.window, 20))
        + _cov("saude", _spread(w.baseline, 4))
    )
    s = _stats(rows, today=RECOVERY_DAY)
    a = classify(s, _owner("mec"), today=RECOVERY_DAY, activity=1.0,
                 resumed=frozenset({"secom"}), phase="recovery")  # fmt: skip
    assert a.kind == "concentrated_coverage"
    assert "resumed_agencies" in a.flags and "recovery" in a.flags


@pytest.mark.parametrize("window_total", [1, 3, 8, 20])
@pytest.mark.parametrize("agencies", [1, 2, 6])
def test_baseline_zero_nunca_e_silencio_nem_concentrada(window_total, agencies):
    w = entity_windows(NORMAL_DAY)
    rows = []
    for i in range(agencies):
        rows += _cov(f"ag{i}", _spread(w.window, window_total))
    for activity in (None, 0.1, 1.0):
        a = classify(_stats(rows), _owner("ag0"), activity=activity)
        assert a.kind not in {"coordinated_silence", "concentrated_coverage"}


# ── candidatos do ranking upstream ──────────────────────────────────────────


def _trend(entity_id, computed_at, vr=3.0, wc=10, score=1.0):
    return {
        "entityId": entity_id,
        "canonicalName": entity_id.upper(),
        "type": "ORG",
        "trendingScore": score,
        "volumeRatio": vr,
        "windowCount": wc,
        "windowAgencies": 2,
        "computedAt": computed_at,
    }


def test_select_candidates_descarta_linhas_antigas_e_de_piso_zero():
    last, old = "2026-10-04 21:06:24.6+00", "2026-07-03 21:06:24.6+00"
    rows = [
        _trend("dgb_censo", old, vr=8571.43, wc=60, score=9.0),  # antiga e piso
        _trend("dgb_a", last, vr=1428.57, wc=10, score=8.0),  # piso (vr/wc ≈ 142,9)
        _trend("dgb_b", last, vr=3.0, wc=10, score=5.0),
        _trend("dgb_c", last, vr=2.0, wc=8, score=7.0),
        _trend("dgb_d", old, vr=2.0, wc=8, score=6.0),  # antiga
    ]
    sel = select_candidates(rows)
    assert isinstance(sel, CandidateSelection)
    assert [c["entityId"] for c in sel.candidates] == ["dgb_c", "dgb_b"]
    assert sel.dropped_floor == 2 and sel.dropped_stale == 1
    assert sel.upstream.rows_total == 5 and sel.upstream.rows_last_run == 3
    assert sel.upstream.rows_legacy_floor == 2
    assert sel.upstream.last_run_at == datetime(2026, 10, 4, 21, 6, 24, 600000, tzinfo=UTC)
    (notice,) = selection_notices(sel)
    assert notice.code == "BASELINE_ZERO_SUPPRESSED" and "2" in notice.message


def test_select_candidates_estado_de_05_10_tudo_no_piso():
    rows = [_trend(f"dgb_{i}", "2026-10-04 21:06:24+00", vr=142.86 * 10, wc=10) for i in range(50)]
    sel = select_candidates(rows, max_candidates=30)
    assert sel.candidates == [] and sel.dropped_floor == 50


def test_select_candidates_limita_e_aceita_ranking_corrigido():
    # depois do F2: Laplace, sem piso; baseline zero dá vr = 4·(wc+1) (vr/wc < 100)
    rows = [_trend(f"dgb_{i}", "2026-10-20 21:06:00+00", vr=4 * 11, wc=10, score=50 - i)
            for i in range(50)]  # fmt: skip
    sel = select_candidates(rows, max_candidates=30)
    assert len(sel.candidates) == 30 and sel.dropped_floor == 0 and sel.dropped_stale == 0
    assert selection_notices(sel) == []
    assert select_candidates([]).upstream.last_run_at is None


# ── sinal completo ──────────────────────────────────────────────────────────


def test_entity_signal_monta_o_payload_com_dona_atividade_e_dominio():
    today = NORMAL_DAY
    w = entity_windows(today)
    rows = _silence_rows(w, others_w=30, others_b=4)
    act_rows = [
        {"period": d.isoformat(), "agencyKey": "saude", "agencyName": "Ministério da Saúde",
         "articleCount": 10}
        for d in DateRange(D(2026, 9, 16), D(2026, 12, 14))
    ]  # fmt: skip
    activity = summarize_activity(act_rows, today=today)
    signal = entity_signal(
        entity={"entityId": "dgb_x", "canonicalName": "Programa X", "type": "POLICY",
                "agencyKey": "saude"},
        coverage_rows=rows,
        policy_domain=None,
        windows=w,
        sens=MEDIUM,
        republishers=REPUBLISHERS,
        activity=activity,
        names={},
        candidate={"volumeRatio": 8571.43, "computedAt": "2026-12-14 21:06:00+00"},
    )  # fmt: skip
    assert isinstance(signal, EntitySignal)
    assert signal.kind == "coordinated_silence"
    assert signal.owner.agency_key == "saude"
    assert signal.owner.agency_name == "Ministério da Saúde"  # nome do snapshot
    assert signal.owner_activity_ratio == pytest.approx(1.0)
    assert signal.domain is Domain.HEALTH  # POLICY sem domínio → mapa da dona
    assert len(signal.daily) == 28 and len(signal.owner_daily) == 28
    assert sum(signal.daily[-7:]) == 30  # a janela é o fim da série de 28 dias
    assert signal.owner_daily[-7:] == [0] * 7  # a dona calada na janela
    assert signal.upstream_volume_ratio == 8571.43
    assert signal.upstream_computed_at == datetime(2026, 12, 14, 21, 6, tzinfo=UTC)
    assert signal.band in {"watch", "alert"}
    assert signal.samples == []


def test_entity_signal_sem_snapshot_de_atividade_e_sem_dona():
    w = entity_windows(BLACKOUT_DAY)
    rows = _cov("mec", _spread(w.window, 6)) + _cov("pf", _spread(w.window, 6))
    signal = entity_signal(
        entity={"entityId": "dgb_y", "canonicalName": None, "type": None, "agencyKey": None},
        coverage_rows=rows,
        policy_domain=None,
        windows=w,
        sens=MEDIUM,
        republishers=REPUBLISHERS,
        activity=None,
        candidate={"canonicalName": "Evento Y", "type": "EVENT", "volumeRatio": 3.0,
                   "computedAt": None},
    )  # fmt: skip
    assert signal.name == "Evento Y" and signal.type == "EVENT"
    assert signal.owner is None and signal.owner_daily is None
    assert signal.kind == "new_entity"
    assert signal.domain is Domain.OTHER
    assert "blackout_baseline" in signal.flags


def test_sem_mencoes_proprias_na_janela_nao_e_entidade_nova():
    # só republicadoras cobriram (ou a janela do upstream era outra): nada a sinalizar
    w = entity_windows(NORMAL_DAY)
    s = _stats(_cov("agencia_brasil", _spread(w.window, 9)))
    assert s.window_count == 0 and s.baseline_count == 0
    a = classify(s)
    assert a.kind == "normal"
    assert "republishers_excluded" in a.flags
