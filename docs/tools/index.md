# Tools

O Gobus MCP expõe **14 tools**, todas somente leitura (`readOnlyHint`) e sem `outputSchema`: o cliente recebe o Markdown direto no `content`. Quatro são tools de [MCP App](../apps/index.md) (`get_readability_recommendations`, `score_article`, `detect_anomalies` e `forecast_trends`): além do Markdown completo no `content`, devolvem o payload estruturado (`structuredContent`, com o mesmo Markdown até 6 KB em `summary`) que o painel desenha. As tools de preview `gobus_dev_preview_*` só existem em desenvolvimento ([Desenvolvimento e validação](../apps/desenvolvimento.md)).

| Tool | Descrição | Quando usar |
|------|-----------|-------------|
| [search_news](search-news.md) | Busca notícias por texto livre e/ou agência | Encontrar artigos sobre um tema, obter `uniqueId` para leitura completa |
| [get_article](get-article.md) | Conteúdo completo de um artigo pelo ID | Ler o texto integral, métricas e entidades mencionadas de um artigo |
| [resolve_entity](resolve-entity.md) | Resolve um nome para o `entityId` canônico | Descobrir o ID canônico de uma entidade antes de usar perfil ou rede |
| [get_entity_profile](get-entity-profile.md) | Perfil completo: série mensal, agências, cópias idênticas e relacionadas | Entender a presença de uma entidade ao longo do tempo |
| [get_entity_network](get-entity-network.md) | Rede de co-menções centrada numa entidade, sem as genéricas | Mapear quem aparece junto com uma entidade nas notícias |
| [get_agency_analytics](get-agency-analytics.md) | Métricas de publicação de agências num período | Comparar volume, sentimento e legibilidade entre agências |
| [get_agency_summary](get-agency-summary.md) | Resumo executivo de uma agência | Overview rápido: volume, legibilidade, sentimento e temas em alta |
| [detect_trends](detect-trends.md) | Temas em crescimento (janela vs baseline) | Radar de pautas em alta |
| [get_readability_recommendations](get-readability-recommendations.md) | Ranking e diagnóstico de legibilidade (Flesch) | Avaliar a clareza dos textos de uma agência e priorizar ajustes de estilo |
| [score_article](score-article.md) | Nota editorial de um artigo contra o benchmark da agência | Avaliar um release antes/depois da publicação |
| [get_policy_lifecycle](get-policy-lifecycle.md) | Ciclo de vida mensal de uma política pública | Saber se uma política está em anúncio, implementação ou rotina |
| [detect_anomalies](detect-anomalies.md) | Picos/quedas de temas e sinais de entidade (silêncio coordenado, concentrada, rajada), cientes do defeso | Achar assuntos fora do padrão, por domínio de política |
| [forecast_trends](forecast-trends.md) | Projeção de temas por share-of-voice em 3 janelas, com horizonte de 1 a 28 dias | Antecipar pautas e o volume esperado |
| [get_message_coherence](get-message-coherence.md) | Coerência de mensagem entre agências sobre uma entidade ou um tema (índice 1–5: entidades, timing, enquadramento e tom), com as republicadoras à parte | Saber se o governo fala em sintonia sobre um programa ou pauta |

## Convenções de saída

- **Markdown, não JSON** — o texto já vem pronto para o LLM apresentar ao usuário. Nas tools de app, o `content` traz o Markdown completo e o `structuredContent` traz o mesmo texto em `summary` (primeiro campo, cortado em 6 KB) e os dados do painel (até 20 KB).
- **Nulo nunca vira 0.** Métrica sem dado aparece como "indisponível", com um aviso `> …` explicando a fonte e, quando conhecido, "desde dd/mm/aaaa". O estado das fontes está em [`gobus://health/pipelines`](../resources/health-pipelines.md).
- **Flesch:** fórmula adaptada ao português (Martins et al., 1996; `readabilityFleschPtbr`), limitada a 0–100 (o valor bruto aparece quando foi limitado), com as faixas de Martins 0–25 muito difícil · 25–50 difícil · 50–75 fácil · 75–100 muito fácil e meta de serviço 50. Notícia de governo fica na divisa entre "difícil" e "muito difícil": no acervo inteiro (22/10/2026), a mediana é 25,2, cerca de 5 pontos acima da fórmula inglesa, e 2,5% dos valores brutos são negativos (mín −339) — por isso o exibido é limitado a 0–100 e a média exibida também. Sem o pt-BR (API sem o campo ou artigo ainda não recalculado), vale a fórmula inglesa do `textstat` (legado), sempre com o aviso "Flesch pt-BR indisponível" — as duas escalas nunca se misturam numa média.
- **Para explorar:** as tools de texto (search_news, get_article, get_agency_summary, detect_trends, get_policy_lifecycle, get_message_coherence, rede e perfil) terminam com um rodapé de até 3 chamadas concretas, montadas do próprio resultado (até 400 B), por exemplo `gobus_get_article(unique_id="…")`. As 4 tools de MCP App não têm rodapé.
- **Links:** artigo citado vira `` [título](url) · `id` `` quando a API traz a URL (inclusive nos artigos representativos dos temas em alta, `ArticleSummary.url`).
- **Compatibilidade:** quando a graphql-api ainda não tem um campo novo (erro "Cannot query field"), a tool repete a consulta sem ele e segue por 1 h no formato antigo (ver [Arquitetura](../arquitetura.md#compatibilidade-de-schema)).
- **Agências:** códigos do catálogo (`gobus://agencies`); um código inválido devolve sugestões (`"ms"` → `saude`, `"trabalho"` → `trabalho-e-emprego`).
- **Janelas:** "últimos N dias" são dias fechados em BRT, de D−N até D−1 (ontem), salvo indicação.
