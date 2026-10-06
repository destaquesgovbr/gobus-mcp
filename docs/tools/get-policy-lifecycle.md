# get_policy_lifecycle

Ciclo de vida comunicacional de uma política pública: série **mensal** de cobertura, fases (anúncio, implementação, rotina), agências dominantes e artigos do mês de pico.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `policy_name` | `str` | Sim | — | Nome ou alias da política (ex: `"Pé-de-Meia"`) |
| `date_from` | `str` | Não | `"2024-01-01"` | Início da série, ISO |

## Retorno

```
# Ciclo de Vida: Pé-de-Meia

**ID:** `dgb_pe-de-meia` · **Fase atual:** ROUTINE
**Pico:** 2026-04 (132 artigos) · **Último mês com cobertura:** 2026-09 · **Total no período:** 824 artigos
**Domínio:** SOCIAL

## Fases Identificadas (por mês, somando as agências)

| Mês | Artigos | Fase | Agência Dominante |
|-----|---------|------|-------------------|
| 2026-03 | 34 | ROUTINE | Ministério da Educação |
| 2026-04 | 132 | ANNOUNCED | Ministério da Educação |
| 2026-05 | 21 | ROUTINE | Ministério da Educação |
| 2026-06 | 130 | IMPLEMENTATION | Ministério da Educação |

## Âncoras Narrativos por Fase
- **ANNOUNCED:** Ministério da Educação

## Perspectiva Atual
…

## Artigos Representativos (pico: 2026-04)
- [Pé-de-Meia paga …](https://www.gov.br/…) — Ministério da Educação · 2026-04-12
```

## Exemplos

> "Qual é o ciclo de vida do Pé-de-Meia no gov.br?"

> "O Bolsa Família ainda está em fase de anúncio ou já virou rotina?"

## Notas

- **Série mensal:** o `entityCoverage(MONTH)` devolve uma linha por mês × agência; a tool soma as agências de cada mês. Meses sem artigos entre o primeiro e o último entram com 0.
- **Fases:** ANNOUNCED = mês de maior volume; IMPLEMENTATION = ≥40% do pico; ROUTINE = abaixo disso. A fase atual é a do último mês da série.
- **Âncoras:** agência com mais artigos em cada fase (soma dos meses da fase).
- **Artigos do pico:** `articles(filter: {entityCanonical, startDate, endDate})` no mês de pico; se nenhum artigo tiver a entidade marcada, busca pelo nome na mesma janela.
- Use `gobus_resolve_entity(entity_type="POLICY")` para descobrir o nome canônico. `policyDetails` (domínio, população-alvo) é opcional.
