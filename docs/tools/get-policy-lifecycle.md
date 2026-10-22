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

**ID:** `dgb_pe-de-meia` · **Fase atual:** ROUTINE (2026-09, último mês fechado)
**Pico:** 2026-04 (132 artigos) · **Último mês com cobertura:** 2026-07 · **Total no período:** 824 artigos
**Domínio:** SOCIAL

> Sem cobertura desde 2026-07: 2 meses fechados sem artigos (até 2026-09).

## Fases Identificadas (por mês, somando as agências)

| Mês | Artigos | Fase | Agência Dominante |
|-----|---------|------|-------------------|
| 2026-03 | 34 | ROUTINE | Ministério da Educação |
| 2026-04 | 132 | ANNOUNCED | Ministério da Educação |
| 2026-05 | 21 | ROUTINE | Ministério da Educação |
| 2026-06 | 130 | IMPLEMENTATION | Ministério da Educação |
| … | … | … | … |
| 2026-09 | 0 | ROUTINE | — |
| 2026-10 (parcial) | 0 | — | — |

## Âncoras Narrativos por Fase
- **ANNOUNCED:** Ministério da Educação

## Perspectiva Atual
…

## Artigos Representativos (pico: 2026-04)
- [Pé-de-Meia paga …](https://www.gov.br/…) — Ministério da Educação · 2026-04-12

**Para explorar:**
- `gobus_get_entity_profile(entity_name="dgb_pe-de-meia")` — série, órgãos e relacionadas
- `gobus_get_message_coherence(entity_id="dgb_pe-de-meia", date_from="2026-04-01", date_to="2026-04-30")` — sintonia no pico
- `gobus_get_article(unique_id="…")` — artigo do pico
```

## Exemplos

> "Qual é o ciclo de vida do Pé-de-Meia no gov.br?"

> "O Bolsa Família ainda está em fase de anúncio ou já virou rotina?"

## Notas

- **Série mensal:** o `entityCoverage(MONTH)` devolve uma linha por mês × agência; a tool soma as agências de cada mês. Meses sem artigos, do primeiro mês com cobertura até o mês corrente, entram com 0. Os meses são UTC, como na API.
- **Fases:** ANNOUNCED = mês fechado de maior volume; IMPLEMENTATION = ≥40% do pico; ROUTINE = abaixo disso. A fase atual é a do **último mês fechado**, não a do último mês com cobertura: uma política sem artigos há meses aparece em ROUTINE, com o aviso "Sem cobertura desde AAAA-MM".
- **Mês corrente:** aparece como `(parcial)`, fora da classificação e das âncoras (só é classificado quando é o único mês com cobertura). Se o parcial já supera o pico dos meses fechados, há um aviso.
- **Âncoras:** agência com mais artigos em cada fase (soma dos meses da fase).
- **Artigos do pico:** `articles(filter: {entityCanonical, startDate, endDate})` no mês de pico; se nenhum artigo tiver a entidade marcada, busca pelo nome na mesma janela.
- Use `gobus_resolve_entity(entity_type="POLICY")` para descobrir o nome canônico. `policyDetails` (domínio, população-alvo) é opcional.
- Artigo sem URL `http(s)` sai com o título em texto puro (`md_link`).
- **Para explorar:** o perfil completo, a coerência entre as agências no mês de pico (dentro do limite de 92 dias da tool) e o artigo do pico. A janela da coerência termina no último dia do pico ou em D−1, o que vier antes: com o pico no mês corrente (parcial), o fim do mês ainda está no futuro. No dia 1 desse mês não há dia fechado, e a coerência sai do rodapé.
