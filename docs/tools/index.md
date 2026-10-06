# Tools

O Gobus MCP expõe **13 tools**, todas somente leitura (`readOnlyHint`) e sem `outputSchema`: o cliente recebe o Markdown direto no `content`.

| Tool | Descrição | Quando usar |
|------|-----------|-------------|
| [search_news](search-news.md) | Busca notícias por texto livre e/ou agência | Encontrar artigos sobre um tema, obter `uniqueId` para leitura completa |
| [get_article](get-article.md) | Conteúdo completo de um artigo pelo ID | Ler o texto integral, métricas e entidades mencionadas de um artigo |
| [resolve_entity](resolve-entity.md) | Resolve um nome para o `entityId` canônico | Descobrir o ID canônico de uma entidade antes de usar perfil ou rede |
| [get_entity_profile](get-entity-profile.md) | Perfil completo: cobertura temporal + relacionadas | Entender a presença de uma entidade ao longo do tempo |
| [get_entity_network](get-entity-network.md) | Rede de co-menções ao redor de uma entidade | Mapear quem aparece junto com uma entidade nas notícias |
| [get_agency_analytics](get-agency-analytics.md) | Métricas de publicação de agências num período | Comparar volume, sentimento e legibilidade entre agências |
| [get_agency_summary](get-agency-summary.md) | Resumo executivo de uma agência | Overview rápido: volume, legibilidade, sentimento e temas em alta |
| [detect_trends](detect-trends.md) | Temas em crescimento (janela vs baseline) | Radar de pautas em alta |
| [get_readability_recommendations](get-readability-recommendations.md) | Ranking e diagnóstico de legibilidade (Flesch) | Avaliar a clareza dos textos de uma agência e priorizar ajustes de estilo |
| [score_article](score-article.md) | Nota editorial de um artigo contra o benchmark da agência | Avaliar um release antes/depois da publicação |
| [get_policy_lifecycle](get-policy-lifecycle.md) | Ciclo de vida mensal de uma política pública | Saber se uma política está em anúncio, implementação ou rotina |
| [detect_anomalies](detect-anomalies.md) | Picos sustentados e cobertura concentrada | Achar assuntos fora do padrão (reescrita no G2) |
| [forecast_trends](forecast-trends.md) | Projeção de temas em 3 janelas | Antecipar pautas (reescrita no G2) |

## Convenções de saída

- **Markdown, não JSON** — o texto já vem pronto para o LLM apresentar ao usuário.
- **Nulo nunca vira 0.** Métrica sem dado aparece como "indisponível", com um aviso `> …` explicando a fonte e, quando conhecido, "desde dd/mm/aaaa". O estado das fontes está em [`gobus://health/pipelines`](../resources/health-pipelines.md).
- **Flesch:** escala inglesa do `textstat`, limitada a 0–100 (o valor bruto aparece quando foi limitado), com faixas únicas 0–25 muito difícil · 25–50 difícil · 50–75 médio · 75–100 fácil.
- **Agências:** códigos do catálogo (`gobus://agencies`); um código inválido devolve sugestões (`"ms"` → `saude`, `"trabalho"` → `trabalho-e-emprego`).
- **Janelas:** "últimos N dias" são dias fechados em BRT, de D−N até D−1 (ontem), salvo indicação.
