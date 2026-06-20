# Tools

O Gobus MCP expõe 7 tools que cobrem busca de notícias, leitura de artigos, resolução e perfil de entidades, rede de co-menções, analytics por agência e detecção de tendências.

| Tool | Descrição | Quando usar |
|------|-----------|-------------|
| [search_news](search-news.md) | Busca notícias por texto livre e/ou agência | Encontrar artigos sobre um tema, obter `uniqueId` para leitura completa |
| [get_article](get-article.md) | Conteúdo completo de um artigo pelo ID | Ler o texto integral, features e entidades mencionadas de um artigo |
| [resolve_entity](resolve-entity.md) | Resolve um nome para o `entityId` canônico | Descobrir o ID canônico de uma entidade antes de usar perfil ou rede |
| [get_entity_profile](get-entity-profile.md) | Perfil completo: cobertura temporal + relacionadas | Entender a presença de uma entidade na mídia ao longo do tempo |
| [get_entity_network](get-entity-network.md) | Rede de co-menções ao redor de uma entidade | Mapear quem aparece junto com uma entidade nas notícias |
| [get_agency_analytics](get-agency-analytics.md) | Métricas de publicação de agências num período | Comparar volume, sentimento e legibilidade entre agências |
| [detect_trends](detect-trends.md) | Temas em crescimento (janela vs baseline) | Radar de pautas em alta; o que está crescendo agora |

Todas as tools retornam **Markdown formatado diretamente** (não JSON). O formato é desenhado para consumo direto por LLMs como Claude — o texto já vem pronto para ser apresentado ao usuário ou usado como contexto, sem necessidade de parsing adicional.
