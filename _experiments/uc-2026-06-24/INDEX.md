# Experimento Gobus MCP — 10 Use Cases
> **Data:** 2026-06-24 | **Servidor:** destaquesgovbr-gobus-mcp (Cloud Run, streamable-http stateless)

## Status dos Use Cases

| UC | Nome | Status | Tools usadas | Chamadas |
|----|------|--------|-------------|---------|
| UC-01 | Briefing Diário (Min. Saúde) | ✅ Completo | `gobus_search_news`, `gobus_get_agency_analytics`, `gobus_get_article` | 5 |
| UC-02 | Comparativo Fazenda × Planejamento (Reforma Tributária) | ✅ Completo | `gobus_search_news`, `gobus_get_agency_analytics` | 3 |
| UC-03 | Trajetória "Mais Médicos" | ✅ Completo (dados parciais por limitação histórica) | `gobus_resolve_entity`, `gobus_get_entity_profile`, `gobus_search_news`, `gobus_get_article` | 7 |
| UC-04 | Radar de Tendências | ✅ Completo | `gobus_detect_trends`, `gobus_search_news` | 4 |
| UC-05 | Release sobre Emprego Formal (Min. Trabalho) | ✅ Completo | `gobus_search_news`, `gobus_get_article` | 5 |
| UC-06 | Rede Institucional (Min. Comunicações) | ✅ Completo | `gobus_resolve_entity`, `gobus_get_entity_network`, `gobus_search_news` | 3 |
| UC-07 | Evolução do Sentimento em Saúde | ⚠️ Parcial | `gobus_get_agency_analytics`, `gobus_search_news` | 2 |
| UC-08 | Coordenação Cross-Agency | ✅ Completo | `gobus_detect_trends`, `gobus_search_news` | 10 |
| UC-09 | Benchmark de Legibilidade | ⚠️ Parcial | `gobus_get_agency_analytics`, `gobus_search_news`, `gobus_get_article` | 17 |
| UC-10 | Boletim Semanal para o Cidadão | ✅ Completo | `gobus_detect_trends`, `gobus_search_news`, `gobus_get_article` | 12 |

---

## Achados Recorrentes (aparecem em 2+ UCs)

**Sentimento sempre 0% positivos** — O campo `positivos` de `gobus_get_agency_analytics` retornou 0% em 100% dos registros testados, para todas as agências e períodos. Não é possível distinguir se é ausência de classificador, threshold mal calibrado para linguagem governamental, ou bug de indexação. Impede qualquer análise diferencial de tom entre agências. UCs afetados: UC-01, UC-02, UC-07, UC-09. Impacto: **alto**.

**Campo `agency_key` / `agency` sempre `None` nos artigos** — `gobus_search_news` e `gobus_get_article` retornam o campo de agência como `None` em todos os artigos recuperados. Para identificar a agência de origem, os agentes foram forçados a fazer parsing manual do path da URL (`gov.br/<agency-key>/...`). Isso não é escalável e quebra filtragens automáticas. UCs afetados: UC-01, UC-03, UC-04, UC-06, UC-08. Impacto: **alto**.

**`limit` não respeitado em `gobus_search_news`** — O parâmetro `limit` é ignorado ou sobreposto por um mínimo interno: `limit=10` retornou 19 artigos (UC-01); `limit=5` retornou 20 artigos (UC-07). O comportamento real não está documentado e induz a erros de paginação. UCs afetados: UC-01, UC-07. Impacto: **médio**.

**Ausência de `date_from`/`date_to` em `gobus_search_news`** — Não há filtro temporal na busca. Artigos de datas muito variadas (2024–2026) aparecem misturados nos resultados, dificultando análises com janela temporal definida (ex.: "últimos 7 dias", "últimos 30 dias"). Os agentes contornaram o problema priorizando artigos pelo topo da lista retornada, mas sem garantia de recência. UCs afetados: UC-02, UC-04, UC-08, UC-10. Impacto: **alto**.

**Cobertura histórica limitada (corpus começa em 2025/2026)** — O banco não cobre publicações anteriores a fins de 2025 de forma confiável. Use cases que pediram análise de longa trajetória (2013–2026 para Mais Médicos; 2020–2022 para pandemia) foram respondidos apenas de forma parcial, com inferências a partir de snippets recentes. O índice NER canônico começa apenas em 2026-03. UCs afetados: UC-03, UC-07. Impacto: **alto** para análises históricas.

**Query literal de categoria taxonômica não funciona em `gobus_search_news`** — Buscas com o rótulo exato de categoria do `gobus_detect_trends` (ex.: "Esportes e Lazer", "Minorias e Grupos Especiais") retornam resultados pobres ou fora do período, porque os artigos usam termos específicos, não o rótulo. A taxonomia interna do `detect_trends` não é exposta para consultas. UCs afetados: UC-04, UC-08, UC-10. Impacto: **médio**.

**Campo `author` ausente** — O campo de autoria retorna `None` em todos os artigos da busca, mesmo quando o artigo completo (via `gobus_get_article`) contém autores no rodapé. Impede análise de comunicação intra-ministerial (ex.: qual unidade da Fazenda lidera). UCs afetados: UC-01, UC-02. Impacto: **baixo**.

**Legibilidade categórica sem score numérico** — `gobus_get_agency_analytics` retorna apenas o label `"legibilidade difícil"` (sem score Flesch ou equivalente). Todas as agências testadas caem na mesma categoria, tornando benchmarks inter-agências impossíveis via API. Adicionalmente, o campo fica ausente no mês corrente (mês parcial), gerando artefato de comparação. UCs afetados: UC-02, UC-09. Impacto: **médio**.

**`agency_key` inválida retorna 0 resultados sem mensagem clara** — Chaves tentadas como `"trabalho"` (UC-05), `"ciencia"`, `"comunicacoes"`, `"justica"`, `"meio-ambiente"`, `"mre"`, `"infraestrutura"`, `"esportes"` (UC-09) não retornaram resultados. Não há endpoint documentado que liste as chaves válidas; o resource `gobus://agencies` não estava acessível nesta sessão. UCs afetados: UC-05, UC-09. Impacto: **médio**.

**`gobus_get_entity_network` com `depth=2` excede limite de tokens MCP** — A resposta com 252.335 caracteres (~2.768 nós) não cabe no contexto do protocolo MCP e precisou ser salva em arquivo e lida em blocos via script Python. Em ambiente de produção sem acesso a sistema de arquivos, a chamada falharia silenciosamente ou truncaria. UCs afetados: UC-06. Impacto: **médio** (uso específico de depth=2).

**Artigos com prefixo `[MOCK]` no corpus de produção** — Dois artigos do Ministério do Esporte apresentaram o prefixo `[MOCK] Resumo gerado para teste local` nos snippets, indicando que o pipeline de geração de resumos não processou esses artigos reais e substituiu por mock de teste. UCs afetados: UC-04. Impacto: **médio** (qualidade do dado).

---

## Dimensões de Melhoria

### 1. Dados

**Sentimento não populado:** O campo `positivos` retorna 0% sistematicamente para todas as agências testadas (Saúde, Fazenda, Planejamento, e outras). Não está claro se é ausência de modelo treinado para linguagem governamental, threshold errado ou bug de indexação. Sem esse dado, UCs de análise de tom e comparação editorial ficam inviáveis.

**Campo `agency_key` ausente nos artigos:** Os artigos indexados não trazem o campo de agência preenchido. O dado existe implicitamente no path da URL gov.br, mas não é extraído no pipeline de ingestão. Isso força parsing manual de URL em todo UC que precise identificar a origem do artigo.

**Artigos MOCK em produção:** Artigos do corpus de produção contêm o prefixo `[MOCK] Resumo gerado para teste local`, indicando que resumos de teste vazaram para o índice. Requer limpeza do corpus e ajuste no pipeline de ingestão.

**Corpus com cobertura histórica parcial:** O banco cobre de forma confiável apenas publicações de 2025/2026 e o índice NER canônico começa em 2026-03. Para análises de programas com histórico de mais de 2 anos (ex.: Mais Médicos desde 2013, pandemia 2020-2022), a ferramenta entrega resultados parciais.

**Legibilidade categórica:** A classificação de legibilidade entrega apenas "difícil" / ausente — sem score numérico, sem distinção "fácil" / "moderado" / "difícil" robusta, e sem cálculo no mês corrente (artefato de pipeline).

**`author` não extraído:** Autores identificados no rodapé dos artigos não são trazidos para o campo `author` do índice. Impede análises editoriais por unidade autora dentro de um ministério.

**Fins de semana ausentes na analytics:** `gobus_get_agency_analytics` com granularidade `DAY` não retorna entradas para sábado e domingo — sem distinguir "nenhuma publicação" de "dado não coletado".

### 2. Design das Tools

**`gobus_search_news` sem filtro temporal:** A ausência de `date_from`/`date_to` é o gap de design mais recorrente. Afetou 4 UCs. Todos os UCs com janela temporal definida precisaram de workarounds manuais.

**`limit` não respeitado:** O parâmetro é ignorado abaixo de um mínimo interno (~20). Não está documentado o comportamento real, causando confusão sobre paginação.

**`agency_key` não validada:** A tool aceita qualquer string e retorna 0 resultados quando a chave é inválida, sem mensagem de erro ou sugestão de chave correta. Um endpoint de listagem (`gobus_list_agencies`) ou validação na própria tool eliminaria esse ponto de atrito.

**`gobus_get_entity_network` sem paginação/truncamento para `depth=2`:** A resposta explode em tamanho com profundidade 2 (252k chars), excedendo o limite de contexto MCP. Deveria haver um limite automático de nós retornados ou uma tool auxiliar para explorar o subgrafo filtrado por tipo de nó (`gobus_get_entity_subgraph(entity_id, node_type, limit)`).

**`gobus_detect_trends` não retorna agências por tema:** O resultado identifica o tema e o volume, mas não lista quais agências contribuíram. Para UC-08 (cross-agency), isso exigiu 9 chamadas adicionais de `gobus_search_news`. Incluir um campo `top_agencies: [{code, count}]` no retorno de cada tema reduziria o caso de uso de 10 chamadas para 1.

**Taxonomia interna não exposta:** As categorias do `gobus_detect_trends` (ex.: "Esportes e Lazer", "Minorias e Grupos Especiais") não têm correspondência documentada com termos de busca. Queries literais com esses rótulos retornam resultados ruins.

**`gobus_get_entity_profile` limitado a 2026-03+:** O parâmetro `date_from` funciona, mas a cobertura de entidades NER é estruturalmente limitada ao período pós-lançamento. Deveria ser documentado como limitação explícita na descrição da tool.

### 3. Qualidade dos Prompts / Use Cases

**UC-07 (sentimento histórico 2020-2022)** ficou parcial por impossibilidade estrutural: o corpus não cobre esse período. O UC pressupôs cobertura histórica que não existe. Para casos de uso de análise histórica, a harness deveria verificar cobertura antes de executar ou fornecer contexto sobre as datas disponíveis.

**UC-09 (benchmark de legibilidade)** pressupôs a existência de score numérico Flesch. Como a API retorna apenas categoria, o agente adaptou para análise qualitativa editorial — válida, mas metodologicamente diferente do proposto. O UC deveria ou ter sido descartado ou redefinido antes da execução.

**UC-04 e UC-10:** A estratégia de buscar por rótulo de categoria (`"Esportes e Lazer"`) após `gobus_detect_trends` é um anti-padrão recorrente. Os prompts futuros deveriam orientar os agentes a construir queries semânticas a partir do tema detectado, não usar o rótulo literalmente.

**UC-05:** A `agency_key="trabalho"` não existe; a chave correta seria `"trabalho-e-emprego"` ou similar. O UC poderia ser melhorado incluindo uma etapa inicial de `gobus_detect_trends` ou listagem de agências para confirmar a chave antes da busca.

**UC-06:** A análise de rede com `depth=2` gerou volume excessivo de dados para o que o UC precisava. `depth=1` seria suficiente para mapear o ecossistema imediato do MCom e evitar a sobrecarga de tokens.

### 4. Schema / Infraestrutura

**Transporte:** O servidor usa `streamable-http stateless` (não SSE), conforme a nota de UC-04 que registrou um erro MCP `-32602` transitório numa execução anterior, supostamente por reinicialização do Cloud Run ou expiração de sessão. O problema foi transitório e não se repetiu na execução documentada.

**`ReadMcpResourceTool` indisponível na sessão:** UC-09 identificou que o resource `gobus://agencies` — que listaria as chaves válidas de agência — não estava acessível como deferred tool na harness. Isso agravou o problema de chaves inválidas sem feedback.

**`gobus_get_entity_network` excede contexto MCP:** Resposta de 252k chars para `depth=2` precisa de paginação no lado do servidor ou truncamento automático por tamanho de resposta. Em ambientes sem sistema de arquivos local, a tool ficaria inutilizável com esses parâmetros.

---

## Próximos Passos Recomendados

### P1 — Alta prioridade (bloqueiam UCs inteiros)

1. **Implementar `date_from`/`date_to` em `gobus_search_news`** — Gap mais recorrente (4 UCs afetados). Permite filtrar por janela temporal definida sem consumir múltiplas páginas.

2. **Popular campo `agency_key` nos artigos indexados** — Extrair do path da URL no pipeline de ingestão. Afeta 5 UCs e elimina a dependência de parsing manual.

3. **Investigar e corrigir sentimento zerado** — Verificar se o classificador está calibrado para linguagem governamental, se o campo está sendo computado, e documentar claramente a disponibilidade do dado. Afeta 4 UCs de análise editorial.

4. **Documentar e validar chaves de agência** — Expor um endpoint ou resource listando as chaves válidas (`code` + `label`) e retornar mensagem de erro útil quando uma chave inválida é usada. Alternativamente, garantir que `ReadMcpResourceTool` acesse `gobus://agencies` na harness.

### P2 — Média prioridade (degradam qualidade, têm workarounds)

5. **Corrigir comportamento do parâmetro `limit` em `gobus_search_news`** — Documentar o mínimo real ou corrigir para respeitar o valor solicitado.

6. **Adicionar `top_agencies` ao retorno de `gobus_detect_trends`** — Campo `[{code, label, count}]` por tema eliminaria 5–9 chamadas extras em UCs cross-agency (como UC-08).

7. **Limitar ou paginar `gobus_get_entity_network` com `depth=2`** — Implementar limite automático de nós retornados ou criar `gobus_get_entity_subgraph(entity_id, node_types, limit)` para consultas filtradas.

8. **Expor score numérico de legibilidade** — Incluir `avg_readability_score` (Flesch ou equivalente) no retorno de `gobus_get_agency_analytics` além do label categórico. Habilita UC-09 como originalmente proposto.

9. **Limpar artigos MOCK do corpus de produção** — Identificar e remover artigos com prefixo `[MOCK]` e ajustar o pipeline para não vazar mocks de teste no índice.

### P3 — Baixo impacto imediato (melhorias incrementais)

10. **Expor campo `author` nos artigos indexados** — Extrair autores do rodapé dos artigos no pipeline de ingestão.

11. **Incluir dias sem publicação explicitamente na analytics diária** — Retornar `{date, articles: 0}` para sábado/domingo em vez de omitir a entrada, para distinguir "sem publicação" de "sem dado".

12. **Publicar dicionário de termos por categoria taxonômica** — Mapear cada categoria do `detect_trends` para queries semânticas equivalentes no `search_news`, orientando a composição de prompts.

13. **Tool `gobus_get_agency_summary(agency, date_from, date_to)`** — Combina volume + temas dominantes + artigos de maior engajamento em uma chamada. Reduziria UC-01 (briefing) de 5 chamadas para 2.
