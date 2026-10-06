# forecast_trends

Projeta tendências de temas combinando três janelas de detecção (3, 7 e 21 dias): score composto, momentum e confiança.

!!! warning "Reescrita na Fase 2.5 (G2)"
    O comportamento descrito aqui é o atual: `horizon_days` só muda o título. O G2 reescreve a tool com share-of-voice por janela, taxa log por dia, perfil de dia útil e feriados, `horizon_days` efetivo (1–28) com projeção amortecida e confiança rebaixada na recuperação pós-defeso. Com os temas sem classificação desde 26/09/2026, as janelas curtas ficam vazias.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `horizon_days` | `int` | Não | `21` | Horizonte da projeção (hoje só informativo) |
| `limit` | `int` | Não | `5` | Máximo de temas, ordenados pelo score composto |

## Retorno

Markdown com a tabela `Tema | Score Composto | Momentum | Confiança`.

## Notas

- Score composto: média ponderada dos `growthScore` das janelas 3d/7d/21d.
- Momentum: compara as janelas de 3 e 7 dias (acelerando, desacelerando, estável).
- Confiança: número de janelas em que o tema aparece (3 = alta, 2 = média, 1 = baixa).
- A janela de 3 dias sofre efeito de borda de fim de semana.
