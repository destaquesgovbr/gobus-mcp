# gobus://themes

Taxonomia de temas usada para classificar os artigos do acervo. Cada tema tem um nome de exibição e um código curto (`code`). Serve de vocabulário controlado para entender e referenciar as categorias temáticas da plataforma.

**URI:** `gobus://themes`
**Atualização:** consultado ao vivo na `graphql-api` a cada leitura (sem cache local).

## Formato

Markdown com uma lista de temas. Cada item traz o nome de exibição e, entre parênteses, o código curto.

```
# Taxonomia de Temas

- **Saúde** (`saude`)
- **Educação** (`educacao`)
- **Economia e Finanças** (`economia`)
- **Meio Ambiente** (`meio-ambiente`)
- **Trabalho e Emprego** (`trabalho`)
```

## Quando usar

Carregue este resource quando o usuário falar em "temas", "pautas" ou "categorias", ou antes de interpretar resultados de `detect_trends` — que reportam crescimento por tema. Conhecer a taxonomia ajuda o LLM a mapear um assunto livre do usuário para o tema correto e a apresentar nomes de tema consistentes com a plataforma.
