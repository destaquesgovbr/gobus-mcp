# ui://readability-dashboard

Dashboard **HTML auto-contido** (SVG + tabela + JSON island, sem referências externas) de legibilidade por agência.

**URI:** `ui://readability-dashboard`
**Fonte:** as mesmas do [`gobus://readability-report`](readability-report.md): 20 agências mais ativas (catálogo), janela de 90 dias com janela efetiva quando o Flesch parou.

## Conteúdo

- Barras horizontais com o Flesch **limitado a 0–100**, coloridas pelas faixas únicas (muito difícil, difícil, médio, fácil).
- Tabela `# · Agência · Flesch · Artigos · Palavras/art.`; agência sem dado aparece com "—" (nunca 0.0) e sem barra.
- Subtítulo com a janela analisada ou a janela efetiva ("dados até MM/AAAA").
- JSON island `#readability-data` com `avgReadabilityFlesch` (limitado), `avgReadabilityFleschRaw` e `null` quando não há dado. Nomes passam por `html.escape` e o JSON escapa `</`.

!!! note "Migração para MCP App no G3"
    Este HTML é o legado. No G3 o recurso vira um MCP App (SEP-1865) ligado à tool `gobus_get_readability_recommendations`, sem dados embutidos no HTML (o payload vem no `structuredContent`).
