# trace_entity

Reconstrói a trajetória completa de uma entidade (órgão, pessoa, programa, lei, evento) no portal Gov.BR ao longo do tempo. Atende o caso de uso [UC-03](../casos-de-uso.md) e serve assessores e pesquisadores que querem entender toda a cobertura de um ator ou política.

## Workflow

O prompt guia o LLM por 5 passos sequenciais:

1. **Identificação da entidade** — [`resolve_entity`](../tools/resolve-entity.md) com `query` (e `entity_type`, se informado) — encontra o ID canônico da entidade.
2. **Perfil e cobertura temporal** — [`get_entity_profile`](../tools/get-entity-profile.md) com o intervalo de datas — obtém a série temporal de menções.
3. **Rede de relacionamentos** — [`get_entity_network`](../tools/get-entity-network.md) com o `entityId` canônico e `depth=2` — mapeia as entidades conectadas.
4. **Artigos âncoras** — [`search_news`](../tools/search-news.md) + [`get_article`](../tools/get-article.md) nos 3 mais relevantes — extrai detalhes das publicações-chave.
5. **Linha do tempo narrativa** — síntese — o LLM monta um relatório com contexto inicial, momentos-chave, rede institucional, estado atual e conclusão sobre a relevância da entidade.

## Como ativar

No Claude, envie:

> "Mostre toda a cobertura do Programa Mais Médicos desde sua criação."

ou

> "Trace a trajetória do Pix entre 2020 e 2024."

## Parâmetros

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `entity_name` | Nome ou alias da entidade | `"Programa Mais Médicos"` |
| `entity_type` | Tipo: `ORG`, `PER`, `LOC`, `EVENT`, `POLICY`, `LAW` (opcional) | `"POLICY"` |
| `date_from` | Data de início ISO (opcional) | `"2013-01-01"` |
| `date_to` | Data de fim ISO (opcional) | `"2024-12-31"` |
