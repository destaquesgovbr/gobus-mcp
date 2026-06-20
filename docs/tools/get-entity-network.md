# get_entity_network

Retorna a rede de co-menções ao redor de uma entidade: os nós (entidades que aparecem junto) e as arestas (força das conexões em número de artigos). Use para mapear o entorno de uma entidade — quem aparece junto com quem nas notícias. Exige o `entityId` canônico, normalmente obtido via [resolve_entity](resolve-entity.md).

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `entity_id` | `str` | Sim | — | ID canônico da entidade (ex: `"Q4294522"`) |
| `depth` | `int` | Não | `1` | Profundidade da busca (1 ou 2; máx 2) |
| `limit` | `int` | Não | `50` | Máximo de arestas a retornar (máx 200) |

## Retorno

Retorna Markdown com um cabeçalho de contagem de nós e conexões, uma lista de nós (com ID, nome canônico, tipo e Wikidata) marcando o nó central, e uma lista das conexões mais fortes ordenadas por peso.

**Exemplo de saída:**

```
# Rede de entidades: Ministério da Economia

**18 nós · 42 conexões**

## Nós
- `Q4294522` **Ministério da Economia** (ORG) ([W](https://www.wikidata.org/wiki/Q4294522)) ← **[CENTRO]**
- `Q1808456` **Ministério da Educação** (ORG) ([W](https://www.wikidata.org/wiki/Q1808456))
- `Q123456` **Paulo Guedes** (PER)

## Conexões mais fortes
- **Ministério da Economia** ↔ **Receita Federal** (310 artigos)
- **Ministério da Economia** ↔ **Banco Central** (245 artigos)
```

## Exemplos

**Mapeamento de entorno:**
> "Mostre a rede de co-menções do Ministério da Economia (Q4294522)"

**Análise de segundo grau:**
> "Expanda a rede do MEC com profundidade 2 e até 100 conexões"

## Notas

- Os nós retornam o campo `entityId` (que é o ID canônico do grafo) — não confunda com o `canonicalId` usado em outras queries.
- `depth` é limitado a 2 e `limit` a 200 pelo servidor, mesmo que valores maiores sejam informados.
- A lista de conexões mais fortes exibe no máximo as 20 arestas de maior peso.
- Esta tool exige o ID canônico; se você só tem o nome, resolva primeiro com [resolve_entity](resolve-entity.md). Alternativamente, use [get_entity_profile](get-entity-profile.md), que aceita o nome e já inclui relacionadas.
