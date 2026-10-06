"""Calendário do gobus: fuso BRT, defeso eleitoral, recuperação, feriados e janelas.

O nome ``calendario`` evita sombrear o ``calendar`` da stdlib (importado por
``http.cookiejar`` e ``email.utils``).

Contrato entre repos (integration.md §1.8): o data-platform (D2 do trend_detection) e o
gobus fixam as mesmas datas nos testes — defeso 2026-07-04..2026-10-25 e recuperação
até 2026-11-29 (= fim + janela 7 + baseline 28); em 30/11 tudo volta ao normal.

Todas as funções são puras: recebem ``today``/``now`` (só ``now_brt`` lê o relógio).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from gobus_mcp.payloads.common import CalendarContext, Notice, Window

BRT = ZoneInfo("America/Sao_Paulo")

PhaseName = Literal["normal", "blackout", "recovery"]


@dataclass(frozen=True)
class BlackoutPeriod:
    """Período de defeso (datas inclusivas) e a recuperação que o segue.

    A recuperação dura ``window_days + baseline_days`` dias depois do fim: é o tempo até
    o baseline da janela padrão (7/28) ficar inteiro fora do defeso.
    """

    start: date
    end: date
    label: str
    window_days: int = 7
    baseline_days: int = 28

    @property
    def recovery_until(self) -> date:
        """Último dia (inclusivo) da fase de recuperação."""
        return self.end + timedelta(days=self.window_days + self.baseline_days)


BLACKOUTS: tuple[BlackoutPeriod, ...] = (
    BlackoutPeriod(date(2026, 7, 4), date(2026, 10, 25), "Defeso eleitoral 2026"),
)

# Feriados nacionais (federais). Os do horizonte da Fase 2.5 são 12/10, 02/11, 15/11,
# 20/11 e 25/12; os anteriores entram para o perfil semanal estimado sobre o histórico.
HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),  # Confraternização Universal
        date(2026, 4, 3),  # Paixão de Cristo
        date(2026, 4, 21),  # Tiradentes
        date(2026, 5, 1),  # Dia do Trabalho
        date(2026, 9, 7),  # Independência
        date(2026, 10, 12),  # Nossa Senhora Aparecida
        date(2026, 11, 2),  # Finados
        date(2026, 11, 15),  # Proclamação da República
        date(2026, 11, 20),  # Dia Nacional de Zumbi e da Consciência Negra
        date(2026, 12, 25),  # Natal
        date(2027, 1, 1),  # Confraternização Universal
    }
)

# Pontos facultativos do Executivo federal (portaria anual do MGI). O Dia do Servidor
# (28/10) costuma ser deslocado por portaria: incluir aqui a data efetiva quando publicada.
PONTOS_FACULTATIVOS: frozenset[date] = frozenset(
    {
        date(2026, 2, 16),  # Carnaval
        date(2026, 2, 17),  # Carnaval
        date(2026, 6, 4),  # Corpus Christi
    }
)

NON_WORKING_DAYS: frozenset[date] = HOLIDAYS | PONTOS_FACULTATIVOS

# Data de troca do classificador de temas (F0a/D0). Enquanto um baseline cruzar essa
# data, o aviso CLASSIFIER_CHANGED fica ligado. Triagem de 05/10: o Haiku 3 entrou em EOL
# (primeira falha 2026-09-25T17:32Z); daí em diante o tema vem do Haiku 4.5 (INF-1 + B2).
# Se a D6 (re-enriquecer os 28 dias anteriores) for aprovada, o corte recua junto.
CLASSIFIER_CUTOFF: date | None = date(2026, 9, 25)


@dataclass(frozen=True)
class DateRange:
    """Intervalo de dias com início e fim **inclusivos**."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"DateRange invertido: {self.start} > {self.end}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def __contains__(self, day: object) -> bool:
        return isinstance(day, date) and self.start <= day <= self.end

    def __iter__(self) -> Iterator[date]:
        for offset in range(self.days):
            yield self.start + timedelta(days=offset)


@dataclass(frozen=True)
class Baseline:
    """Baseline escolhido para uma janela."""

    range: DateRange
    overlaps_blackout: bool
    pre_blackout: bool  # True na recuperação: baseline = mesmo tamanho antes do defeso


def now_brt() -> datetime:
    """Agora, em BRT."""
    return datetime.now(BRT)


def reference_date(now: datetime | None = None) -> date:
    """D: o dia corrente em BRT. ``now`` precisa ter fuso."""
    now = now or now_brt()
    if now.tzinfo is None:
        raise ValueError("reference_date exige datetime com fuso")
    return now.astimezone(BRT).date()


def _active(
    day: date, periods: tuple[BlackoutPeriod, ...]
) -> tuple[PhaseName, BlackoutPeriod | None]:
    for period in periods:
        if period.start <= day <= period.end:
            return "blackout", period
        if period.end < day <= period.recovery_until:
            return "recovery", period
    return "normal", None


def phase(day: date, periods: tuple[BlackoutPeriod, ...] = BLACKOUTS) -> PhaseName:
    """Fase do calendário em ``day``: ``normal``, ``blackout`` ou ``recovery``."""
    return _active(day, periods)[0]


def is_holiday(day: date, holidays: frozenset[date] = NON_WORKING_DAYS) -> bool:
    """Feriado ou ponto facultativo federal."""
    return day in holidays


def effective_weekday(day: date, holidays: frozenset[date] = NON_WORKING_DAYS) -> int:
    """Dia da semana (0=segunda … 6=domingo); feriado conta como domingo."""
    return 6 if day in holidays else day.weekday()


def closed_window(days: int, today: date) -> DateRange:
    """Janela fechada de ``days`` dias terminando em D−1: ``[D−days, D−1]``."""
    if days < 1:
        raise ValueError("days deve ser >= 1")
    return DateRange(today - timedelta(days=days), today - timedelta(days=1))


def _brt_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0), BRT)


def brt_bounds(r: DateRange) -> tuple[str, str]:
    """Limites ISO com offset BRT para ``articles(filter:{startDate, endDate})``.

    Fim exclusivo: ``("<start>T00:00:00-03:00", "<end+1>T00:00:00-03:00")``.
    """
    return (
        _brt_midnight(r.start).isoformat(),
        _brt_midnight(r.end + timedelta(days=1)).isoformat(),
    )


def utc_day_bounds(r: DateRange, *, end_exclusive: bool = True) -> tuple[str, str]:
    """Datas ISO (dias UTC da API). ``entityCoverage`` e ``agencyAnalytics`` MONTH/WEEK
    usam ``dateTo`` exclusivo; ``agencyAnalytics`` DAY é inclusivo (``end_exclusive=False``).
    Para o ``agencyAnalytics``, prefira ``agency_analytics_bounds``."""
    end = r.end + timedelta(days=1) if end_exclusive else r.end
    return r.start.isoformat(), end.isoformat()


def agency_analytics_date_to(last_day: date, granularity: str = "MONTH") -> str:
    """``dateTo`` do ``agencyAnalytics`` que inclui ``last_day`` inteiro (dia UTC da API).

    O resolver tem duas semânticas:
    - ``DAY``: ``published_at::date BETWEEN from AND to`` → fim inclusivo;
    - ``MONTH``/``WEEK``: ``published_at BETWEEN from::timestamptz AND to::timestamptz``, e
      o asyncpg converte a data em 00:00 → fim **exclusivo** na prática (manda o dia seguinte).
    """
    exclusive = granularity.upper() != "DAY"
    return (last_day + timedelta(days=1) if exclusive else last_day).isoformat()


def agency_analytics_bounds(r: DateRange, granularity: str = "MONTH") -> tuple[str, str]:
    """``(dateFrom, dateTo)`` do ``agencyAnalytics`` para cobrir ``r`` inteiro em qualquer
    granularidade (ver ``agency_analytics_date_to``)."""
    return r.start.isoformat(), agency_analytics_date_to(r.end, granularity)


def as_window(
    r: DateRange,
    *,
    baseline_overlaps_blackout: bool = False,
    bucket_tz: Literal["America/Sao_Paulo", "UTC"] = "America/Sao_Paulo",
) -> Window:
    """``Window`` fechada (dias nominais em BRT) para o payload; ``end`` exclusivo (D 00:00 BRT).

    ``bucket_tz="UTC"`` quando as contagens vêm em dias UTC da API (``entityCoverage``,
    ``agencyAnalytics`` DAY), embora a janela seja nomeada pelos dias em BRT.
    """
    return Window(
        kind="closed",
        start=_brt_midnight(r.start),
        end=_brt_midnight(r.end + timedelta(days=1)),
        days=r.days,
        bucket_tz=bucket_tz,
        baseline_overlaps_blackout=baseline_overlaps_blackout,
    )


def rolling_window(days: int, now: datetime, *, baseline_overlaps_blackout: bool = False) -> Window:
    """Janela móvel de ``days`` × 24 h até ``now``, em UTC — o ``range:{days}`` do Typesense
    (``topThemes``, ``analyticsKpis``). ``now`` precisa ter fuso."""
    if now.tzinfo is None:
        raise ValueError("rolling_window exige datetime com fuso")
    end = now.astimezone(UTC)
    return Window(
        kind="rolling",
        start=end - timedelta(days=days),
        end=end,
        days=days,
        bucket_tz="UTC",
        baseline_overlaps_blackout=baseline_overlaps_blackout,
    )


def rolling_range(days: int, today: date) -> DateRange:
    """Dias tocados por uma janela móvel de ``days`` dias até hoje: ``[D−days, D]``
    (o primeiro e o último parciais). Serve para checar sobreposição com o defeso e com a
    troca de classificador."""
    return DateRange(today - timedelta(days=days), today)


def overlaps_blackout(r: DateRange, periods: tuple[BlackoutPeriod, ...] = BLACKOUTS) -> bool:
    """O intervalo toca algum dia de defeso?"""
    return any(p.start <= r.end and r.start <= p.end for p in periods)


def calendar_context(
    today: date,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    *,
    silenced_agencies: int | None = None,
    resumed_agencies: int | None = None,
) -> CalendarContext:
    """Contexto de calendário do payload. ``days_to_end`` = dias até o fim da fase."""
    current, period = _active(today, periods)
    if period is None:
        return CalendarContext(
            phase="normal",
            label=None,
            blackout_start=None,
            blackout_end=None,
            recovery_until=None,
            days_to_end=None,
            silenced_agencies=silenced_agencies,
            resumed_agencies=resumed_agencies,
        )
    if current == "blackout":
        label, phase_end = period.label, period.end
    else:
        label, phase_end = f"Recuperação pós-{period.label.lower()}", period.recovery_until
    return CalendarContext(
        phase=current,
        label=label,
        blackout_start=period.start,
        blackout_end=period.end,
        recovery_until=period.recovery_until,
        days_to_end=(phase_end - today).days,
        silenced_agencies=silenced_agencies,
        resumed_agencies=resumed_agencies,
    )


def baseline_for(
    window: DateRange,
    baseline_days: int,
    *,
    today: date | None = None,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
) -> Baseline:
    """Baseline de ``baseline_days`` dias para ``window``.

    - normal e defeso: rolante, logo antes da janela (``[start−B, start−1]``);
    - recuperação (fase de ``today``, por padrão o dia seguinte ao fim da janela):
      os ``B`` dias antes do início do defeso — o mesmo baseline do D2 upstream
      (``[2026-06-06, 2026-07-04)`` para B=28).
    """
    ref = today or window.end + timedelta(days=1)
    current, period = _active(ref, periods)
    if current == "recovery" and period is not None:
        rng = DateRange(
            period.start - timedelta(days=baseline_days), period.start - timedelta(days=1)
        )
        pre_blackout = True
    else:
        rng = DateRange(
            window.start - timedelta(days=baseline_days), window.start - timedelta(days=1)
        )
        pre_blackout = False
    return Baseline(rng, overlaps_blackout(rng, periods), pre_blackout)


def classifier_changed_within(r: DateRange, cutoff: date | None = CLASSIFIER_CUTOFF) -> bool:
    """O intervalo cruza a troca de classificador (dias antes e depois do corte)?"""
    return cutoff is not None and r.start < cutoff <= r.end


def _fmt(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def calendar_notices(
    today: date,
    *,
    baselines: Iterable[DateRange] = (),
    silenced_agencies: int | None = None,
    periods: tuple[BlackoutPeriod, ...] = BLACKOUTS,
    cutoff: date | None = CLASSIFIER_CUTOFF,
) -> list[Notice]:
    """Avisos de calendário em ``today`` (detecção pela fase e pelos intervalos passados):

    - ``ELECTORAL_BLACKOUT`` durante o defeso;
    - ``POST_BLACKOUT_RECOVERY`` na recuperação (baselines pré-defeso, confiança −1 nível);
    - ``CLASSIFIER_CHANGED`` enquanto algum intervalo de ``baselines`` cruzar ``cutoff``.
    """
    notices: list[Notice] = []
    current, period = _active(today, periods)
    if current == "blackout" and period is not None:
        silenced = (
            f" {silenced_agencies} agências estão sem publicar há ≥14 dias."
            if silenced_agencies
            else ""
        )
        notices.append(
            Notice(
                code="ELECTORAL_BLACKOUT",
                severity="info",
                message=(
                    f"{period.label} de {_fmt(period.start)} a {_fmt(period.end)} "
                    f"(faltam {(period.end - today).days} dias): o volume e a mistura de "
                    f"agências mudam, e as comparações com o período anterior são atenuadas."
                    f"{silenced}"
                ),
                since=period.start,
                affects=["themes", "entities"],
            )
        )
    elif current == "recovery" and period is not None:
        notices.append(
            Notice(
                code="POST_BLACKOUT_RECOVERY",
                severity="info",
                message=(
                    f"Recuperação pós-{period.label.lower()} até {_fmt(period.recovery_until)}: "
                    "agências retomando a publicação; os baselines usam o período antes do "
                    "defeso e a confiança dos sinais cai um nível."
                ),
                since=period.end + timedelta(days=1),
                affects=["themes", "entities"],
            )
        )
    if cutoff is not None and any(classifier_changed_within(r, cutoff) for r in baselines):
        notices.append(
            Notice(
                code="CLASSIFIER_CHANGED",
                severity="warn",
                message=(
                    f"Troca do classificador de temas em {_fmt(cutoff)}: comparações cujo "
                    "baseline cruza essa data misturam dois modelos e podem mostrar picos ou "
                    "quedas artificiais de tema."
                ),
                since=cutoff,
                affects=["themes"],
            )
        )
    return notices
