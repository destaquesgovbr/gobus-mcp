# Ontologia de Políticas Públicas — DGB

> Criado: 2026-07-01 | Status: Design · Fase 1

## Objetivo

Estruturar POLICYs como objetos de primeira classe no entity_registry, com domínio semântico e fase do ciclo de vida. Isso permite:
- Rastrear o arco narrativo de uma política (anúncio → rotina)
- Comparar políticas dentro do mesmo domínio
- Alinhar entidades LAW relacionadas à política que as habilitam

## Motivação

O EXPERIMENTO_V3 (UC-09) confirmou: `dgb_taxa-selic` tem **0 artigos NER** apesar de ser o conceito econômico mais central do corpus. O UC-02 mostrou que o Pé-de-Meia (247 artigos) tem arco narrativo rico mas nenhum campo de "fase de ciclo de vida" explorável via API. A canonicalização de POLICYs hoje é cega para metadados semânticos.

## Modelo de dados

A ontologia é armazenada no campo `extra: JSONB` da tabela `entity_registry` — sem migração de schema adicional.

```json
{
  "domain": "SOCIAL",
  "lifecycle_phase": "ROUTINE",
  "instance_of": "Q327254",
  "enabling_laws": ["dgb_lei-14818-2024"],
  "responsible_agencies": ["mec", "caixa"],
  "target_population": ["estudantes", "ensino-medio"],
  "first_mentioned_date": "2023-08-01"
}
```

## Enums

### domain
| Valor | Descrição | Exemplos |
|-------|-----------|---------|
| SOCIAL | Proteção social, transferência de renda | Bolsa Família, Pé-de-Meia, BPC |
| ECONOMIC | Política econômica, fiscal, monetária | Novo PAC, Arcabouço Fiscal, Taxa Selic |
| HEALTH | Saúde pública, programas de saúde | Mais Médicos, Farmácia Popular |
| EDUCATION | Educação, ciência, tecnologia | ProUni, SISU, CAPES |
| SECURITY | Segurança pública, defesa | PRONASCI, Estratégia Nacional |
| ENVIRONMENT | Meio ambiente, clima | PPCDAm, Fundo Amazônia, COP30 |
| GOVERNANCE | Governança, transparência, reforma | Reforma Administrativa, e-Gov |

### lifecycle_phase
| Valor | Descrição | Indicadores textuais |
|-------|-----------|---------------------|
| ANNOUNCED | Anúncio, proposta, intenção | "lança", "anuncia", "propõe", "cria" |
| REGULATION | Regulamentação, decreto, portaria | "regulamenta", "decreto", "portaria" |
| IMPLEMENTATION | Execução, expansão, implementação | "inicia", "expande", "implementa", "alcança X beneficiários" |
| EVALUATION | Avaliação, balanço, revisão | "avalia", "balanço", "resultado", "impacto" |
| ROUTINE | Rotina, pagamento recorrente, manutenção | "pagamento", "ciclo", "continuidade" |

## Gazetteer inicial

Ver: `data-platform/scripts/seeds/policy_gazetteer.csv` — 45 políticas prioritárias curadas manualmente.

Critérios de inclusão:
- Políticas com >100 artigos no corpus (ex: Pé-de-Meia 247 art), OU
- Relevância estratégica alta mesmo com baixa cobertura NER (ex: Taxa Selic: 0 artigos NER, mas conceito econômico central)

## Mapeamento para Wikidata

Quando `wikidata_id` está preenchido, o campo `extra.instance_of` referencia a classe Wikidata que descreve a política:
- `Q327254` = programa de transferência de renda (cash transfer program)
- `Q2376464` = programa habitacional
- `Q2305408` = programa de saúde pública

## Integração com o pipeline

| Camada | Componente | Status |
|--------|-----------|--------|
| Dados | `data-platform/scripts/seeds/policy_gazetteer.csv` | ✅ Criado (PR #195) |
| Dados | `data-platform/scripts/migrations/026_policy_ontology_seed.sql` | ✅ Criado (PR #195) |
| API | `graphql-api` — query `policyDetails(entityId)` | ✅ Criado (PR #25) |
| MCP | `gobus_get_policy_lifecycle(policy_name)` | ✅ Criado (PR #6) |
| Dashboard | `ui://readability-dashboard` (MCP App) | ✅ Criado (PR #6) |
| Streamlit | Ciclo de Vida de Política | Issue #4 em streamlit-panorama-dgb |

## Roadmap de enriquecimento

| Fase | Ação | Impacto |
|------|------|---------|
| Imediata | Merge PRs + apply migration 026 | Cobre ~80% do volume de POLICY |
| 30 dias | Reprocessar corpus 2024+ via LLM para novos POLICYs | Cobertura total |
| 90 dias | Integrar eventos de calendário (Copom, votações) como gatilhos de lifecycle_phase | Detecção automática de mudança de fase |

## Leitura adicional

- EXPERIMENTO_V3/UC-02.md — ciclo de vida do Pé-de-Meia
- EXPERIMENTO_V3/UC-09.md — gap NER da Taxa Selic
- BLUEPRINT.md — roadmap completo da Fase 1
