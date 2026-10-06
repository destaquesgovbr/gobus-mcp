# EXPERIMENTO_V3 — Índice de Use Cases
> **Data:** 2026-06-30 | **Plataforma:** Gobus MCP + GraphQL API de produção

---

## Status dos 10 UCs

| UC | Persona | Pergunta-gatilho | Status | Achado principal |
|----|---------|-----------------|--------|-----------------|
| UC-01 | O Sismógrafo | Proto-crises e anomalias comunicacionais | ⚠️ Parcial | `trendingThemes` cego em 3d; sinal real em `trendingEntities × agencyAnalytics`. PF silenciosa (11 art/jun) enquanto MJ narra 125 sobre crime. |
| UC-02 | O Genealogista | Ciclo de vida de política pública | ✅ Completo | Pé-de-Meia: 4 fases nítidas (anúncio→rotina). Pivô retórico 2025: "justiça social" → "educação financeira / Tesouro Direto". |
| UC-03 | O Diplomata | Coerência de mensagem inter-agência | ⚠️ Parcial | Defesa=4/5 (crise força coordenação); Minorias=3/5; Justiça=2/5. Divergência de Flesch no mesmo tema: MDH a -5 vs. Incra a +20 sobre quilombolas. `Article` não expõe `entities`. |
| UC-04 | O Epidemiologista | Difusão de narrativas no ecossistema gov | ✅ Completo | Difusão BIMODAL: cluster militar (D+0→2) → platô 8 dias → reinfecção Venezuela (D+25–27). `entityNetwork` é estático — inútil para reconstruir ordem de difusão. |
| UC-05 | O Cartógrafo da Equidade | Representatividade geográfica e temática | ✅ Completo | Full-text: ratio Norte/Sudeste=1.11× (parece equânime). NER canônico: São Paulo=6.2× Região Norte. Amazônia Legal (59% território)=117 artigos em Q2. SUDAM=0 H1, FUNAI=0 fev–abr. |
| UC-06 | O Oráculo | Previsão multi-sinal (horizonte 21 dias) | ✅ Completo | Score composto 3d×7d×21d funciona, com ressalva: efeito de borda de fim de semana zera todos os temas na janela 3d. Métrica certa é **momentum direction** (derivada), não produto bruto. |
| UC-07 | O Alquimista | Receita do artigo de alto impacto | ⚠️ Parcial | `trendingScore`=100% null em jun/2026 — pipeline morto. Comprimento e legibilidade são **independentes** (corr=0.05). Agência Brasil (Flesch 33.5) é o padrão-ouro interno. |
| UC-08 | O Estrategista de Legibilidade | Diagnóstico acionável de acessibilidade | ⚠️ Parcial | Nenhuma das 14 agências atinge Flesch≥50. Melhor: Secom 17.2. Pior com alto volume: CGU -1.2, Defesa -22.9. Aviso INSS para idosos: -46.6. Artigos de serviço ≈ tão ilegíveis quanto institucionais. |
| UC-09 | O Decifrador | Entidades como termómetro de política económica | ⚠️ Parcial | BC↔Fazenda são **coincidentes** (lag=0, r=0.49), não leading. `dgb_taxa-selic`=0 artigos NER. Sinal antecipador real está no *conteúdo* (relatórios Focus), não na co-menção entre órgãos. |
| UC-10 | O Arquiteto | Blueprint estratégico v3 | ✅ Completo | RFC consolidado: 8 tools novos, 4 resources, 9 MCP Apps, 4 campos de schema, 4 páginas Streamlit, roadmap 3 fases. Ver BLUEPRINT.md. |

**Legenda:** ✅ Completo | ⚠️ Parcial (premissa do UC comprometida por bug de dados ou schema) | ❌ Falha

**Nota sistémica:** tools `mcp__gobus__*` falharam em **100% das chamadas em todos os 9 UCs** (`-32602 Invalid request parameters`). Causa: sessão SSE não persiste entre invocações de subagente. Fix: `.mcp.json` → `/mcp` (endpoint stateless). Ver BLUEPRINT.md §Bugs Críticos.

---

## Top 3 Insights Cross-UC

### 1. A métrica de equidade importa mais do que o número (UC-05 × UC-01)

Por menção full-text a comunicação federal parece equânime (Norte+Nordeste=12.409 vs Sudeste+Sul=13.753, ratio 1.11×). Por entidade NER canônica — que mede de *quem* a notícia fala, não quem ela cita de passagem — a assimetria real é São Paulo=6.2× Região Norte. A Amazônia Legal, com 59% do território nacional, gerou 117 artigos em todo o Q2.

O mesmo princípio de "a métrica certa muda a conclusão" aparece no UC-01: `trendingThemes` está cego na janela de 3 dias (retorna vazio mesmo com limiares mínimos), mas `trendingEntities` está muito ativo. O sismógrafo real não é o sinal de tema — é o cruzamento entidade×agência-dona, que revela o silêncio coordenado da PF (11 artigos em junho enquanto MJ narrava 125 sobre o mesmo eixo de segurança).

**Implicação de produto:** as visualizações existentes do Panorama DGB usam full-text. Uma toggle simples de "menção vs. protagonismo (NER)" tornaria visível uma realidade que hoje está escondida.

---

### 2. Difusão governamental é dirigida por eventos exógenos, não por contágio orgânico (UC-04 × UC-02 × UC-06)

UC-04 descobriu que a difusão do tema Defesa em junho foi **bimodal**: o cluster militar (censipam, HFA, ESD, ESG) contaminava-se em 48h (D+0→D+2), depois havia um platô de 8 dias sem nenhuma agência nova — e então a missão humanitária na Venezuela (D+25–27) recrutou as agências generalistas (Casa Civil, Mcom, agencia_brasil, tvbrasil) e fechou o ecossistema. A difusão não foi por contágio espontâneo entre pares: foi dirigida por um **evento exógeno** que mudou o contexto.

UC-02 confirma a mesma lógica no ciclo de vida: o Pé-de-Meia não mudou de "justiça social" para "educação financeira" por deriva orgânica — foi a entrada deliberada do Tesouro Nacional e da CAIXA como parceiros operacionais (2025) que forçou a mudança de registro.

UC-06 encontrou o mesmo padrão no forecasting: `trendingEntities` é dramaticamente mais informativo que `trendingThemes` para *datar* picos porque captura entidades EVENT/LAW/POLICY com gatilhos concretos (Lei 15.358/2026, Censo Escolar 2025) — os rótulos genéricos de tema escondem a estrutura causal.

**Implicação de produto:** um sistema de detecção de anomalias eficaz deve integrar uma agenda de eventos (Copom, votações no Congresso, acordos internacionais, datas comemorativas) como contexto, não apenas séries de volume.

---

### 3. O governo federal escreve para si mesmo — e o problema não é o assunto, é o registro (UC-07 × UC-08 × UC-03)

UC-08 testou 14 agências e nenhuma chegou à faixa "médio" (Flesch≥50) na média. A melhor é Secom a 17.2. CGU tem -1.2, Defesa tem -22.9. Um aviso do INSS dirigido a idosos sobre acordo com a Defensoria pontuou -46.6 — o texto que mais precisa ser acessível é tão ilegível quanto o institucional.

UC-07 revelou o mecanismo: comprimento e legibilidade são **independentes** (correlação 0.05). "Encurtar não resolve" — é o *registro* burocrático que mata a legibilidade. A Agência Brasil escreve em 473 palavras com Flesch 33.5; ministérios escrevem em 600+ com Flesch < 10. A diferença não é de tema, é de disciplina editorial.

UC-03 acrescentou uma dimensão: o mesmo tema (reparação quilombola/Rio Doce) tem Flesch entre -5 (MDH) e +23 (Incra/Mulheres) em agências diferentes. Não é que "texto de direitos é difícil" — é que algumas assessorias escrever para o Diário Oficial enquanto outras escrevem para o cidadão.

**Implicação de produto:** a recomendação mais acionável de todo o experimento não é um tool novo — é a Agência Brasil já ter provado a fórmula internamente. O governo não precisa inventar boas práticas de legibilidade; precisa replicá-las. A plataforma pode explicitar esse benchmark.

---

## Verificação do plano original

| Critério de verificação do EXPERIMENTO_V3 | Status |
|------------------------------------------|--------|
| UC-06 confirma que score composto multi-janela funciona melhor que single-window | ✅ Parcialmente — funciona para separar tendências reais de ruído (ex: rebaixou Esportes, confirmou Defesa), mas o produto multiplicativo é frágil em bordas de calendário. Recomendado: trocar por momentum direction. |
| UC-01 identifica pelo menos 1 proto-crise real ou silêncio estratégico documentado | ✅ Silêncio documentado: PF muda (11 art/jun) enquanto MJ narra 125 sobre crime organizado. Sem sinal de sentimento (bug), não há proto-crise 🔴 confirmável — apenas atenção 🟡. |
| UC-10 produz pelo menos 5 propostas de tools/apps priorizadas por impacto × esforço | ✅ 8 tools + 9 MCP Apps + 4 resources + 4 campos de schema — todos priorizados em 3 fases. Ver BLUEPRINT.md. |

---

## Outputs do experimento

```
gobus-mcp/_experiments/uc-2026-06-30-v3/
  INDEX.md        ← este arquivo — status + top 3 insights
  UC-01.md        ← O Sismógrafo (⚠️ Parcial)
  UC-02.md        ← O Genealogista (✅ Completo)
  UC-03.md        ← O Diplomata (⚠️ Parcial)
  UC-04.md        ← O Epidemiologista (✅ Completo)
  UC-05.md        ← O Cartógrafo da Equidade (✅ Completo)
  UC-06.md        ← O Oráculo (✅ Completo)
  UC-07.md        ← O Alquimista (⚠️ Parcial — trendingScore morto)
  UC-08.md        ← O Estrategista de Legibilidade (⚠️ Parcial)
  UC-09.md        ← O Decifrador (⚠️ Parcial — dgb_taxa-selic sem NER)
  UC-10.md        ← O Arquiteto (✅ Completo)
  BLUEPRINT.md    ← RFC de produto extraído do UC-10 — input direto para backlog
```
