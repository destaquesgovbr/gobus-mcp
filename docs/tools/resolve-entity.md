# resolve_entity

Resolve o nome ou alias de uma entidade para o seu `entityId` canônico. É o passo preliminar para tools que exigem um ID: use antes de [get_entity_network](get-entity-network.md) e útil também para confirmar qual entidade canônica corresponde a um nome ambíguo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `query` | `str` | Sim | — | Nome ou alias a buscar (ex: `"MEC"`, `"Ministério da Educação"`) |
| `entity_type` | `str` | Não | — | Tipo da entidade — `ORG`, `PER`, `LOC`, `EVENT`, `POLICY`, `LAW` |
| `limit` | `int` | Não | `5` | Máximo de resultados distintos (por `entityId`) |

## Retorno

Retorna Markdown listando as entidades encontradas, **uma por `entityId`**, cada uma com nome canônico, tipo, `entityId`, link para Wikidata (se houver), contagem de artigos, confiança, tipo de match, aliases e descrição.

**Exemplo de saída:**

```
# Entidades encontradas para: MEC

## Ministério da Educação (ORG)
- **ID:** `Q1808456` · [Wikidata](https://www.wikidata.org/wiki/Q1808456)
- **Artigos:** 8.412 · **Confiança:** 0.98 (exact) · Aliases: MEC, Min. Educação
- Órgão do governo federal brasileiro responsável pela política nacional de educação.

## Ministério da Economia (ORG)
- **ID:** `Q4294522`
- **Artigos:** 5.103 · **Confiança:** 0.42 (fuzzy)
```

## Exemplos

**Desambiguação antes de consultar a rede:**
> "Qual é o entityId canônico do MEC?"

**Resolução com tipo explícito:**
> "Resolva 'Lula' como uma pessoa (PER)"

**Verificação de aliases:**
> "Sob que nomes o Ministério da Saúde aparece no acervo?"

## Notas

- Tipos válidos de entidade: `ORG`, `PER`, `LOC`, `EVENT`, `POLICY`, `LAW`. O valor é convertido para maiúsculas automaticamente.
- A confiança e o `matchType` (ex: `exact`, `fuzzy`) ajudam a julgar se o primeiro resultado é realmente a entidade desejada.
- O `entityId` retornado costuma ser o QID do Wikidata para entidades canonicalizadas.
- **Sem repetição:** o `entitySearch` une o casamento exato de alias (`alias_exact`) com o trigrama do nome (`trgm_fuzzy`) e repete o mesmo `entityId` quando ele casa por mais de um alias ou pelos dois caminhos (em 21/10/2026, "Enem" voltava o `Q5419278` três vezes e "Camilo Santana", o `Q18242106` duas). A tool fica com a linha de maior confiança de cada id, na ordem da 1ª aparição, e pede à API 3× o `limit` (teto de 20 do resolver) para que as repetições não ocupem as vagas.
