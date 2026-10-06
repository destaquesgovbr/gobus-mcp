"""Análises puras sobre séries do acervo (razões, janelas, sinais).

- ``ratios``: limiar convertido do ``trendingThemes``, razão sem sobreposição, Laplace,
  share-of-voice, taxa log por dia, severidade e faixa;
- ``weekday``: perfil de dia útil, feriados, dias efetivos e nível de volume por fase;
- ``themes``: sensibilidade, cobertura de classificação e picos/quedas sustentados;
- ``entities``: cobertura sem republicadoras, agência dona, silêncio e classes de sinal;
- ``forecast``: composto, momentum, confiança e projeção amortecida;
- ``render``: Markdown de anomalias, forecast e coerência a partir dos modelos de ``payloads``;
- ``framing``: léxico pt-BR de enquadramento (anúncio, resultado, desafio, serviço, agenda);
- ``coherence``: coerência de mensagem entre agências (entidades, timing BRT, enquadramento
  e tom; índice 1–5 com pesos renormalizados).

Todas recebem ``today``/``now`` injetados; o I/O fica nos builders das tools.
"""
