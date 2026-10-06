# EXPERIMENTO_V2 — Índice de Resultados
> **Data:** 2026-06-29 | **Modelo:** Claude Sonnet 4.6

## Status dos Use Cases

| UC | Personagem | Pergunta-gatilho | Status | Método |
|----|-----------|-----------------|--------|--------|
| [UC-01](UC-01.md) | O Cartógrafo | Hubs de poder institucional | ⚠️ Parcial | GraphQL direto |
| [UC-02](UC-02.md) | O Arqueólogo | Cronologia diária de evento | ⚠️ Parcial | GraphQL direto |
| [UC-03](UC-03.md) | O Detetive | Mapa de silêncios estratégicos | ⚠️ Parcial | GraphQL direto |
| [UC-04](UC-04.md) | O Taxonomista | Almanaque semanal por categoria | ⚠️ Parcial | GraphQL via httpx |
| [UC-05](UC-05.md) | O Etnógrafo | Perfil narrativo do Ministério da Fazenda | ⚠️ Parcial | Python direto |
| [UC-06](UC-06.md) | O Compositor | Convergências temáticas inesperadas | ⚠️ Parcial | GraphQL direto |
| [UC-07](UC-07.md) | O Cronista | Narrativa de política pública (90 dias) | ⚠️ Parcial | Dados experimento anterior |
| [UC-08](UC-08.md) | O Estrategista | Benchmarking Ministério do Meio Ambiente | ❌ Falha | Sem workaround eficaz |
| [UC-09](UC-09.md) | O Profeta | Antecipação de pautas | ⚠️ Parcial | GraphQL direto |
| [UC-10](UC-10.md) | O Sintetizador | Estado da comunicação governamental | ⚠️ Parcial | GraphQL via curl |

**Resultado:** 9 ⚠️ Parcial | 1 ❌ Falha | 0 ✅ Completo

---

## Bug Crítico: MCP Tools Inoperantes no Claude Code

**Todos os tools `mcp__gobus__*` falharam com `-32602 Invalid request parameters` em 100% das chamadas.**

- **Causa raiz confirmada:** O servidor MCP gobus roda em modo `stdio` via Claude Desktop. Sessões Claude Code não compartilham esse processo. O `.mcp.json` do projeto está vazio — a configuração vive apenas no Claude Desktop config.
- **Workaround usado pelos agentes:** Chamadas HTTP diretas ao endpoint GraphQL de produção (`https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql`).
- **Ação necessária:** Adicionar configuração MCP ao `.mcp.json` do projeto para que os tools funcionem em sessões Claude Code. Ver [issue de configuração].

---

## Validação Técnica P3.11 — `generate_series` DAY ✅ Confirmada

UC-02 confirmou: a série `agencyAnalytics` com `granularity: DAY` retorna **29 registros** para junho/2026, incluindo **11 zeros explícitos** (fins de semana + Corpus Christi). Sem lacunas. O `generate_series` funciona corretamente.

---

## Artigos MOCK

Nenhum agente encontrou artigos com `[MOCK]` no título nos dados de junho de 2026. Issue #3 possivelmente mitigado ou dados MOCK concentrados em datas anteriores.

---

## Sentimento (Bug Persistente)

Todos os agentes confirmaram `avgSentimentScore: null` ou `0% positivo` em todos os contextos. Bug não corrigido. Os relatórios não interpretam esses dados.

---

## Bug Adicional Documentado

- **Agency key errada:** `"trabalho"` retorna sem dados — chave correta é `"trabalho-e-emprego"` (documentado no UC-02).
- **`wordCount: null`** em artigos recentes — possível regressão no pipeline de features (documentado no UC-02).
- **`topArticles` sempre vazio** em `trendingThemes` (documentado nos UC-09, UC-10).
- **`avgFleschScore: null`** para junho 2026 — pipeline de features possivelmente atrasado (documentado no UC-10).

---

## Top 3 Insights Surpreendentes

### 🥇 O MRE (Itamaraty) é comunicacionalmente inexistente

UC-03 identificou que o Ministério das Relações Exteriores tem **zero artigos em junho 2026** e apenas ~14 artigos em dois anos e meio de dados. Com a Copa do Mundo 2026 acontecendo nos EUA e brasileiros sendo repatriados, o MDH faz o trabalho consular na narrativa pública enquanto o Itamaraty é invisível. Maior gap comunicacional do governo federal.

### 🥈 A Receita Federal é mais comunicativa que a Fazenda

UC-05 (Etnógrafo) revelou que a Receita Federal tem **564 artigos** vs. **337 do Ministério da Fazenda**. A RF é comunicacionalmente mais independente que o ministério que a supervisiona. Padrão incomum: o MF comunica via secretário técnico (Appy), não via o ministro.

### 🥉 O MTE é um hub estrutural silencioso

UC-01 (Cartógrafo) descobriu que o Ministério do Trabalho e Emprego aparece em **6/6 redes de co-menção** mas **sem crescimento temático visível** — hub de alta conectividade sem voz editorial própria. Contrasta com o MEC (também 6/6 redes), que tem 1.447 artigos e presença ativa.

---

## Achados Secundários Notáveis

- **MEC domina o corpus:** 1.447 artigos acumulados, 1.175 menções só em junho/2026. Único ministério que toca simultaneamente esportes, saúde, direitos, igualdade racial e legislativo.
- **Pico anômalo da Agência Brasil:** spike de 279 → 1.060 artigos em abril/2026 (UC-06).
- **Esportes lidera o trending (1.81×):** Copa do Mundo 2026 nos EUA, mas o Ministério do Esporte não publica nada sobre ela — 100% focado na Copa Feminina 2027 (UC-03).
- **SPA (apostas esportivas) emergiu como 6ª entidade mais conectada** ao Ministério da Fazenda — não prevista na análise (UC-05).
- **CNPq em Minorias** via editais de bolsas com critérios de diversidade — convergência temática inesperada (UC-06).
- **Temas preditivos UC-09:** Educação (ENEM pico em ago-out), Defesa (eleições 2026 + fragata), Justiça/DH (Cidadania PopRua — tendência estrutural contínua).

---

## Notas de Execução

- **Tempo total:** ~15 minutos (10 agentes paralelos)
- **Tokens de subagentes:** ~666k estimados
- **Lotes A+B+C:** todos lançados em paralelo; UC-01 e UC-06 precisaram de retry por timeout na primeira tentativa (agentes travaram investigando MCP em vez de usar workaround)
- **Schema divergências:** 6 divergências entre schema documentado e API real (UC-06): `searchArticles` e `resolveEntity` não existem — substitutos: `searchNews` e `entitySearch`
