> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — crítica de completude, gerado em 2026-10-05 por agente read-only (wf_98f5ad51-e18). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Crítica de completude da Fase 2.5: lacunas, contradições e riscos

Fiz tudo em modo somente leitura. Usei `git show`/`git grep` em `origin/main`, introspecção e consultas ao GraphQL público, testes do fastmcp em memória com `python -` via stdin e sem bytecode, e uma chamada real a `gobus_detect_trends` nesta sessão. Não gravei nenhum arquivo.

**Nome da fase.** O pedido diz "plano Fase 5", mas não existe "Fase 5" no repositório. O `BLUEPRINT.md:147-180` tem só as Fases 1 a 3, e `_plan/*.md` não menciona Fase 4 nem 5. O texto calculado fala em "Fase 2.5" com 5 frentes. Vale confirmar o nome do arquivo e do branch do plano (sugestão: `feature/fase2.5-…`).

## 1. Lacunas e respostas verificadas

**L1. Basta tirar `limit:` para consertar `get_readability_recommendations(agency_key)`?**
Não. A segunda chamada passa `query: ""` (`tools/get_readability_recommendations.py:183-187`), e ao vivo isso dá `search(query:"")` → `"Query must not be empty"`.
- O que funciona: `articles(limit:3, filter:{agencies:["saude"]}, sort:DATE)`, testado ao vivo (`found: 4155`).
- `ArticleSort` só tem `RELEVANCE|DATE|TRENDING|VIEWS`, então não há ordenação por Flesch. O "pior artigo" precisa ser escolhido no cliente, em até 250 artigos de 2026-03..06, que é o único período com Flesch.

**L2. Qual SDL usar no teste de contrato?**
Não o `graphql-api/docs/reference/schema.graphql`, que está **desatualizado**.
- Foi regenerado pela última vez em 096f57a (01/07) e não tem `policies(domain, lifecyclePhase, limit, offset)`. Essa query existe ao vivo e em `resolvers/entities.py:144-160`, com `min(limit,200)`.
- Use introspecção ao vivo ou `scripts/export_schema.py` (o Makefile chama na linha 35).
- O gobus-mcp não tem `graphql-core` na venv; o relatório gobus-internals usou o da venv da graphql-api.

**L3. Hoje o LLM recebe Markdown?**
Não.
- Todas as 13 tools são `-> str`, e o fastmcp 3.4.2 gera `outputSchema` com `x-fastmcp-wrap-result` e `structuredContent={"result": md}`. Confirmei em memória.
- Confirmei também nesta sessão: `gobus_detect_trends` devolveu `{"result":"# Radar de Tendências…"}`, ou seja, Markdown escapado como string JSON.
- `@mcp.tool(output_schema=None)` desliga isso (testado: `outputSchema None`, `structured None`).
- A assinatura do decorator tem `name, description, tags, output_schema, annotations, meta, app`.
- `fastmcp.tools.ToolResult` (`fastmcp.tools.base`) e `fastmcp.apps.AppConfig` (campos `resource_uri, visibility, csp, permissions, domain, prefers_border`) importam sem erro.

**L4. Corrigir o resolver de `trendingEntities` basta?**
Não.
- O `scorer.py` não tem top-N: todas as entidades que passam nos filtros são gravadas por `persist.py`.
- Com baseline zero, `vr ≥ 428,6` (`signals.py` usa piso de 0,001), contra 1,5 a 20 para entidades com histórico.
- Com `WHERE computed_at = MAX(computed_at)`, o top-50 continua dominado por entidades novas. O **Laplace no data-platform é obrigatório** para o radar ter sentido.
- O filtro por igualdade é seguro: um único `engine.begin()`, logo `NOW()` é igual em todas as linhas da execução.
- A próxima migração é a **029** (a última é `028_remove_orphan_gazetteer_policies.sql`). O `db-migrate.yaml` é só `workflow_dispatch`.
- Os testes existem: graphql-api em `tests/datasources/test_trending_entities_datasource.py` e `tests/resolvers/test_trending_entities.py`; data-platform em `tests/unit/jobs/test_trend_detection_{persist,scorer}.py` e `tests/unit/dags/test_compute_entity_trending.py`.

**L5. O defeso termina mesmo em 25/10?**
Sim, para a esfera federal. Há segundo turno presidencial: agencia_brasil, 2026-10-05T00:02Z, "Lula e Flávio vão disputar 2º turno para presidente da República".

**L6. Quais valores `domainFilter` pode ter?**
`policies` ao vivo, paginado (2.441 itens): `None` 983, ECONOMIC 316, SOCIAL 271, EDUCATION 202, ENVIRONMENT 200, GOVERNANCE 193, HEALTH 184, SECURITY 92.
- Isso só cobre POLICY. O top trending tem EVENT, LAW, PER e PRODUCT.
- Para os outros tipos é preciso um mapa agência-dona → domínio, curado no gobus.

**L7. Dá para montar séries de tema por agência com datas explícitas (para excluir o defeso do baseline)?**
Não pela `agencyAnalytics`: `topThemes` é sempre `[]` (`resolvers/analytics.py:172`; e o tipo nem tem `name`).
- `trendingThemes` só aceita `windowDays`/`baselineDays`, sempre contados a partir de "agora" em UTC.
- O único caminho no cliente é contar `articles(limit:1, filter:{themeLabel, startDate, endDate}){found}` por tema e janela (cerca de 25 temas × 2 janelas).
- Não há tema depois de 26/09 de qualquer forma.

**L8. Onde está o nome humano da agência?**
`agencies` devolve `label == code` em **156 de 156** casos. `isRepublisher` vem `true` para agencia_brasil, tvbrasil e ebc. O nome só existe em `agencyAnalytics.agencyName` e `Article.agencyName`.

**L9. O sentimento existe?**
Sim, no Typesense; a graphql-api é que lê a chave errada.
- Typesense, `articles(filter:{sentiment:[…]}, 01/09..26/09)`: positive 2.582, negative 532, neutral 686.
- `agencyAnalytics(saude, 01/09..26/09)` no mesmo período: `avgSentimentScore null`, `pctPositive 0.0`.
- Quem grava: o worker grava `features.sentiment={label,score}` (`data-science/.../handler.py:271-273`).
- Quem lê certo: `data-platform/.../postgres_manager.py:548-549` lê `features->'sentiment'->>'label'`.
- Quem lê errado: a graphql-api lê `features->>'sentiment_score'`/`'sentiment_label'` em três SQLs (`postgres.py:326-412`).

**L10. Por que tema, resumo e sentimento estão nulos?**
Amostras de 100 artigos/dia:
- 24/09: summary 70, theme 98, entities 98;
- 28/09: summary 0, theme 0, entities 99;
- 03/10: 0 / 0 / 48 de 50.

A chamada combinada (`handler.py:191-197`) falha ou volta vazia, e o NER, que é uma chamada separada com `NER_MODEL_ID`, continua funcionando.
- O `enrichment-worker.tf` só define `NER_MODEL_ID`. Sem `ENRICHMENT_MODEL_ID`/`BEDROCK_MODEL_ID`, o default é `anthropic.claude-3-haiku-20240307-v1:0` (`handler.py:76-79`).
- Hipótese não verificada: modelo descontinuado ou sem acesso. Só os logs confirmam, e gcloud está vedado aqui.

**L11. Por que Flesch e wordCount pararam?**
O que está verificado:
- O `feature_worker` sempre grava `word_count` quando roda (`features.py:257-271`).
- O backfill 9c90bb0 é de 2026-06-29 20:00 −03, com janela default 01/06..01/07.
- Amostras de wordCount: 06-29 80/100, **06-30 0/100**, 07-15 0, 09-20 0.
- **Defeito real, verificado ao vivo:** `data-platform/clients/graphql_client.py:121,134,161,177,191` declaram `$uniqueId: ID!`, e a API responde `"Unknown type 'ID'"`. O schema não tem o tipo ID; a assinatura é `newsById(uniqueId: String!)`. A partir de 2026-05-26, `GRAPHQL_API_URL` está configurado (`infra/terraform/feature-worker.tf:103-106`, também em `typesense-sync-worker.tf:116` e `bronze-writer.tf:111`).

O que **não** está confirmado é que esse defeito seja a causa:
- a cobertura de maio e junho é irregular (05-28 wc 0 com annotations 15; 06-03 100 com annotations 99; 06-20 58/58 com annotations 0);
- o Typesense, alimentado pelo `typesense-sync` com o mesmo `ID!`, continua indexando.

Trate como dois itens: um bug latente certo e um incidente a diagnosticar nos logs.

**L12. A escala de Flesch é para português?**
Não. `features.py:56-62` usa `textstat.flesch_reading_ease` sem `set_lang` (textstat 0.7.13), ou seja, a fórmula inglesa. Numa frase de teste, `set_lang('pt')` mudou o valor de 25,9 para −30,5.

**L13. Em que branch está a correção do CLAUDE.md?**
A linha `baseDailyAvg` só existe em 7021868, em `origin/feature/fase2-analytics`, que **não** foi mergeado em main. O `main` local está ahead 3 / behind 2. Crie o branch a partir de `origin/main` e decida se faz cherry-pick de 7021868 já com a correção.

**L14. As dependências de dev estão prontas?**
Não. A venv não tem `ruff`, `freezegun`/`time-machine`, `playwright`, `graphql-core` nem `respx`. Há conflito de restrições:
- o pyproject pede `pytest ^8` e `pytest-asyncio ^0.23`;
- a venv tem 9.1.0 e 1.4.0;
- `poetry lock` + `install` vai **rebaixar** essas versões, a menos que o pyproject seja atualizado.

**L15. Como ficou a issue #3?**
Verifiquei ao vivo: `search("Resumo gerado para teste local")` → `found: 4600`.

## 2. Contradições resolvidas

| Tema | Versões | Correta (evidência) |
|---|---|---|
| Sentimento | live-probe: "nenhum dado desde maio"; upstream: chave errada na graphql-api | **upstream** (L9) |
| Artigos MOCK | gobus-internals: "pelo menos 1"; live-probe: 4.600 | **4.600** (L15). O `DELETE` da issue apagaria 4.600 notícias reais |
| Fix de readability | "tirar `limit` e fatiar no cliente" | **insuficiente**: query vazia é rejeitada (L1) |
| Filtro de trendingEntities | `= MAX(computed_at)` (upstream) contra `>= MAX − 6h` (live-probe) | **igualdade**. A janela de 6h misturaria linhas que saíram na última execução |
| Data de parada do Flesch | 06-30 / 07-01 / "julho" | **06-30** (0/100); o último dia com dado é 06-29. Não é um pipeline que "morreu": os dados de mar–jun vêm do backfill (L11) |
| Data de parada do tema | ~09-25 / ~09-26 | parcial em 25/09 (49/175), **zero a partir de 26/09** (amostra de 28/09 = 0/100) |
| Agências zeradas: 15 / 28 / 39 | critérios diferentes | todos válidos. Ao vivo, gestao 38, inss 15, secom 11, agu 19, casacivil 10, funai 8 em **julho**, e zero depois. O "15" do brief é o critério de ≥10 artigos em junho e 0 em setembro. Conclusão: **não usar lista fixa** |
| Queda de volume no defeso: −35% / −43% / −33,9% | depende da janela escolhida | parametrizar; não fixar constante |
| SDL de referência | upstream citou `docs/reference/schema.graphql` | desatualizado (L2) |
| CLAUDE.md "corrigir nota" | tratado como se estivesse em main | só existe no branch não mergeado (L13) |
| "Claude Code mostra structuredContent" | afirmação do mcp-apps-spec | **confirmado** nesta sessão (L3) |

## 3. Riscos não óbvios para o plano

1. **Health check enganoso mesmo depois do fix.** O top-50 por score sempre inclui as linhas da última execução, então `max(computedAt)` parece recente. A métrica certa é a fração de linhas com mais de 7 dias no top-N, ou a fração com `vr` ≥ 428 (baseline zero).
2. **Apps no Claude Code.** Com `ToolResult(structured_content=payload)`, o modelo no Claude Code vê o payload, não o Markdown. É obrigatório incluir `summary` (Markdown) no payload. As tools que não são app devem usar `output_schema=None`.
3. **Mudar a fórmula de Flesch para PT muda tudo.** Quando o feature-worker voltar, qualquer `set_lang('pt')` invalida o benchmark "~33.5", a meta de 50 e as faixas de cor. O clamp tem de ser na escala atual (inglesa), com testes parametrizados.
4. **Janelas rolantes até "agora" em UTC.** Elas incluem o dia parcial e o atraso de indexação do Typesense (live-probe: 14 contra 155 em 05/10). Picos e quedas falsos aparecem às segundas-feiras e no dia corrente. As janelas próprias do cliente devem fechar em D−1 23:59 no horário de Brasília (`endDate` = dia seguinte).
5. **message_coherence no formato do BLUEPRINT não funciona hoje.** A assinatura do BLUEPRINT é `(theme, agencies)` com `articles(filter:{themeLabel})` (`BLUEPRINT.md:64`), e `themeLabel` está morto depois de 26/09, assim como Flesch depois de 06-30. O tom só existe via filtro `sentiment` do Typesense até 25/09. Exige assinatura alternativa com `entity_id`/`policy`.
6. **Retomada pós-25/10.** As 39 agências que voltam geram `bc=0` em massa e inflam `trendingEntities` justamente quando o Laplace ainda não estiver em produção. O fix da Frente 2 precisa estar no ar **antes de 25/10**, ou o gobus suprime entidades com `vr ≥ 428`.
7. **Build não reproduzível.** O Dockerfile faz `pip install .` sem lock, com fastmcp `^3.0`. Uma versão 3.5+ pode mudar o comportamento de `app=`/wrap-result ou a API privada `_additional_http_routes` (`server.py:57`), sem nenhum CI de teste no gobus.
8. **Falha de upstream mascarada como valor.** `null → 0.0` e `or 0.0` produzem nota constante 5,6 no `score_article` e Flesch 0,0 em tudo. Toda tool nova precisa de um estado explícito de "indisponível".

## Implicações para o plano

- **Frente 0 (fora do gobus, bloqueia as frentes 3 e 4):**
  - incidente da chamada combinada do enrichment, verificando o modelo default `claude-3-haiku-20240307`;
  - incidente de features: investigar o feature-worker e corrigir `ID!`→`String!` em `graphql_client.py`, nas 5 queries;
  - a graphql-api lê a chave de sentimento errada.
- **Frente 1:**
  - a readability usa `articles(limit, filter:{agencies}, sort:DATE)`;
  - `output_schema=None` nas tools que não são app;
  - teste de contrato por introspecção ao vivo ou `export_schema.py`, adicionando `graphql-core` às dev-deps;
  - fixar `fastmcp>=3.4.2,<3.5`, atualizar `pytest`/`pytest-asyncio` no pyproject antes do `poetry lock`, e o Dockerfile instala do lock;
  - CLAUDE.md a partir de `origin/main` mais cherry-pick de 7021868 corrigido;
  - issue #3 reescrita como `UPDATE summary=NULL` + reindexação (4.600 linhas);
  - `docs/deploy.md`: "HTTP stateless `/mcp` + compat `/sse`".
- **Frente 2:**
  - PR na graphql-api: `computed_at = (SELECT MAX…)`, chaves de sentimento, testes em `tests/datasources|resolvers`;
  - PR no data-platform: DELETE na mesma transação, Laplace, ≥2 dias distintos na janela, migração 029 manual;
  - prazo: em produção antes de 25/10.
- **Frente 3:**
  - funções puras com `today` injetável (sem freezegun);
  - dona da entidade = `entity.agencyKey` ou, se nulo, a agência com mais artigos em `entityCoverage(DAY, 90d)` excluindo republicadoras;
  - `domainFilter` = enum das 7 categorias de `policies.domain` mais um mapa agência→domínio para tipos que não são POLICY;
  - defeso de 04/07 a 25/10 confirmado, com "última data ativa" por agência calculada dinamicamente via `agencyAnalytics(DAY)`;
  - aviso explícito de "temas sem classificação desde 26/09".
- **Frente 4:** `ToolResult` com `structured_content` incluindo `summary`; estado "indisponível" para Flesch, wordCount, tema e sentimento; validação visual fora do Claude Code.
- **Frente 5:** assinatura `(entity_id | theme, agencies, date_from, date_to)`. Usar entidades (`canonicalId`, `salience`) e timing em `America/Sao_Paulo`; tom só até 25/09 via filtro `sentiment` do Typesense; republicadoras via `agencies{isRepublisher}`; sem dispersão de Flesch.
