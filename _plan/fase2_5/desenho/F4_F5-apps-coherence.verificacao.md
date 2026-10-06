> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — verificação adversarial, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

**(A) Correções obrigatórias**

1. **`TextContent(text=markdown)` não valida.** No mcp 1.28 o campo `type` de `TextContent` é `Literal['text']` com `required=True`.
   - Correção: `ToolResult(content=markdown, structured_content=...)`. Testei e ele gera `[{'type':'text','text':…}]` sozinho. A alternativa é `TextContent(type="text", text=...)`.

2. **`importlib.metadata.version("gobus-mcp")` pode quebrar em produção depois do F1.** Hoje funciona porque o `Dockerfile` roda `pip install .` e a venv tem `gobus_mcp-0.1.0.dist-info`. Se o F1 passar a instalar só as dependências a partir do lock (`--no-root` ou export para requirements), aparece `PackageNotFoundError` ao renderizar o resource.
   - Correção: try/except com fallback para `"0+unknown"`, ou `__version__` em `src/gobus_mcp/__init__.py` (hoje vazio).

3. **`addopts="-m 'not ui'"` deixa os testes de rede rodando no CI.** O F5 cria o marker `live`, e o teste de contrato do F1 pode usar introspecção ao vivo.
   - Correção: `markers=["ui: …","live: …"]` e `addopts="-m 'not ui and not live'"`.

4. **O Makefile não é novo.** `Makefile` em `origin/main` já tem `docs-serve` e `docs-build`; os alvos devem ser acrescentados.
   - A receita "servidor `&` … `kill %1`" em linhas separadas não funciona no make, porque cada linha roda num shell próprio.
   - Correção: uma linha só, com `$$!`, espera ativa (`until curl …`) e `trap kill`.

5. **`.mcp.json` → `/mcp` no commit 12 está no lugar errado e sem verificação.**
   - É escopo do F1, segundo a própria lista de frentes.
   - O histórico registra o problema: o commit 33d3ba8 ("reverter .mcp.json para /sse — Claude Code não suporta spec 2025-03-26") e `CLAUDE.md:18-19` ("Claude Code CLI envia GET em vez de POST → falha").
   - Correção: tirar do F4. No F1, só trocar depois de testar o Claude Code atual contra `/mcp`.
   - No passo (C), prever fallback para `/sse` no claude.ai: `CLAUDE.md:48` diz que Desktop/claude.ai usam `/sse`.

6. **A convenção do CLAUDE.md fica violada sem nota.** `CLAUDE.md:150` diz "Tools retornam Markdown formatado (não JSON)". As 4 tools de app passam a expor JSON (`structuredContent`) no Claude Code.
   - Correção: o commit de docs atualiza a regra com a exceção (tools de app = `summary` Markdown + payload) e o orçamento de tokens.

7. **`coverage.articlesWithFlesch` e `agencies[].articlesWithFlesch` não têm fonte.** A introspecção de `AgencyPeriodMetrics` dá `period, agencyKey, agencyName, articleCount, avgSentimentScore, pctPositive, pctNegative, avgReadabilityFlesch, avgWordCount, topThemes`, sem contagem de artigos com Flesch.
   - Correção: amostrar `articles(limit:250, filter:{agencies:[k], startDate, endDate}){features{readabilityFlesch wordCount}}` por agência (até 30 aliases, custo a medir) ou remover o campo.
   - `lastDayWithData` também não tem fonte definida. Especificar a origem: varrer `agencyAnalytics(DAY)` ou o health do F1.

8. **`daily[≤28]` por tema em `spikes` e `forecast.themes` sai caro.**
   - Nenhuma query dá série diária de tema com intervalo de datas. `themeArticleCounts(days, level)` é móvel, `trendingThemes` é agregado e `articlesTimeline` está quebrado e não filtra por tema.
   - Só daria com aliases `articles(limit:1, filter:{themeLabel, startDate, endDate}){found}`: 10×28 = 280 no forecast e 15×28 = 420 nas anomalias.
   - Correção: `daily: null` para itens de tema na v1. Para entidades vale manter, porque `entityCoverage(DAY)` já devolve a série.

9. **O prefixo `dgb_` não identifica só agências.** Ao vivo, `entity(id:"dgb_pe-de-meia")` é `type: POLICY`, `agencyKey: null`, e o `entitySearch("Pé-de-Meia")` devolve 3 `dgb_*` POLICY.
   - Correção: a exclusão em E é `dgb_{code}` com `code ∈ agency_catalog` (ou `type ORG` com `agencyKey`), nunca `startswith("dgb_")`.
   - Conferi os ids de calibração: `Q575545` = Bolsa Família (POLICY); `dgb_pe-de-meia` existe.

10. **A janela de 90 dias do benchmark do scorecard é nominal.** `articles(limit:250, sort:DATE)` pega os 250 mais recentes. Na agencia_brasil (cerca de 40 artigos/dia) isso cobre uns 6 dias; na saude, uns 40.
    - Correção: `window{from,to}` deve vir do min/max real de `publishedAt` da amostra, ou paginar.
    - `agencyAnalytics` MONTH/WEEK exclui o `dateTo` (BETWEEN com meia-noite). Para o `date_to` inclusivo da readability, passar `date_to + 1`.

11. **O teste "sem referência externa" pode ficar impossível.** O `_svg.js` precisa de `createElementNS("http://www.w3.org/2000/svg", …)`.
    - Correção: a regex só olha `src=`, `href=`, `url(` e `import`, ou põe o namespace SVG numa allowlist. Não usar `https?://` em qualquer posição.

12. **Ordem do TDD nos commits do PR.** O mini-host Playwright e as fixtures (commit 7) vêm depois dos apps (2–6), então o JS dos apps nasce sem teste vermelho.
    - Correção: mini-host e fixtures logo depois do commit 1. Cada app entra como `test: … (red)` e depois `feature: … (green)`.

13. **O F3 dentro do PR único com F4 e F5 conflita com o prazo de 25/10.**
    - A salvaguarda do lado do gobus (`BASELINE_ZERO_SUPPRESSED` e filtro de `computedAt`) é o plano B caso o F2 atrase. O 8571× já está no ar hoje.
    - Correção: PR-A com F3 (funções puras + tools, sem UI) em produção até cerca de 20/10, e PR-B com F4+F5. Continuam sendo poucos PRs: F1, F3, F4+F5.

14. **Tom "cortado em 25/09 detectado via health do F1" não funciona.** O health usa `agencyAnalytics.pctPositive`, que a chave errada da graphql-api (F0c) deixa sempre em 0.
    - Correção: não cortar `endDate`. Medir a cobertura de tom na janela via Typesense (`sentiment`) e aplicar a regra de cobertura abaixo de 50%.
    - O mesmo vale para "temas sem classificação desde 26/09" e "Flesch desde 30/06": detectar dinamicamente (ex.: `themeArticleCounts(days:3)` vazio com `analyticsKpis` > 0) e passar a data em `DataNotice.since`. Nada de data fixa no código ou no JS, porque o F0 vai consertar e fazer backfill.

15. **`summary` com `[MOCK]` contamina o enquadramento F do F5.** São 4.600 artigos de 2025-09-24 a 2026-02-27 com summary "[MOCK] Resumo gerado para teste local — …", e a issue #3 ainda não foi aplicada.
    - Correção: ignorar summaries que começam com `[MOCK]`.

16. **Snippet do `server.py`:** `app_tool_kwargs` é usado mas não está no import `from gobus_mcp.ui import …`.

17. **Afirmações conferidas e corretas:**
    - `@mcp.tool(app=…, meta=…, annotations={"readOnlyHint":True}) -> ToolResult` dá `meta` com `ui/resourceUri` e `ui{resourceUri, visibility}`, `outputSchema None` e `readOnlyHint=True`. `output_schema=None -> str` não gera `structuredContent`. O default sai como `{"result": md}`.
    - `@mcp.resource(..., title=, app=AppConfig(prefers_border=True))` dá MIME `text/html;profile=mcp-app` e `meta.ui.prefersBorder` também no `resources/read`.
    - `getattr(caps, "extensions")` funciona (o campo vem como extra).
    - `run_http_async(middleware=…)` está em `fastmcp/server/mixins/transport.py:236`.
    - Terraform (`infra/terraform/gobus-mcp.tf`): `allUsers` em 125-130, comentário falso em 121-123, `min=0`, `max=1`, `3600s`, `GOBUS_REQUEST_TIMEOUT=15.0`.
    - Config do Claude Desktop, log do Desktop e `cloudflared` existem.
    - Empacotamento pelo poetry-core (`glob("**/*")`) e `.gitignore` sem padrão que exclua os assets.
    - Todos os campos e argumentos das queries do F5: `articles(page:Int!, limit:Int!, filter, sort)`, `ArticlesResult{articles, page, found}`, `EntityType{text, type, count, canonicalId, salience}`, `ArticleFilter.sentiment/entityCanonical/themeLabel`, `entityCoverage(entityId, dateFrom, dateTo, granularity)`, `entitySearch(query, entityType, limit)`, `Agency.isRepublisher`.
    - Offset BRT: 197 contra 200.
    - 6 testes no dashboard, incluindo `test_html_contem_canvas_chartjs`.

**(B) Lacunas**

- **Retrabalho entre F1 e F4.** O F1 já reescreve `get_readability_recommendations.py` (query, null, clamp, catálogo) e `score_article.py` (recusa em vez de 5,6). O F4 reescreve os dois de novo e os testes também (`test_score_article.py` 2 vezes). Fazer a separação `build_*_payload` + `render_*_markdown` já no F1; o F4 só liga o app.
- **Docs das tools de app.** `docs/tools/` não tem página para `detect_anomalies`, `forecast_trends`, `score_article` nem `readability_recommendations`, e o F4 muda o contrato delas. `docs/apps/*` não substitui a convenção de uma página por tool. Dizer também se as `gobus_dev_preview_*` ficam isentas.
- **Mock frágil.** O `FakeGraphQLClient.set_responses` usa `side_effect` em ordem. Com `gather` (páginas 2–4 do F5) mais o `agency_catalog` com cache TTL do F1, a ordem fica frágil. Propor despacho por nome de operação (`CoherenceArticles`, `CoherenceTone`, …) e uma fixture que limpe o cache do catálogo e o `lru_cache` entre testes. Usar a fixture `fake_client`, não instanciar a classe do conftest.
- **`tzdata` é obrigatório, não opcional.** Não dá para garantir `/usr/share/zoneinfo` no `python:3.12-slim` (base Debian recente). Põe em risco `ZoneInfo("America/Sao_Paulo")` no F3 e no F5. Adicionar `tzdata` ao pyproject.
- **Validação no claude.ai só depois do merge.** Como o merge já faz o deploy, a validação no claude.ai não serve de gate do PR. Ou o túnel `cloudflared` passa a ser obrigatório antes do merge, ou o plano declara validação pós-deploy com rollback por revert do squash.
- **Interações nas tools de preview.** `gobus_dev_preview_*` valida só o render inicial. Os `tools/call` do app chamam a tool real (nome fixo no JS), que hoje devolve `unavailable`. Isso precisa constar. Também é preciso uma descrição "DEV — dados fictícios" e um prefixo no `summary`, para o modelo do Desktop não tratar a fixture como dado real.
- **`ui://readability-dashboard` lido direto vira casca vazia.** Qualquer cliente que leia o resource sem a tool recebe um template sem dados. Documentar.
- **Branch e worktree.** O branch local `feature/fase2-analytics` tem trabalho não commitado. Recomendar `git worktree add … origin/main` para os subagentes, em vez de trocar de branch no checkout atual.
- **Sem estimativa.** Hoje é 05/10, e o F1 precisa ser mergeado antes. Faltam estimativas por commit e uma data-alvo do PR-A (F3) antes de 25/10.
- **Não verificável offline.**
  - MCPJam: "não chama tools", `--reporter junit-xml`, e se Node 20 atende o `engines` do 5.13.0.
  - basic-host: `implementation.ts:52-66`, `bun` como devDependency, e `npm run start` em `examples/basic-host` contra `npm start` na raiz (o relatório de spec usa a raiz).
  - `playwright = "^1.63"`: confirmar no PyPI. O cache local tem chromium-1243.
  - Marcar esses pontos como "conferir no clone" no plano.
- **Sync API do Playwright com pytest-asyncio em `asyncio_mode=auto`.** Preferir `playwright.async_api` para evitar o erro "Sync API inside the asyncio loop".
- **F5: prior.** O aviso de "início truncado" sempre dispara para entidades grandes (Bolsa Família). Comparar a taxa diária do prior com a da janela.
- **F5: resolução de entidade.** `entitySearch(limit:1)` pode pegar a variante errada (`dgb_programa-pe-de-meia` tem 0 artigos). Usar `limit:3`, escolher o maior `articleCount` e listar as alternativas.
- **F5: calibração.** São 4 cortes calibrados com 3 rótulos do UC-03, que foram dados por um agente, não são gabarito. Tratar como sanity check e não como ajuste.
- **`.claude/skills/gobus.md` desatualizado.** Não tem UC de coerência e usa nomes sem `gobus_`.

**(C) Simplificações sugeridas**

- Remover o job de CI `package`. Em runtime, `PYTHONPATH=/app/src` faz o código e os assets virem da árvore, e `test_render_app` (via `importlib.resources`) já cobre o caso.
- Tom S no F5: trocar o join por `uniqueId` com paginação por aliases de contagem `articles(limit:1, filter:{…, agencies:[a], sentiment:[l]}){found}`. Com até 12 emissores × 3 rótulos, é uma requisição de cerca de 0,7 s, exata e sem teto de 1000.
- Tirar `include_republishers` da assinatura: o usuário decidiu que as republicadoras ficam sempre separadas.
- Tirar `projection` e `daily` de tema do contrato v1, ou deixar sempre `null`.
- Unificar `tests/ui/` com `tests/test_ui/`: por exemplo, `tests/test_ui/` para os testes puros e `tests/browser/` para o Playwright, com o marker por arquivo. Cada diretório novo precisa de `__init__.py`, como os existentes.
- Aplicar `annotations={"readOnlyHint": True}` às 14 tools no F1, não só às de app.
