# get_article

Retorna o conteúdo completo de um artigo a partir do seu ID único. Use após [search_news](search-news.md) para ler o texto integral, métricas de leitura (features) e as entidades mencionadas no artigo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `unique_id` | `str` | Sim | — | ID único do artigo (ex: obtido via `search_news`) |

## Retorno

Retorna Markdown com título, agência, data, URL, tags, um bloco de features (tempo de leitura, legibilidade, visualizações, trending), uma seção de entidades mencionadas agrupadas por tipo, e o conteúdo completo do artigo.

**Exemplo de saída:**

```
# Campanha Nacional de Vacinação contra a Gripe é prorrogada

**Ministério da Saúde** · 2024-05-12
🔗 https://www.gov.br/saude/...
Tags: vacinação, gripe, saúde pública

⏱ 4 min leitura (812 palavras) · 📖 Legibilidade: médio (58) · 👁 12.430 visualizações · 🔥 Em alta (score 3.2)

## Entidades mencionadas
**Instituições:** Ministério da Saúde (6x), Anvisa (2x)
**Pessoas:** Nísia Trindade (3x)
**Políticas:** Programa Nacional de Imunizações (4x)

## Conteúdo
A campanha foi estendida até o fim de maio...
```

## Exemplos

**Leitura aprofundada após busca:**
> "Abra o artigo completo `ms-2024-05-12-vacinacao-gripe`"

**Extração de entidades de um artigo:**
> "Quais instituições e pessoas são citadas nessa notícia da reforma tributária?"

## Notas

- O tempo de leitura é estimado em 200 palavras por minuto.
- A legibilidade usa o índice Flesch: acima de 70 é "fácil", acima de 50 é "médio", abaixo disso "difícil".
- As entidades por tipo são limitadas a 8 nomes por categoria na saída.
- Tipos de entidade exibidos: `ORG` (Instituições), `PER` (Pessoas), `LOC` (Locais), `EVENT` (Eventos), `POLICY` (Políticas), `LAW` (Leis).
