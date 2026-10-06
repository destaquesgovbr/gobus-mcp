# get_readability_recommendations

Diagnóstico de legibilidade (índice Flesch) por agência, com recomendações de estilo. Sem `agency_key`, devolve o ranking das agências ativas; com `agency_key`, o diagnóstico da agência, o benchmark da Agência Brasil na mesma janela, o pior e o melhor artigo de uma amostra e 3 recomendações.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `agency_key` | `str` | Não | `""` | Código da agência (ex: `"saude"`). Vazio = ranking geral |
| `days` | `int` | Não | `90` | Tamanho da janela em dias (1–730) |
| `limit` | `int` | Não | `10` | Máximo de agências no ranking (1–50) |
| `date_to` | `str` | Não | `""` | Último dia da janela, ISO (ex: `"2026-06-30"`). Vazio = ontem |

## Retorno

Markdown. No modo ranking, uma tabela `# · Agência · Flesch · Nível · Artigos (com Flesch) · Gap até 50`, a lista de agências **sem dado de legibilidade** e o benchmark interno (Agência Brasil, calculado na mesma janela). No modo agência, a média da agência, o gap até a meta de serviço, o benchmark, o pior e o melhor artigo da amostra e as recomendações.

**Exemplo de saída (modo agência, com o Flesch parado desde 30/06):**

```
# Diagnóstico de Legibilidade: Ministério da Saúde (`saude`)

**Janela pedida:** 07/07/2026–04/10/2026 (90 dias)
> **Janela efetiva:** 02/04/2026–30/06/2026 (90 dias) — dados até 06/2026. A janela pedida não tem Flesch até o fim.
> Legibilidade (Flesch): indisponível — 0% dos artigos com valor (0 de 4046) (desde 30/06/2026)

**Flesch médio:** 13.7 (muito difícil) · **Artigos na janela:** 273 (273 com Flesch) · **Palavras/artigo:** 682
**Gap até a meta de serviço (50):** -36.3
**Benchmark interno (Agência Brasil, mesma janela):** 33.6 (difícil)

## Artigos da janela (amostra dos 100 mais recentes: 77 com Flesch)

- **Pior:** [Tecnologia e vínculo: calculadora de idade corrigida…](https://www.gov.br/saude/…) — 2026-06-01 · Flesch 0.0 (muito difícil; valor bruto -8.3) · 958 palavras
- **Melhor:** [Mais da metade das equipes de saúde alcançam…](https://www.gov.br/saude/…) — 2026-06-02 · Flesch 42.6 (difícil) · 454 palavras

## Recomendações de Estilo
1. **Frases curtas:** …
```

## Exemplos

> "Qual o nível de legibilidade das notícias do Ministério da Saúde?"

> "Faça o ranking de legibilidade das agências nos últimos 90 dias"

> "Mostre o diagnóstico de legibilidade do MEC até 30/06/2026"

## Notas

- **Nulo nunca vira 0.0.** Agência sem Flesch aparece em "Sem dado de legibilidade".
- **Janela efetiva:** se o cálculo do Flesch parou antes do fim da janela pedida, a análise usa uma janela do mesmo tamanho terminando no último mês com dado e avisa "dados até MM/AAAA". Para analisar um período específico, use `date_to`.
- **Escala:** o pipeline calcula o Flesch com a fórmula **inglesa** do `textstat` (valores negativos são comuns em português). O valor exibido é limitado a 0–100 e o bruto aparece quando houve limite. Faixas únicas: 0–25 muito difícil · 25–50 difícil · 50–75 médio · 75–100 fácil.
- **Metas:** ≥50 para textos de serviço ao cidadão; ≥30 para institucionais.
- **Agência inválida** devolve sugestão: `"ms"` → `saude`, `"trabalho"` → `trabalho-e-emprego`; `tcu`, `camara`, `senado` e `ibge` estão fora do catálogo.
- O pior e o melhor artigo são escolhidos no cliente entre os 100 artigos mais recentes da janela efetiva (`articles(sort: DATE)`).
- Payload estruturado: `build_readability_payload` devolve um `ReadabilityReport` (pydantic, `payloads/readability.py`), base do app `ui://readability-dashboard` do G3.
