> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — relatório de investigação, gerado em 2026-10-05 por agente read-only (wf_98f5ad51-e18). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Fase 2.5: medição do comportamento real do gobus-mcp e da graphql-api (2026-10-05, ~22h UTC)

**Resumo.** Das 9 tools medidas, 1 falha sempre e quase todas as outras devolvem saída enganosa ou vazia. Não é o defeso que causa isso. São três pipelines parados:

| Pipeline | Parado desde | Efeito |
|---|---|---|
| Legibilidade (Flesch / wordCount) | 2026-06-30 | todo Flesch aparece como 0.0 |
| Classificação de tema | ~2026-09-25 | janelas de tema de 3d e 7d ficam vazias |
| Sentimento | — (nenhum dado desde maio) | sem eixo de tom |

Além disso, `trendingEntities` só mostra linhas velhas com ratios de 714× a 8571×, e `gobus://health/pipelines` diz "OK" para dois desses pipelines que estão parados.

**Como medi.** O MCP desta sessão é o servidor local por stdio: o `.mcp.json` do workspace chama `.venv/bin/python3.12 -m gobus_mcp` (PID 93698, iniciado às 19:02, depois do reinício), apontando para a graphql-api pública. O `src/` está igual ao `origin/main`. O `~/.claude.json` ainda aponta o "gobus" para `/sse` remoto. Medi a latência chamando as mesmas funções de tool contra a API pública; o overhead do stdio não entra.

## 1. Tools

| Tool | Funcionou? | Latência | Útil? |
|---|---|---|---|
| detect_anomalies (high/medium/low) | sim | 0,47–0,49 s | **Poluída** |
| forecast_trends (default, horizon 7) | sim | 0,45 s | **Inútil** |
| detect_trends | sim | 0,35 s | **Vazia** |
| readability_recommendations, ranking (sem agência) | sim | 0,63 s | **Falsa** (0.0 em tudo) |
| readability_recommendations("saude") | **ERRO** | 0,60 s | — |
| readability_recommendations("trabalho") | **ERRO** | 0,60 s | — |
| agency_summary("trabalho-e-emprego") | sim | 0,59 s | Mínima (só volume) |
| search_news("eleições", desde 09-28) | sim | 0,29 s | OK |
| score_article (2 artigos recentes) | sim | 0,47 s | **Constante 5.6** |
| policy_lifecycle("Pé-de-Meia") | sim | 1,39 s | **Poluída** (14.882 caracteres) |
| entity_profile("Censo Escolar 2025") | sim | 1,14 s | OK, e mostra que o "em alta" é velho |

### detect_anomalies
- Nas três sensibilidades: "Picos Sustentados: Nenhum pico sustentado detectado." Isso acontece porque `trendingThemes` devolve 0 linhas para 3d/21d e 7d/28d (ver §3.6).
- Em "Cobertura Concentrada" aparecem as mesmas 20 entidades de `trendingEntities(limit:20)`. Exemplos:
  - `Censo Escolar 2025 (EVENT) · volumeRatio 8571.4× · apenas 5 agências`
  - `Projeto Mais Médicos Especialistas · 4000.0×`
  - `Lei nº 14.621, de 2023 · 3714.3× · apenas 1 agências`
  - `Discord (PRODUCT) · 1428.6×`
  - `Pablo Marçal (PER) · 1285.7×`
- A sensibilidade, na prática, só muda o corte em `windowAgencies` (<8, <5, <3). O limiar de ratio (2/3/5×, em `detect_anomalies.py:32-36`) nunca filtra nada, porque o menor ratio é 714×. Resultado: high = 19 concentradas + 1 normal; medium = 15 + 5; low = 9 + 11.
- 46 das 20+ linhas da tabela de origem têm computedAt com mais de 7 dias; detalhe em §3.3. Censo Escolar foi calculado em 2026-07-03.

### forecast_trends
A saída com default e com `horizon_days=7` é idêntica. Só o título muda (`forecast_trends.py:95`; o parâmetro é "apenas informativo", linha 37):

```
| Minorias e Grupos Especiais | 0.22 | estavel | baixa |
| Justiça e Direitos Humanos  | 0.20 | estavel | baixa |
```

- Todos os temas aparecem como "estavel/baixa". Só a janela de 21d tem dados, então o composto é 0,2 × growth21, e s3 = s7 = 0 gera "estavel".
- A nota sobre fim de semana é texto fixo (`forecast_trends.py:107-111`); não há correção nenhuma.

### detect_trends
Devolve: "Nenhum tema em crescimento detectado (últimos 7d vs 28d baseline, threshold 1.5×)". Mesma causa: os temas estão nulos desde 09-25.

### get_readability_recommendations
- **Com agência dá erro** para qualquer chave: `GraphQL errors: Unknown argument 'limit' on field 'Query.search'.` A causa está em `get_readability_recommendations.py:34-36`: a query passa `search(..., limit:)`, mas o SDL (`schema.graphql:580`) não tem esse argumento. Para a chave inválida "trabalho" o mesmo erro aparece antes da mensagem "Sem dados".
- **Ranking geral:** todas as 10 agências aparecem com "0.0 | muito difícil" (Agência Brasil 3582 artigos, MEC 502…), e o texto continua afirmando "Benchmark interno: Agência Brasil (~33.5)" (linha 170, fixo no código). O 0.0 vem do `or 0.0` na linha 141 aplicado a valores nulos.

### get_agency_summary("trabalho-e-emprego")
Só traz "Volume: 9 artigos publicados". Não traz legibilidade (Flesch nulo) nem temas (pipeline de tema parado). Com "trabalho" devolve "Sem dados para agência: `trabalho`" em 0,45 s.

### search_news
Funciona: 188 resultados, o mais recente de 2026-10-05. Há quase-duplicatas da PF (dois "PF divulga balanço parcial…" com sufixos `-3` e `-4`, IDs diferentes). Ponto importante: o Typesense tinha só **14 artigos de 10-05, contra 155 no Postgres**. O dia 10-04 bate (110 = 110), então é atraso de indexação. Isso também atinge `trendingThemes`, que lê do Typesense.

### score_article
Os dois artigos (pf e agencia_brasil) receberam **5.6/10**: "Legibilidade: N/A · Concisão 5/10 — 0 palavras (benchmark 0) · Densidade 8/10 — 10 entidades em 0 palavras". A nota é constante: legibilidade nula vira 5 (`score_article.py:138`), concisão sem base vira 5 (`:50-51`) e qualquer artigo com 2 ou mais entidades tira 8, porque o denominador é forçado a 1 (`:66`). Portanto **todo artigo publicado depois de 2026-06-30 com ≥2 entidades recebe 5.6**. O cabeçalho também mostra a chave no lugar do nome: `[pf] pf`.

### get_policy_lifecycle("Pé-de-Meia")
- A tabela tem cerca de 150 linhas, uma por mês × agência, porque `entityCoverage` devolve por agência e `_analyze_coverage` (`get_policy_lifecycle.py:60-74`) trata cada linha como um período.
- "ANNOUNCED" ficou com uma única linha, MEC 2026-04 (75 artigos). O total real de 2026-04 é 132, e o de 2026-06 é 130.
- A fase atual é a da última linha (TV Brasil 2026-09, 1 artigo; linha 162).
- Os "Artigos Representativos (Fase de Pico)" são de 2026-08 e 2026-09, não do pico, porque vêm de um `search` pelo nome (`:163-174`).
- O período sai cru: `2024-01-01 00:00:00+00`.

### get_entity_profile("Censo Escolar 2025")
Funciona. Mostra 85 artigos, com o pico em 2026-06 (INEP 29 + MEC 28) e apenas 1 artigo em 08 e 1 em 09. Ou seja, a entidade número 1 "em alta" está fria há 3 meses.

## 2. Resources

- **`gobus://health/pipelines`** está enganoso:
  - `trendingScore: OK`. Ele lê a tabela `entity_trending_scores` (`health_pipelines.py:30-37`), mas `Article.features.trendingScore` está nulo em 100% dos artigos dos últimos 30 dias.
  - `flesch: OK — "Flesch positivo em todas as agências amostradas"`. Só procura valores negativos (`:50-57`), e o nulo vira 0.0 (`:94`).
  - `sentiment: DEAD` está correto.
- **`gobus://readability-report`**: 12 agências, todas com `avgReadabilityFlesch 0.0, gapToTarget -50.0`. Das 20 chaves fixas no código, 8 sumiram (6 inválidas + secom/agu, zeradas no período).
- **`ui://readability-dashboard`**: o HTML renderiza com 13 barras de largura 0 e "Palavras/art. 0". Esse URI não aparece no `ListMcpResources` (só 6 resources listados), mas é legível.
- **`gobus://agencies`**: 156 chaves, todas no formato `**abc** (\`abc\`)`, sem nome humano. A query `agencies` devolve `label == code`; `agencyAnalytics.agencyName` traz o nome correto.
- **`gobus://platform-stats`**: 4.184 artigos em 30 dias, 23 temas ativos, 102 agências, 139,5/dia.

## 3. Medições via GraphQL

### 3.1 Volume e defeso
`articlesTimeline` está **quebrado em produção**: `[Errno 404] Could not find a facet field named 'published_date'` (`graphql-api/.../analytics.py:134`). Usei `agencyAnalytics(DAY)` com as 156 agências: 24.648 linhas, 6,8 s.

| Mês | Artigos | Média/dia |
|---|---|---|
| 2026-05 | 5.240 | 169,0 |
| 2026-06 | 6.728 | 224,3 |
| 2026-07 | 4.353 | 140,4 |
| 2026-08 | 4.386 | 141,5 |
| 2026-09 | 4.488 | 149,6 |
| 2026-10 (5 dias) | 700 | 140,0 |

- Por semana: W26 = 1.790, W27 = 1.750, **W28 (06/07) = 670 (−62%)**. Depois sobe devagar: W32 = 954, W36 = 1.100, W40 = 1.084.
- Pré-defeso (05-01 a 07-03) = 205,2/dia; defeso (07-04 a 10-04) = 135,6/dia, ou **−33,9%**. De junho para setembro: −33,3%.
- Fim de semana em setembro: 189,0/dia nos dias úteis contra 41,1/dia no sábado e domingo (4,6×). Exemplos: 09-26 = 51, 09-27 = 23, 10-03 = 50.
- A fatia dos republicadores (agencia_brasil, tvbrasil, ebc) subiu de 26,7% em junho para 34,5% em setembro.

### 3.2 Agências com volume em junho e zero em setembro
- **39 agências.** Com 10 ou mais artigos em junho são **exatamente 15**: gestao 134, secom 131, inss 74, agu 53, casacivil 46, funai 44, ibict 41, icmbio 38, sri 25, abc 20, ird 14, cemaden 12, aids 11, cbtu 11, insa 11.
- Agências ativas: 140 em junho, 103 em setembro.
- Quedas parciais grandes: mds 182→20, planalto 115→12, cidades 81→2, mcom 106→21.

### 3.3 trendingEntities
- O resolver limita a 50 linhas (`entities.py:174`): pedi 5000 e vieram 50.
- **computedAt se espalha por 32 datas distintas, de 2026-06-25 a 2026-10-05.** Só 2 linhas são da última execução (10-05 21:00:20). 46 linhas têm mais de 7 dias, 37 têm mais de 30 dias e 10 são anteriores ao defeso.
- **volumeRatio:** mínimo 714,3, mediana 1000, máximo 8571,4 (todas as 50 acima de 100×; 18 acima de 1000×).
  - O baseline implícito (windowCount / volumeRatio) é **0,007 em todas as 50**. Ou seja, o baseline é 0 e cai no piso `0.001` (`data-platform/.../signals.py:113`), o que dá volumeRatio = windowCount × 142,86.
  - trendingScore ≈ 0,6 × volumeRatio (mínimo 428,8, máximo 5144,1).
- **Causa no código:**
  - `persist.py:10-23` faz UPSERT por PK `entity_id` e nunca apaga linhas.
  - `_TRENDING_ENTITIES_SQL` (`graphql-api/.../postgres.py:479-486`) faz `ORDER BY trending_score DESC LIMIT $1`, sem filtro de `computed_at`.
  - O scorer (`scorer.py:29-30`) só aceita `window_agencies > baseline_agencies`, o que favorece entidades sem histórico.
- O DAG está vivo, mas as linhas novas ficam enterradas (ex.: "Nossa Senhora Aparecida", 857×). A distribuição de windowAgencies é {1:10, 2:14, 3:13, 4:6, 5:3, 6:3, 8:1}, o que explica por que quase tudo cai em "concentrada".

### 3.4 Completude dos artigos dos últimos 30 dias
Varredura completa de 4.246 artigos (desde 2026-09-05), em 10,2 s:

| Campo | Situação |
|---|---|
| `features` nulo | 0% |
| `readabilityFlesch` nulo | **100%** (negativos 0%) |
| `wordCount` nulo | **100%** |
| `trendingScore` nulo | **100%** |
| `viewCount` nulo | 99,8% |
| `entities` vazio | 1,7% (média de 11,4 entidades/artigo — NER funcionando) |
| `theme1Level1Label` nulo | **29,2%**, e **100% desde 09-26** (09-25: 49/175) |

- Flesch/wordCount por agência-dia: preenchido até 06-29 (59 de 60), **0 a partir de 06-30**.
- Nos dados de maio e junho, 908 de 3.270 agência-dias tinham Flesch negativo (mínimo −125,1). O clamp continua necessário quando o backfill voltar.

### 3.5 Sentimento
Nenhum campo vivo. `avgSentimentScore` está nulo nas 24.648 linhas desde maio. `pctPositive` é não nulo em 7.175 linhas, mas sempre 0.

### 3.6 trendingThemes
- Com threshold 0 e minArticles 1: 3d/14d → 0 linhas; 3d/21d → 0; 7d/28d → 0; 21d/84d → 22 linhas, todas com growth ≤ 1,11.
- `analyticsKpis`: 7 dias = 930 artigos e `activeThemes: 0`; 14 dias = 22 temas.
- Defeitos de desenho no resolver:
  - O baseline **inclui a janela**, porque usa `_ts_filter(baseline_days)` (`analytics.py:209`).
  - O piso de 0.001 (`:228`) gera o mesmo tipo de ratio absurdo das entidades.
  - `themeCode` é sempre `None` (`:234`).

### 3.7 Artigos MOCK (issue #3)
- A issue diz para identificar por `summary LIKE '[MOCK]%'`. Com busca por frase `"Resumo gerado para teste local"` e paginação completa (230 páginas, 17 s), achei **4.600 artigos**, todos com summary `[MOCK] Resumo gerado para teste local — <título>`.
- Datas de 2025-09-24 a 2026-02-27 (pico em 2025-11 com 1.534). São 133 agências; as maiores são ebc 755, agencia_brasil 321 e tvbrasil 162. Nenhum está nos últimos 30 dias.
- **São artigos reais** (URL gov.br, content com 3–6 mil caracteres, 6–18 entidades). Só o summary é falso. O `DELETE FROM news WHERE summary LIKE '[MOCK]%'` proposto na issue apagaria 4.600 notícias reais.
- Um exemplo aparece hoje na busca: `suica-amplia-contribuicao-ao-fundo-amazonia-com-nova-doacao-de-r-33-milhoes_dedae7`.

### 3.8 Ontologia de POLICY (insumo para "silêncio coordenado")
- `policies()` está no ar: 2.441 políticas, 1.458 com `domain` e 1.460 com `lifecyclePhase`.
- **`responsibleAgencies` está vazio em 150 de 150** (as 150 com mais artigos), e `policyDetails` de Pacto EJA devolve `null`. Não existe, portanto, o mapeamento "agência-dona" que o BLUEPRINT:59 pressupõe.
- `Agency.isRepublisher` e `Article.publicationHour` estão no ar.

## 4. Agency keys

- A API tem 156 agências válidas; a lista completa está em `gobus://agencies`.
- Das chaves suspeitas:
  - **Existem:** `trabalho-e-emprego`, `secom`, `mre`.
  - **Não existem:** `trabalho`, `cgcom`, `tcu`, `ibge`, `caixa`, `ipea`, `sus`, `senado`, `camara`.
- Onde estão fixas no código:
  - `get_readability_recommendations.py:5-9` e `readability_dashboard.py:6-10`: 20 chaves, 5 inválidas (trabalho, cgcom, tcu, ibge, caixa).
  - `readability_report.py:7-11`: 20 chaves, 6 inválidas (trabalho, ipea, sus, ibge, senado, camara).
- Das chaves válidas nessas listas, secom, agu e inss tiveram **0 artigos em setembro**.

## Implicações para o plano

- **Novo pré-requisito, antes de todas as frentes:** abrir issues de pipeline (fora do gobus-mcp) para:
  - features de legibilidade paradas desde 2026-06-30 (o data-platform já tem `9c90bb0 script de backfill… readability_flesch`);
  - classificação de tema parada desde ~09-25;
  - `trendingScore` por artigo nulo;
  - sentimento;
  - `articlesTimeline` quebrado (facet `published_date`);
  - atraso de indexação no Typesense.

  Sem tema, as frentes 3 e 4 (forecast, radar) não têm sinal.
- **Frente 1 (PR de limpeza):**
  - corrigir o `limit` em `search` (readability por agência está 100% quebrada);
  - trocar `or 0.0` por "sem dado" e marcar o pipeline como DEAD quando Flesch for todo nulo;
  - corrigir o health de `trendingScore` para olhar `features.trendingScore`;
  - fazer `score_article` recusar a nota (em vez de dar 5.6) quando não houver wordCount/Flesch;
  - ler as listas de agências de `agencies` e excluir as com volume 0;
  - tirar o "~33.5" fixo do texto;
  - reescrever a issue #3 como `UPDATE news SET summary = NULL` (ou regenerar) mais reindexação. **Não usar o DELETE.** São 4.600 linhas.
  - Também: mostrar nomes em `gobus://agencies` (vindo de `agencyAnalytics.agencyName`, ou corrigir `Agency.label`); policy_lifecycle agregando por mês, com o pico real e artigos da janela do pico.
- **Frente 2 (trendingEntities):** mudar nos dois lados.
  - **graphql-api:** `WHERE computed_at >= (SELECT max(computed_at) FROM entity_trending_scores) - interval '6 hours'` ou equivalente.
  - **data-platform:** fazer `DELETE` mais `INSERT` na mesma transação (ou TTL); suavizar o baseline zero (ex.: `(w+1)/(b+1)` ou um teto) no lugar do piso 0.001.
  - Os testes devem cobrir: linhas velhas não voltam; ratio menor que ~50× quando o baseline é 0.
- **Frente 3 (anomalias e defeso):**
  - O "silêncio coordenado" precisa de uma agência-dona derivada, porque `responsibleAgencies` está vazio: por exemplo, a agência dominante em `entityCoverage` do baseline.
  - Calendário do defeso: 04/07 a 25/10, com queda de −33,9% e 15 agências com ≥10 artigos zeradas (39 no total). Recomendo uma de duas opções: baseline de mesma fase (pré-defeso contra pós), ou suprimir alertas para agências que tinham volume 0 até ~4 semanas depois de 25/10.
  - O fim de semana pesa 4,6×. Normalizar por dia útil e implementar `horizon_days` de verdade.
  - Corrigir o baseline sobreposto em `trendingThemes`.
- **Frente 4 (MCP Apps):** a dashboard existente prova o transporte, mas hoje renderiza só zeros. Os três apps novos deveriam mostrar o estado "dado indisponível" vindo do health check; caso contrário vão expor ratios de 8571× e notas constantes.
- **Frente 5 (message_coherence):** viável. `entities` está populado em 98,3% dos artigos (média 11,4) e `isRepublisher` está no ar (3 agências). Atenção: os republicadores passaram de 26,7% para 34,5% do volume durante o defeso, o que distorce qualquer medida de coerência se não forem separados.
- **Configuração:** o `~/.claude.json` (no nível do usuário e no projeto gobus-mcp) ainda usa SSE `/sse`. Esta sessão usou o stdio local do `.mcp.json` do workspace. Ao validar a Fase 2.5, deixar claro qual servidor está sendo testado.
