# get_message_coherence

Mede a **coerência de mensagem entre agências** sobre uma entidade (programa, política, órgão, pessoa) ou um tema: as agências falam em sintonia, citando as mesmas entidades, no mesmo momento, com o mesmo enquadramento e o mesmo tom? Devolve um índice de 1 a 5 com a tabela de dimensões, uma linha por agência, as âncoras compartilhadas, os pares mais divergentes e as republicadoras numa seção à parte.

Não tem MCP App nesta fase. O builder já produz o `CoherenceReport` (payload versionado), que um app futuro (`ui://coherence-matrix`) vai desenhar.

## Parâmetros

| Parâmetro | Tipo | Obrigatório | Default | Descrição |
|-----------|------|-------------|---------|-----------|
| `entity_id` | `str` | Um dos dois | `""` | `entityId` canônico (`Q575545`, `dgb_pe-de-meia`) ou um **nome**. Com nome, a tool usa o `entitySearch(limit:3)` e fica com a entidade de maior volume; as outras aparecem como alternativas |
| `theme` | `str` | Um dos dois | `""` | Label L1 de tema ([`gobus://themes`](../resources/themes.md)). Aceita sem acento e prefixo único (`"defesa"` → `Defesa e Forças Armadas`) |
| `agencies` | `list[str]` | Não | — | Restringe às agências listadas (códigos do catálogo). Código inválido devolve sugestões (`"ms"` → `saude`) |
| `date_from` | `str` | Não | D−14 | Primeiro dia da janela (ISO, dia em BRT) |
| `date_to` | `str` | Não | D−1 | Último dia da janela (ISO, dia em BRT). Só `date_from` → 14 dias a partir dele, limitados a ontem |

Regras: informe **exatamente um** entre `entity_id` e `theme`; a janela tem no máximo **92 dias** e não pode terminar no futuro. Entrada inválida devolve a mensagem (com as opções), sem consultar os artigos.

## Retorno

Exemplo real (Bolsa Família no defeso):

```
## Coerência de Mensagem — Bolsa Família (POLICY · `Q575545`)
**Janela:** 01/08–30/09/2026 (61 dias, BRT) · **Artigos:** 58 · **Emissores:** 2 agências (13 artigos) · **Republicadoras:** 40 artigos (69%)
_5 agência(s) não republicadora(s) com 1 artigo ficam fora do índice._

### Índice: 2/5 (0,27)
| Dimensão | Valor | Peso | Leitura |
|---|---|---|---|
| Entidades | 0,32 | 35% | 7 âncoras em comum entre 2 agências; cosseno médio 0,32 |
| Timing (BRT) | 0,00 | 25% | 1º artigo em até 48 h: 0 de 1 agência; dias em comum (Jaccard) 0,00; início truncado (a pauta já corria) |
| Enquadramento | 0,32 | 25% | 85% dos artigos classificados; dominante: serviço (55%) |
| Tom | 0,54 | 15% | cobertura de sentimento 100%; 85% positivo |

### Por agência
| Agência | Artigos | 1ª publicação (BRT) | Atraso | Enquadramento | Âncoras exclusivas |
|---|---|---|---|---|---|
| Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome (`mds`) | 10 | 10/08 07:44 | 1º | serviço | Gás do Povo; MDS; Cadastro Único |
| Ministério da Fazenda (`fazenda`) | 3 | 13/08 19:16 | +3,5 d | desafio | Secretaria de Prêmios e Apostas; … |

### Âncoras compartilhadas
- BPC (POLICY) — 2 agências
…
### Divergências
- `mds` × `fazenda`: 0,27 — mais fraca: timing (0,00)

### Republicadoras
_Fora do índice: republicam conteúdo de outras agências._
- Agência Brasil (`agencia_brasil`): 33 artigos · 1ª em 06/08 16:28 (−3,6 d do 1º emissor)

### Avisos de dados
> - A janela cruza o defeso eleitoral 2026 (04/07–25/10/2026): …
> - Início truncado: a pauta já corria antes da janela (0,7 artigos/dia nos 30 dias anteriores contra 1,0/dia na janela) …
```

A saída fica em torno de 2–4 KB (alvo ≤ 5 KB): até 12 agências, 8 âncoras compartilhadas e 5 divergências.

## Algoritmo

1. **Amostra:** `articles(limit:250, page, filter, sort:DATE)` com `entityCanonical` (entidade) ou `themeLabel` (tema), mais `agencies` e a janela em BRT (`startDate`/`endDate` com `-03:00`, fim exclusivo). A tool lê a página 1 e, com `found > 250`, as páginas 2–4 em paralelo. Acima de 1000 artigos, a amostra fica com os 1000 mais recentes e sai o aviso `SAMPLE_TRUNCATED`. O `content` não é pedido.
2. **Emissores:** agências **não republicadoras** com pelo menos 2 artigos. As republicadoras do catálogo (Agência Brasil, TV Brasil, EBC e Radioagência Nacional) ficam sempre numa seção separada, com volume, participação e atraso da 1ª republicação. Com menos de 2 emissores não há índice ("voz única: X").
3. **Dimensões** (funções puras em `analytics/coherence.py` e `analytics/framing.py`):

    | Dimensão | Peso | Cálculo |
    |---|---|---|
    | E, entidades | 0,35 | Peso por agência `Σ salience / n_a × ln(1 + N/df)`, só entidades com `canonicalId`, sem a própria entidade e sem as `dgb_{código}` das agências do catálogo. Média dos cossenos entre pares, ponderada por `min(n_a, n_b)`. Agência com menos de 3 entidades fica fora |
    | T, timing | 0,25 | `0,5 ×` fração dos emissores com o 1º artigo em até 48 h do primeiro emissor `+ 0,5 ×` Jaccard médio dos dias de publicação. Datas sempre em BRT a partir do `publishedAt` (`2026-09-26T01:30Z` conta como 25/09) |
    | F, enquadramento | 0,25 | Léxico pt-BR (anúncio, resultado, desafio, serviço, agenda) sobre título (peso 2), subtítulo, lead, resumo e tags. Resumos `[MOCK]` são ignorados. `1 − JSD` médio (base 2) entre agências. Indisponível com menos de 40% dos artigos classificados |
    | S, tom | 0,15 | Aliases de contagem `articles(limit:1, filter:{…, agencies:[a], sentiment:[l]}){found}` para os 12 maiores emissores, numa requisição. `1 − JSD` médio. Indisponível com cobertura de sentimento abaixo de 50% |

4. **Índice:** `score = Σ w·D / Σ w` das dimensões disponíveis (pesos renormalizados). Índice 1–5 pelos cortes 0,2 / 0,4 / 0,6 / 0,8, **provisórios** (ver Calibração).
5. **Contexto:** HHI do volume entre os emissores (no payload) e os 5 pares de menor similaridade combinada, com a dimensão mais fraca de cada um.
6. **Cobertura do Postgres** (só entidade, em paralelo com a página 1): `entityCoverage(DAY)` dos 30 dias antes da janela e da própria janela, numa chamada.
    - **Início truncado:** a pauta já corria antes da janela quando a taxa diária do prior é pelo menos metade da taxa da janela (com ≥ 3 artigos antes). Nesse caso, o atraso conta a partir do início da janela.
    - **Índice de busca:** compara o `found` do Typesense com o Postgres na janela (`indexing_lag`). Se o Typesense não tem a marcação `entity_canonical` (histórico ainda não reindexado), o relatório fica **indisponível**, com `INDEXING_LAG`, em vez de dizer "nenhum artigo".

Custo típico: 3–4 requisições em 1–2 s. Os nomes das agências vêm do catálogo (cache de 24 h). A frio, a tool espera por eles até 2 s desde o início; depois disso, a tabela mostra os códigos.

## Avisos

| Código | Quando |
|---|---|
| `ELECTORAL_BLACKOUT` | a janela cruza o defeso (04/07–25/10/2026): agências caladas e republicadoras com mais peso |
| `POST_BLACKOUT_RECOVERY` | a janela cruza a recuperação (26/10–29/11): agências retomando podem parecer atrasadas |
| `CLASSIFIER_CHANGED` | caminho por tema com janela que cruza a troca do classificador (25/09/2026) |
| `THEMES_UNCLASSIFIED` | caminho por tema: fração dos artigos **da janela** com tema, medida por aliases de contagem (total contra Σ labels L1). Abaixo de 80% fica degradado e abaixo de 50%, indisponível; a tool sugere `entity_id`. O aviso some sozinho quando o re-enriquecimento e o reindex cobrem a janela |
| `SENTIMENT_UNAVAILABLE` | cobertura de sentimento dos emissores abaixo de 80% (abaixo de 50%, o tom sai do índice) |
| `SAMPLE_TRUNCATED` | mais de 1000 artigos, ou páginas 2–4 com falha |
| `INDEXING_LAG` | Typesense com menos artigos que o Postgres na janela (caminho por entidade) |

Também aparecem no Markdown: as entidades sem NER (`entities_ner`), os resumos `[MOCK]` ignorados, o início truncado e as falhas do catálogo.

## Payload (`CoherenceReport`)

`build_coherence_output` devolve `(CoherenceReport, Markdown completo)`. O modelo (`kind: "gobus.coherence"`, `schemaVersion: 1`) segue o contrato comum (`summary` primeiro, `status`, `calendar`, `dataStatus`, `notices`) e traz:

- `subject`: `kind` (`entity` ou `theme`), `id`, `label`, `type`, `resolvedBy` (`id`, `search`, `taxonomy` ou `literal`), `query` e `alternatives`;
- `window` (fechada, dias em BRT), `indexStatus` (`scored`, `insufficient`, `no_articles` ou `unavailable`), `indexNote`, `index{score, level, cuts}`;
- `dimensions[4]` em ordem fixa (`entities`, `timing`, `framing`, `tone`), com `weight`, `effectiveWeight` (null quando fora), `value`, `status`, `detail` e `metric`;
- `sample` (`found`, `fetched`, `truncated`, emissores, artigos de agências com 1 artigo, republicadoras e `[MOCK]` ignorados);
- `agencies[≤12]` (1ª publicação em BRT, atraso, dias ativos, enquadramento dominante e contagens, tom, âncoras exclusivas) e `agenciesOmitted`;
- `sharedAnchors[≤8]`, `divergences[≤5]`, `republishers`, `prior` (30 dias antes, taxas e `truncatedStart`), `hhi` e `notes`.

## Calibração

Os cortes e os pesos são provisórios. A rodada de 06/10/2026 (`_experiments/coherence-calibration-2026-10/`) foi um **sanity check**, não um ajuste:

- **Entidade:** a direção é plausível. Pé-de-Meia em junho ficou com 3/5 (MEC, Inep e Secretaria-Geral com as mesmas âncoras) e Bolsa Família com 2/5 (MDS dominante e citações periféricas).
- **Tema:** não reproduz a ordem do UC-03 (Defesa > Minorias > Justiça). A label L1 é um guarda-chuva, e o E fica perto de zero entre agências diferentes. Os rótulos do UC-03 não são gabarito; nada foi ajustado por eles.

## Limitações

- Antes de ~20/05/2026, o filtro `entityCanonical` do Typesense ainda não tem a marcação (histórico não reindexado). Nessas janelas, a tool avisa `INDEXING_LAG` ou fica indisponível.
- Entidades de agência com QID (por exemplo "MDS", "INSS") não são excluídas, porque a regra exclui só `dgb_{código}`, e podem aparecer como âncoras compartilhadas.
- O tom quase não discrimina: a comunicação oficial sai 85–95% positiva.
- Acima de 1000 artigos, o timing usa só a amostra mais recente.
