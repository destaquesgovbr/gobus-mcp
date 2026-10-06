# score_article

Atribui uma nota editorial (0–10) a um artigo, comparando-o ao benchmark da própria agência. Três dimensões, com pesos 50/30/20: legibilidade (Flesch), concisão (palavras contra a mediana da agência) e densidade de entidades (por 100 palavras). Com `compare_with`, pontua um segundo artigo e devolve a comparação.

!!! info "MCP App"
    Tool de app: em hosts com suporte abre o painel [`ui://article-scorecard`](../apps/article-scorecard.md) (semáforos, benchmark, comparação lado a lado). O `content` é o Markdown abaixo; o `structuredContent` traz o `ScoreReport` com o mesmo Markdown em `summary`, como primeiro campo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `unique_id` | `str` | Sim | — | ID único do artigo (obtido via `gobus_search_news`) |
| `compare_with` | `str` | Não | `""` | `uniqueId` de outro artigo para comparar lado a lado. A resposta sugere até 2 (seção "Sugestões de comparação") |

## Retorno

Markdown com a nota geral (ou "Nota indisponível"), as notas por dimensão, uma tabela de benchmark da agência e da Agência Brasil, as sugestões de comparação e, com `compare_with`, a tabela "Comparação" (nota, dimensões, Flesch e palavras dos dois artigos). `compare_with` inexistente ou igual ao artigo vira o aviso "Comparação indisponível", sem derrubar a nota.

**Estados da nota:**

| Estado | Quando | Nota |
|--------|--------|------|
| `scored` | Flesch, contagem de palavras e benchmark da agência disponíveis | média ponderada 50/30/20 |
| `partial` | sem benchmark de concisão (amostra da agência < 10 artigos) | média **renormalizada** de legibilidade e densidade |
| `refused` | artigo sem Flesch **ou** sem contagem de palavras | "Nota indisponível" — nunca uma nota neutra |

**Exemplo de saída:**

```
# Score Editorial: Mais da metade das equipes de saúde alcançam resultados “bom” e “ótimo”…
**Ministério da Saúde** (`saude`) · 02/06/2026 · `mais-da-metade-das-equipes…_6cf9e5`

## Nota Geral: 8.4/10

## Notas por Dimensão
- **Legibilidade (peso 50%):** 8.5/10 — Flesch 42.6 (difícil)
- **Concisão (peso 30%):** 10.0/10 — 454 palavras (mediana da agência: 646)
- **Densidade de entidades (peso 20%):** 6.0/10 — 5 entidades (1.1 por 100 palavras)

## Benchmark (90 dias antes da publicação)
| | Ministério da Saúde | Agência Brasil |
|---|---|---|
| Amostra | 234 artigos com palavras, 233 com Flesch (19/03–01/06/2026) | 226 artigos com palavras, 226 com Flesch (14/05–02/06/2026) |
| Flesch mediano | 14.6 (muito difícil) | 33.8 (difícil) |
| Palavras (mediana) | 646 | 434 |
```

## Exemplos

> "Dê uma nota editorial para este artigo: `brasil-mantem-acoes-de-resposta-ao-sarampo…_30e5f6`"

> "Esse release está mais longo que o padrão da agência?"

> "Compare a nota deste artigo com a do melhor texto da Agência Brasil no mesmo período"

## Notas

- **Benchmark ancorado na publicação:** amostra `articles` da agência (até 250) e da Agência Brasil nos **90 dias antes da publicação** do artigo (o próprio artigo fica fora). As medianas são calculadas no cliente; com menos de 10 artigos com o campo, a mediana é `null` ("—").
- **Legibilidade:** Flesch limitado a 0–100 (fórmula inglesa do `textstat`); nota linear até a meta de serviço (Flesch 50 = 10).
- **Concisão:** razão palavras ÷ mediana da agência — ≤0,8 → 10; ≤1,0 → 8; ≤1,3 → 6; ≤1,6 → 4; acima → 2.
- **Densidade de entidades:** entidades por 100 palavras — ≥2 → 8; ≥1 → 6; ≥0,5 → 4; abaixo → 2.
- Quando o pipeline de features está parado, a tabela de benchmark mostra quantos artigos da amostra têm métricas e um aviso "indisponível (desde …)".
- **Semáforo** por dimensão e da nota (`light`, `overallLight`): verde ≥ 7, amarelo ≥ 4, vermelho abaixo, cinza sem nota. Os limiares ficam no Python; o app não os reimplementa.
- **Sugestões de comparação:** o maior Flesch da amostra da agência e o da Agência Brasil (até 2; o próprio artigo nunca entra).
- Payload estruturado: `build_score_payload` devolve um `ScoreReport` (`payloads/scorecard.py`) com `comparison` (`ScoreComparison`) e `suggestedComparisons`; a tool o entrega como `structuredContent`.
