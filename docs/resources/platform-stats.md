# gobus://platform-stats

KPIs agregados da plataforma Destaques Gov.BR nos últimos 30 dias: total de artigos, temas ativos, agências ativas e média diária de publicação. Dá ao LLM uma noção de escala e de atividade recente do acervo.

**URI:** `gobus://platform-stats`
**Atualização:** consultado ao vivo na `graphql-api` a cada leitura (janela fixa de 30 dias; sem cache local).

## Formato

Markdown com um cabeçalho de período e quatro métricas em lista.

```
# Plataforma Destaques Gov.BR — Últimos 30 dias

- **Total de artigos:** 12.480
- **Temas ativos:** 28
- **Agências ativas:** 41
- **Média diária:** 416.0 artigos/dia
```

## Quando usar

Carregue este resource quando o usuário pedir um panorama geral ("o quão ativo está o governo?", "qual o tamanho do acervo?") ou para dar contexto de escala antes de uma análise. Ele também serve de sanidade: se o total ou a média diária vierem zerados, é sinal de que a `graphql-api` ou o pipeline de ingestão pode estar com problema, e vale alertar antes de prosseguir com outras tools.
