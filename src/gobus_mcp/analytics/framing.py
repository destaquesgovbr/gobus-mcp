"""Enquadramento lexical pt-BR (dimensão F da coerência de mensagem, F5).

Cada artigo recebe no máximo um enquadramento entre ``announcement`` (anúncio),
``result`` (resultado), ``challenge`` (desafio), ``service`` (serviço) e ``agenda``, pela
contagem de termos de um léxico curado sobre o texto normalizado (minúsculas, sem acento,
sem pontuação):

- texto = título (peso 2) + subtítulo + lead editorial + resumo + tags (peso 1);
- resumo ``[MOCK]`` (4.600 artigos de 24/09/2025 a 27/02/2026 com texto de teste, issue #3)
  é ignorado e contado;
- empate entre enquadramentos: ``FRAME_PRIORITY``; nenhum termo → sem enquadramento.

Os padrões casam no início de palavra e usam formas explícitas quando o prefixo curto
pegaria palavras comuns (``institui`` ≠ ``instituto``; ``cria`` ≠ ``criança``).
Heurística provisória: a calibração é sanity check, não gabarito.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from gobus_mcp.payloads.coherence import Frame

# Ordem de desempate (o primeiro vence).
FRAME_PRIORITY: tuple[Frame, ...] = ("challenge", "announcement", "result", "service", "agenda")

FRAME_LABELS: dict[str, str] = {
    "announcement": "anúncio",
    "result": "resultado",
    "challenge": "desafio",
    "service": "serviço",
    "agenda": "agenda",
    "other": "outro",
}

MOCK_PREFIX = "[MOCK]"
TITLE_WEIGHT = 2

# Padrões sobre o texto normalizado (sem acento). Cada um casa no início de palavra.
_LEXICON: dict[Frame, tuple[str, ...]] = {
    "announcement": (
        r"anunci\w*",
        r"lanc(a|am|ou|aram|ado|ada|ados|adas|amento|amentos)\b",
        r"institui\w*",
        r"inaugur\w*",
        r"sancion\w*",
        r"assin(a|am|ou|aram|atura)\b",
        r"cri(a|am|ou|aram|ado|ada|acao)\b",
        r"autoriz\w*",
        r"decret\w*",
        r"portaria\w*",
        r"novo programa\b",
    ),
    "result": (
        r"resultado\w*",
        r"balanc(o|os)\b",
        r"recorde\w*",
        r"cresc\w*",
        r"aument\w*",
        r"alcanc\w*",
        r"ating(e|em|iu|iram|ido|ida)\b",
        r"super(a|am|ou|aram)\b",
        r"ultrapass\w*",
        r"entreg(a|am|ou|aram|ue|ues)\b",
        r"conclu(i|iu|ido|ida|isao)\b",
        r"ca(i|em|iu|iram)\b",
        r"queda\w*",
        r"reduc(ao|oes)\b",
        r"reduz\w*",
        r"estudo\w*",
        r"pesquisa\w*",
        r"levantamento\w*",
        r"mostra\b",
        r"aponta\b",
    ),
    "challenge": (
        r"desafi\w*",
        r"combat\w*",
        r"fraud\w*",
        r"irregular\w*",
        r"investig\w*",
        r"operac(ao|oes)\b",
        r"deflagr\w*",
        r"crise\w*",
        r"emergenc\w*",
        r"risco\w*",
        r"alert\w*",
        r"denunc\w*",
        r"crime\w*",
        r"criminos\w*",
        r"ilega\w*",
        r"ilicit\w*",
        r"golpe\w*",
        r"desmat\w*",
        r"queimad\w*",
        r"incendi\w*",
        r"enfrent\w*",
        r"violenc\w*",
        r"enchente\w*",
        r"desastre\w*",
        r"apreen\w*",
        r"pris(ao|oes)\b",
        r"suspen\w*",
        r"bloquei\w*",
    ),
    "service": (
        r"inscri\w*",
        r"inscrev\w*",
        r"cadastr\w*",
        r"consult(a|ar|e|em)\b",
        r"atendiment\w*",
        r"aplicativo\w*",
        r"saiba\b",
        r"como (fazer|solicitar|acessar|consultar|sacar|receber|participar|se inscrever)\b",
        r"solicit\w*",
        r"agendament\w*",
        r"agendar\b",
        r"prazo\w*",
        r"calendario\w*",
        r"pagament\w*",
        r"saque\w*",
        r"requeriment\w*",
        r"orientac\w*",
        r"duvida\w*",
        r"passo a passo\b",
        r"vagas?\b",
        r"matricul\w*",
        r"edita(l|is)\b",
        r"gratuit\w*",
    ),
    "agenda": (
        r"agenda\b",
        r"reun\w*",
        r"visit\w*",
        r"particip(a|am|ou|aram|acao)\b",
        r"encontro\w*",
        r"evento\w*",
        r"seminario\w*",
        r"forum\b",
        r"cerimoni\w*",
        r"solenidade\w*",
        r"audiencia\w*",
        r"comitiva\w*",
        r"viagem\b",
        r"missao\b",
        r"palestra\w*",
        r"congresso\w*",
        r"conferencia\w*",
        r"feira\w*",
        r"debate\w*",
        r"assembleia\w*",
        r"cupula\b",
        r"receb(e|eu)\b",
    ),
}

_PATTERNS: dict[Frame, re.Pattern[str]] = {
    frame: re.compile(r"\b(?:" + "|".join(patterns) + r")") for frame, patterns in _LEXICON.items()
}
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str | None) -> str:
    """Minúsculas, sem acento, só letras e dígitos separados por espaço."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(_NON_WORD.sub(" ", folded).split())


def is_mock_summary(summary: str | None) -> bool:
    """Resumo de teste ``[MOCK] …`` (não é texto do órgão)."""
    return bool(summary) and summary.lstrip().startswith(MOCK_PREFIX)


def frame_scores(text: str) -> dict[Frame, int]:
    """Termos do léxico por enquadramento em ``text`` (normalizado aqui)."""
    normalized = normalize_text(text)
    return {frame: len(_PATTERNS[frame].findall(normalized)) for frame in FRAME_PRIORITY}


def classify_frame(title: str | None, body: str | None = "") -> Frame | None:
    """Enquadramento dominante (título com peso 2); ``None`` sem nenhum termo."""
    title_scores = frame_scores(title or "")
    body_scores = frame_scores(body or "")
    totals = {f: TITLE_WEIGHT * title_scores[f] + body_scores[f] for f in FRAME_PRIORITY}
    best = max(FRAME_PRIORITY, key=lambda f: (totals[f], -FRAME_PRIORITY.index(f)))
    return best if totals[best] > 0 else None


def article_frame(article: Mapping) -> tuple[Frame | None, bool]:
    """``(enquadramento, resumo [MOCK] ignorado)`` de uma linha do ``articles``."""
    summary = article.get("summary")
    mock = is_mock_summary(summary)
    parts = [
        article.get("subtitle"),
        article.get("editorialLead"),
        None if mock else summary,
        " ".join(t for t in article.get("tags") or [] if t),
    ]
    body = " ".join(p for p in parts if p)
    return classify_frame(article.get("title"), body), mock
