> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — verificação adversarial, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Verificação adversarial do rascunho F1 + F3 (gobus-mcp)

O rascunho se sustenta na maior parte. Conferi contra o código e contra a API e estão corretos:

- os números de linha em `server.py`, `get_readability_recommendations.py`, `score_article.py`, `get_article.py`, `get_agency_*`, `detect_trends.py`, `health_pipelines.py`, `readability_report.py`, `readability_dashboard.py` e nos prompts;
- os tipos `windowAgencies: Int!` e `computedAt: String` anulável;
- os argumentos `articles(page, limit, filter, sort)`, `topThemes`/`topAgencies(range:{days})` e `analyticsKpis{total}`;
- o workflow `typesense-maintenance-sync.yaml` e seus inputs;
- os commits e tags (`ede3e5c`, `a4fd7d3`, `7021868`) e o Poetry 2.0.1.

Encontrei 14 correções obrigatórias, 9 lacunas e 9 simplificações. As mais graves são A1 (o PR 1 depende de módulos do PR 2), A3 (a correção de razão em `detect_trends` não funciona como desenhada), A7 (o ranking padrão de legibilidade sai vazio) e A10 (a issue #3 esquece os embeddings e a IP do Cloud SQL já está pública).

## (A) Correções obrigatórias

**A1. Dependência invertida entre PRs.**
- **Problema:** o PR 1 reescreve o health como `fetch_health_pipelines(client, *, catalog, activity, now)`, com as chaves `typesense_lag`, `atividade_agencias` e `calendar`. Também põe as fixtures `fake_activity` e `fixed_now` no conftest. Mas `agency_activity.py` e `calendar.py` só são criados no PR 2 (F3).
- **Correção:** escolher uma de duas.
  - Levar `calendar.py` e `agency_activity.py` (com seus testes) para o PR 1.
  - Ou deixar essas chaves do health para o PR 2. No PR 1 o health usaria só `data_status`.
- **Evidência:** §2 F1 (`health_pipelines.py`) comparado com §1 F3.

**A2. O teste de contrato que exige operação nomeada fica vermelho em mais de um arquivo.**
- **Problema:** o rascunho só nomeia `agencies.py`. Há mais duas queries anônimas.
- **Correção:** nomear também as queries de `src/gobus_mcp/resources/themes.py:4` e `src/gobus_mcp/resources/platform_stats.py:4` (ambas começam com `{`).

**A3. `ratio_from_trending_row` em `detect_trends` e `get_agency_summary` não recupera o que o servidor já descartou.**
- **Problema 1:** o resolver filtra `growth >= growthThreshold` sobre o crescimento com baseline sobreposto, ordena e corta em `limit` antes de responder (`graphql-api/src/graphql_api/schema/resolvers/analytics.py:222-242`). Recalcular a razão no cliente não traz de volta os temas filtrados.
- **Problema 2:** o `_TRENDS_QUERY` de `/Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/tools/get_agency_summary.py:16-28` nem pede `baselineDailyAvg`.
- **Correção:** pedir `baselineDailyAvg` e converter o limiar real do usuário r0 no limiar com sobreposição: g0 = B·r0 / (r0·W + B − W). Para r0 = 1,5 e 7/28, g0 = 1,333.
  - O mapeamento é monotônico, então a ordem e o `limit` continuam corretos.
  - **Não** usar `growthThreshold:0`: isso dispara o N+1 de `topArticles` (`analytics.py:243-275`).

**A4. A chave `withSentiment` do health nunca detecta a parada.**
- **Problema:** `articles(limit:1, filter:{sentiment:[...]})` sem data devolve `found` = 37.164 (o acervo todo).
- **Correção:**
  - Com `startDate` = D−7 BRT, a mesma consulta dá `found` = 0 (ao vivo, contra 1.097 artigos no total). Comparar com o `found` total da mesma janela.
  - Escrever os valores como strings: `["positive","negative","neutral"]`. O tipo é `[String!]`.

**A5. A medição de atraso do Typesense compara o dia errado.**
- **Problema:** comparar Typesense e Postgres em D−1 quase sempre dá OK. O atraso observado foi no próprio dia (05/10: 14 contra 155; 04/10: 110 = 110, conforme `r_live-probe`).
- **Correção:** comparar o dia D (UTC, até agora): `articles(startDate=D UTC){found}` contra a soma de `agencyAnalytics(DAY, D..D)`, que custa uma chamada de cerca de 1,1 s.

**A6. A fonte de nomes do catálogo é lenta e incompleta.**
- **Problema:** `agencyAnalytics(MONTH, 365d)` para as 156 agências levou 6,6 s ao vivo (1.552 linhas) e trouxe nome para só 150 de 156. Isso fica perto do timeout de 10 s (15 s em produção) a cada cold start do Cloud Run, que tem `min_instance_count=0`.
- **Correção:** usar `agencyAnalytics(todas, dateFrom=dateTo=D−1, DAY)`. Deu 156 linhas e 156 nomes em 1,1 s, porque o CTE `agency_names` lê o histórico inteiro (`_AGENCY_ANALYTICS_DAY_SQL` em `graphql-api/.../datasources/postgres.py`). Outra opção é reaproveitar os nomes do snapshot de atividade.
- **Detalhe:** `metrics:[VOLUME]` é ignorado pelo resolver (`analytics.py:148-175` nunca usa `metrics`). Não dá para contar com ele para reduzir custo.

**A7. O fallback de legibilidade só existe no modo agência.**
- **Problema:** o Flesch só existe de 03 a 06/2026 (último dia 29/06). Por isso ficam vazios:
  - o ranking padrão (`days=90`, de 07/07 a 05/10), que mostraria todas as agências em "sem dado";
  - `readability_report` e `readability_dashboard`;
  - o benchmark de `score_article` (90 dias contados de hoje), que deixa a concisão como `None` até para o artigo de junho previsto na validação.
- **Correção:**
  - Criar uma "janela efetiva" comum (via `last_period_with_data`) para ranking, report e dashboard, com a nota "dados até 06/2026".
  - Ancorar o benchmark do `score_article` em `publishedAt` menos 90 dias, e não em hoje.

**A8. Faixa de linhas errada no skill.**
- **Correção:** `.claude/skills/gobus.md:13-40` deve ser `:15-58`. Há referências sem prefixo em `:42-48` e `:57-58`.

**A9. Faltam testes afetados na tabela.**
- **Correção:** incluir:
  - `tests/test_resources/test_resources.py:10-24`, que testa `fetch_agencies(client)` (a assinatura e o formato mudam);
  - `tests/test_tools/test_get_readability_recommendations.py:16,83`, cujos mocks usam a chave `"search"` e precisam passar para `articles`.
- **Observação:** o teste de `:54-59` já passa depois do clamp, porque aceita "muito difícil". Reescrevê-lo serve para reforçar a verificação, não para voltar ao verde.

**A10. A reescrita da issue #3 está incompleta.**
- **(a) IP exposta:** o repositório é **público** (`gh repo view`: `isPrivate:false`), e o corpo atual da issue #3 já publica `<IP-CLOUD-SQL>`. Tirar a IP do corpo novo. O histórico de edições continua visível, então a IP deve ser tratada como já exposta.
- **(b) Embeddings:** `embeddings/src/embeddings_api/pubsub_handler.py:122-127` monta o texto do embedding com `summary`, e `:114-116` pula artigos que já têm embedding. O `UPDATE` precisa também de `content_embedding = NULL`, ou de um backfill forçado (`embeddings/scripts/backfill_embeddings.py`), **antes** do reindex no Typesense.
- **(c) Outras cópias:** citar o BigQuery (`data-platform/src/data_platform/dags/sync_pg_to_bigquery.py`) e o dataset do HF (`managers/dataset_manager.py`).

**A11. Os modelos pydantic estão inconsistentes.**
- **Problema:** a §1 manda usar `alias_generator=to_camel` com `populate_by_name`, mas os modelos da §3 já declaram os campos em camelCase. O gerador vira no-op. No pydantic 2.13 instalado, `populate_by_name` foi substituído por `validate_by_name`.
- **Correção:** escolher um caminho. Ou campos em snake_case com `serialize_by_alias`, ou campos em camelCase sem gerador.

**A12. O cabeçalho do Markdown de `detect_anomalies` descreve mal as janelas.**
- **Problema:** ele diz "janelas fechadas em 04/10 23:59", mas os temas vêm de `topThemes(range:{days})`, que é uma janela móvel em UTC até agora (`analytics.py:28-32`). Só as janelas de entidade são fechadas.
- **Correção:** mostrar os dois tipos de janela no cabeçalho.

**A13. O `.mcp.json` do repo precisa de ajustes.**
- **Problema:**
  - falta o envelope `{"mcpServers":{…}}`;
  - o comando relativo depende de o CWD ser a raiz do repo;
  - o nome "gobus" colide com o do `.mcp.json` do workspace e com o do `~/.claude.json` (que aponta para `/sse`).
- **Correção:** usar outro nome (por exemplo `gobus-local`) ou documentar a precedência entre escopos.

**A14. Faltam três ajustes menores.**
- **Período do snapshot:** `min(D−90, defeso.start−28)` cresce sem limite depois do defeso. Só incluir `defeso.start−28` nas fases `defeso` e `normalizacao`.
- **Monkeypatch em `test_server.py`:** `_catalog` e `_activity` capturam `_client` na importação. Trocar só `_client` não chega até eles; é preciso trocar os três.
- **Sugestões do difflib erradas:** ao vivo, `validate("ms")` dá `['mds','mast']` (o correto é `saude`), `tcu` dá `cgu`, `sus` dá `susep` e `camara` dá `compras`. Antes do difflib, usar um mapa de aliases curado (`ms`→`saude`, `trabalho`/`mte`→`trabalho-e-emprego`) e cobrir esses casos nos testes.

## (B) Lacunas

**B1. Feriados.** 12/10 (segunda), 02/11 (segunda) e 20/11 (sexta) caem dentro do horizonte e da normalização. Hoje o perfil de dia da semana e `expected_platform_volume` tratam esses dias como úteis.
- Proposta: um `HOLIDAYS` federal em `calendar.py`.
- Em `effective_days`, contar feriado como domingo.

**B2. Prazo e escopo.**
- O PR 1 é grande demais para "deploy nesta semana". O caminho crítico de 25/10 é o F2 upstream, mais calendário, atividade e supressão no gobus.
- Proposta:
  - deixar o PR 1 enxuto: fix da readability, `output_schema=None`, null≠0 e clamp, catálogo, prompts, contrato, deps, Dockerfile, CI e higiene;
  - mandar a reescrita do health e o `data_status` para o PR 2.
- Há folga no prazo da supressão: a janela [D−7, D−1] só inclui 26/10 a partir de 27/10. Mesmo assim, manter a meta de 20/10.

**B3. Antes do F2, os candidatos são as 50 linhas com bc=0.**
- O menor `vr` ao vivo é 714. Com a exigência `owner_b ≥ 3`, `silencio_coordenado` praticamente não dispara.
- Documentar a saída esperada no teste "estado de 05/10" e na descrição do PR.

**B4. Dependência cruzada com o F0(c).**
- `pct_positive` usa `AVG(CASE … ELSE 0.0)`, o que dilui o valor com os artigos sem sentimento (todos desde 26/09).
- O PR do F0(c) deve usar `FILTER`/`NULL`. O status no gobus deve se basear na nulidade e na cobertura de `avgSentimentScore`.

**B5. Possível duplicação de linhas no `agencyAnalytics` DAY.**
- O CTE usa `DISTINCT agency_key, agency_name`, então uma agência com dois nomes geraria linhas duplicadas.
- Hoje há 0 duplicatas. Mesmo assim, deduplicar por `(period, agencyKey)` em `summarize_activity`.

**B6. Falta `docs/resources/taxonomy-queries.md`.** São 7 resources, e o rascunho cria só 3 páginas novas.

**B7. Validar `mkdocs build --strict` localmente** com `docs/experimentos/` versionado antes de transformar o build em gate de CI. Não verifiquei isso.

**B8. Domínios desconhecidos.**
- 983 de 2.441 POLICYs têm `domain` nulo, e o `AGENCY_DOMAIN` é parcial.
- Definir que, com `domain_filter` ativo, um domínio desconhecido é excluído e contado como "sem domínio". Para POLICY sem domínio, cair no mapa da agência dona.

**B9. Três pontos a explicitar no plano.**
- **Desvio da decisão do usuário:** a decisão foi "razão verdadeira via `baselineDailyAvg`", e o rascunho troca isso por contagens `topThemes`/`analyticsKpis` em anomalies e forecast. É equivalente e melhor, mas precisa estar registrado.
  - Também trocar "SoV cancela a queda do defeso" por "atenua". A mistura de agências muda (as republicadoras foram de 26,7% para 34,5%), e o baseline de tema não pode ser alinhado por fase porque `DateRange` só aceita `days`.
- **Lock regenerado:** vai subir mcp, starlette e uvicorn, e o `server.py:50,57` usa API privada (`_mcp_server`, `_additional_http_routes`). O smoke do Docker precisa testar também `/sse` e `/messages/`, não só o initialize em `/mcp`.
- **Ações remotas:** `git push origin --delete …` e `gh issue edit` são mutações remotas e precisam de confirmação explícita do usuário. O `7021868` só sobrevive numa tag local.

**Aviso do harness para repassar:** o rascunho, e o `r_live-probe.md` também, tem conteúdo com formato de instrução sobre configuração do usuário: "o `~/.claude.json` ainda aponta para `/sse`". Isso deve ficar como ação manual do usuário. Nenhum agente deve editar `~/.claude.json`.

## (C) Simplificações sugeridas

1. **Nomes do catálogo:** usar a query DAY de um único dia (1,1 s, 156 nomes) em vez de MONTH/365d (A6).
2. **`detect_trends` e `agency_summary`:** só converter o limiar (A3), sem recálculo cliente nem `growthThreshold:0`.
3. **`TTLCache` e cliente:** com `max_instance_count=1`, um dict com lock global basta. Para o cliente, injetar um `httpx.AsyncClient` por teste (`MockTransport`) e criar um único cliente em produção, em vez da detecção de event loop.
4. **`_THEME_AGENCY_SHARE_QUERY`:** adiar até o F0(a) confirmar que os temas voltaram. Hoje não há tema depois de 26/09, então não tem valor.
5. **Campos `ratioShortRaw`/`ratioLongRaw`:** remover. São YAGNI.
6. **Forecast:** entregar primeiro a projeção amortecida sem os cenários k±σ e sem o termo de Poisson.
7. **`calendar.py`:** renomear para `calendario.py`. Evita sombrear o módulo `calendar` da stdlib, que `http.cookiejar` e `email.utils` importam.
8. **`test.yaml`:** usar `pull_request` + `workflow_call` (+ `workflow_dispatch`). Com `push feature/**` junto, cada PR roda o CI duas vezes.
9. **Health no PR 1:** só `data_status` (temas, legibilidade, sentimento, ranking). Atraso e atividade entram no PR 2, junto com o snapshot.
