# detect_anomalies

Detector de anomalias comunicacionais, ciente do **defeso eleitoral**: picos e quedas sustentados de **temas** (share-of-voice) e sinais de **entidades** (silêncio coordenado, cobertura concentrada, rajadas, entidades novas), recalculados pela cobertura diária do acervo.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `sensitivity` | `str` | Não | `"medium"` | `high` (mais sinais) \| `medium` \| `low` (só sinais fortes). Valor inválido devolve as opções |
| `domain_filter` | `str` | Não | `""` (todos) | Domínio de política: `HEALTH`, `EDUCATION`, `SOCIAL`, `ECONOMIC`, `SECURITY`, `ENVIRONMENT`, `GOVERNANCE` ou `OTHER`. Aceita em português: `saude`, `educacao`, `social`, `economia`, `seguranca`, `meio_ambiente`, `governanca`, `outros`. Valor inválido devolve as opções |

Limiares por sensibilidade:

| Sensibilidade | Razão mínima | Agências na concentrada | Razão das outras no silêncio | Volume mínimo |
|---|---|---|---|---|
| `high` | 1,3× | < 8 | 1,5× | 3 |
| `medium` | 1,5× | < 5 | 2,0× | 5 |
| `low` | 2,0× | < 3 | 3,0× | 8 |

## Retorno

Markdown com:

- **Cabeçalho das janelas.** Entidades: janela **fechada** de 7 dias até ontem 23:59 (America/Sao_Paulo; as contagens vêm em dias UTC da API) contra o baseline. Temas: janelas **móveis** de 3 e 7 dias até o instante da consulta (UTC).
- **Calendário:** fase (defeso de 04/07 a 25/10/2026, recuperação até 29/11), dias restantes, agências silenciadas ou retomadas.
- **Avisos de dados** (ver abaixo).
- Seções `### Picos Sustentados`, `### Quedas Sustentadas`, `### Silêncio Coordenado`, `### Cobertura Concentrada`, `### Explicado pelo Calendário`, `### Rajadas e Entidades Novas`, `### Tendências Normais` e `### Metodologia`.

Cada sinal traz a razão, o volume, a severidade de 0 a 1 com a faixa (normal, atenção ou alerta) e a confiança (alta, média ou baixa). Nas tendências normais, a severidade fica só no payload. O Markdown tem no máximo 6 KB; acima disso, é cortado em fim de linha com aviso.

```
## Detector de Anomalias Comunicacionais
**Entidades:** janela fechada 28/09–04/10/2026 (até 04/10 23:59, America/Sao_Paulo; contagens por dia UTC) contra o baseline 31/08–27/09/2026 · **Temas:** janelas móveis de 3 e 7 dias até 05/10 23:05 (BRT; contagens em UTC)
**Sensibilidade:** medium · **Domínio:** todos
**Calendário:** Defeso eleitoral 2026 (04/07–25/10/2026) — faltam 20 dias · 45 agências sem publicar há ≥14 dias

> **Avisos de dados**
> - Temas: indisponível — 6% dos artigos dos últimos 7 dias com tema (59 de 971) (desde 26/09/2026)
> - 31 de 50 linhas do ranking de entidades com baseline zero (piso antigo) descartadas como candidatas; …

### Cobertura Concentrada
- **Centro Integrado de Comando e Controle Nacional (CICCN)** (ORG, Outros) · 5 artigos/7d em 2 agência(s) e 3 dia(s) · razão 12,0× · severidade 1,00 (alerta) · confiança média
```

## Algoritmo

### Temas

- Fonte: `topThemes(range:{days}, limit:100)` + `analyticsKpis(range:{days}){total}` nos ranges 3, 21, 7 e 28 (Typesense). O `trendingThemes` não é usado aqui (decisão D7).
- **Share-of-voice sem sobreposição:** fatia do tema entre os artigos **classificados** da janela contra a fatia no baseline anterior a ela (21 − 3 e 28 − 7 dias), com suavização de Laplace. Cancela fim de semana, dia parcial e atraso de indexação. Atenua o defeso, mas não o cancela, porque a mistura de agências muda.
- **Gate de cobertura de classificação**, medido na janela **e** no baseline: abaixo de 50% de artigos com tema, o bloco fica `unavailable` com o aviso `THEMES_UNCLASSIFIED`; abaixo de 80%, `degraded` com confiança baixa. A detecção é dinâmica: a data "desde 26/09" é só redação.
- `sustained_spike`: razão ≥ limiar nas **duas** janelas e ≥ volume mínimo na curta. `sustained_drop`: razão ≤ 1/limiar nas duas, com volume mínimo no baseline. A severidade vem do sinal mais fraco das duas janelas.

### Entidades

- **Candidatos:** `trendingEntities(limit:50)`, só a última execução (`computedAt`) e sem as linhas do piso antigo (`volumeRatio / windowCount ≥ 100`, baseline zero). As linhas descartadas geram `BASELINE_ZERO_SUPPRESSED`. Execuções misturadas ou linhas legadas deixam o ranking `degraded` (`TRENDING_ENTITIES_STALE`). Até 30 candidatos, por `trendingScore`.
- **Recálculo por candidato:** `entity` (dona por `agencyKey`) + `entityCoverage(DAY)` + `policyDetails` (domínio), com no máximo 8 consultas em voo e cache de 30 min. O `volumeRatio` do upstream só vai para o payload (`upstreamVolumeRatio`), **nunca** para o Markdown nem para a decisão.
- **Janelas:** janela `[D−7, D−1]` e baseline de 28 dias antes dela. Na recuperação (26/10 a 29/11), o baseline são os 28 dias antes do defeso (06/06 a 03/07), como o D2 do upstream. As contagens excluem as **republicadoras** (Agência Brasil, TV Brasil e afins). Razões com Laplace: baseline zero não explode.
- **Dona:** `entity.agencyKey` ou, sem ele, a agência dominante em `[D−90, D−8]` sem republicadoras (fatia ≥ 0,3 e ≥ 3 artigos).
- **Classes**, em ordem de precedência:
  1. `burst`: ≥ 80% das menções da janela num único dia (caso Censo: 57 de 60);
  2. `new_entity`: nenhuma menção no baseline;
  3. `calendar_explained`: no defeso, dona silenciada (≥ 14 dias sem publicar) ou com produção < 0,2× do baseline. Na recuperação, ≥ 50% da janela vem de agências retomadas **e** o sinal não se sustenta sem elas; se se sustentar, segue com a flag `resumed_agencies`;
  4. `coordinated_silence`: as outras agências sobem (razão ≥ limiar do silêncio e ≥ volume mínimo), a dona some (0 menções ou ≤ 25% do próprio normal), mas segue ativa no geral (≥ 0,5× da própria produção) e tinha ≥ 3 menções no baseline;
  5. `concentrated_coverage`: razão ≥ limiar, ≥ volume mínimo, menos agências que o limite e ≥ 2 dias distintos;
  6. `normal`.
- Garantia: baseline zero **nunca** vira silêncio coordenado nem cobertura concentrada (vira entidade nova).
- **Severidade** (0–1): 1/3 no limiar e 2/3 no quadrado dele (faixas: atenção a partir de 0,33, alerta a partir de 0,66). No silêncio coordenado, conta o `silence_score`. Vale zero sem menções próprias e em `calendar_explained`. Abaixo do volume mínimo, é proporcional ao volume.
- **Confiança:** pelo volume da janela; cai um nível na recuperação e quando a atividade da dona é desconhecida.

### Domínios

`domain_filter` filtra as listas de sinais. Tema: mapa curado das labels L1. POLICY: `policyDetails.domain`. Demais entidades, ou POLICY sem domínio: mapa curado da agência dona. Sem mapa, `OTHER`. Os 8 gauges `domains` do payload (ordem fixa) resumem **todos** os domínios, mesmo com filtro, para o radar manter o contexto.

## Avisos

| Código | Quando |
|---|---|
| `ELECTORAL_BLACKOUT` | durante o defeso (04/07–25/10/2026) |
| `POST_BLACKOUT_RECOVERY` | na recuperação (26/10–29/11): baselines pré-defeso, confiança −1 |
| `CLASSIFIER_CHANGED` | enquanto o baseline de tema (21 ou 28 dias) cruzar a troca de classificador (25/09/2026) |
| `THEMES_UNCLASSIFIED` | cobertura de classificação < 80% na janela ou no baseline |
| `TRENDING_ENTITIES_STALE` | ranking upstream com linhas legadas, execuções misturadas, velho ou fora do ar |
| `BASELINE_ZERO_SUPPRESSED` | linhas do piso antigo descartadas como candidatas |

## Payload (`AnomalyReport`)

`build_anomaly_report` devolve o modelo pydantic (`kind: "gobus.anomalies"`, `schemaVersion: 1`, camelCase), que o G3 liga ao app `ui://anomaly-radar`. Hoje a tool devolve só o Markdown, que é o `summary`. Blocos: `themes` (`ThemeSignal`), `entities` (`EntitySignal` com dona, `silenceScore`, séries `daily`/`ownerDaily` de até 28 dias, `upstream`) e `domains[8]`. O payload cabe em 20 KB: se não couber, perde primeiro as séries e os sinais `normal`.

## Limitações

- As janelas de tema são móveis em UTC (o `range:{days}` do Typesense) e as de entidade são fechadas em BRT com contagens por dia UTC. Os dois blocos não se comparam dia a dia.
- O ranking upstream limita os candidatos a 50 e é recalculado 2×/dia. Uma anomalia fora do top-50 não aparece.
- O mapa agência → domínio é curado e parcial: agências sem mapa caem em `OTHER`.
- O `entity.agencyKey` do registro de entidades pode apontar uma dona improvável. Ele é usado como veio.
- Orçamento de latência: p50 ≤ 2 s com cache quente e ≤ 6 s a frio, dominado pelo snapshot de atividade das 156 agências (cache de 6 h).
