# Calibração da coerência de mensagem (F5) — outubro de 2026

> Rodada de 06/10/2026 contra a graphql-api pública (só queries de leitura), com o código do
> branch `feature/fase2.5-apps-coerencia`. **Sanity check, não gabarito:** os rótulos do UC-03
> foram dados por um agente lendo subtemas, não por especialistas
> (`_plan/fase2_5/desenho/F4_F5-apps-coherence.verificacao.md`, item "F5: calibração").

Para reproduzir, na raiz do clone ou do worktree:

```bash
PYTHONPATH=src .venv/bin/python3.12 _experiments/coherence-calibration-2026-10/run.py
```

O script grava `outputs/<caso>.md` (o Markdown da tool) e `results.json` (dimensões, índice,
emissores, avisos e latência).

## Resultados

Janela de junho = 01/06–30/06/2026. Valores 0–1; o índice usa os pesos 0,35/0,25/0,25/0,15
renormalizados e os cortes provisórios 0,2/0,4/0,6/0,8.

| Caso | Ref. UC-03 | Índice | Score | E | T | F | S | Emissores | Artigos | Republicadoras | Tempo |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Tema Defesa e Forças Armadas, jun | 4/5 | 2/5 | 0,36 | 0,03 | 0,31 | 0,51 | 0,93 | 8 | 47 | 23% | 2,0 s |
| Tema Minorias e Grupos Especiais, jun | 3/5 | 2/5 | 0,34 | 0,07 | 0,21 | 0,49 | 0,94 | 11 | 107 | 10% | 1,8 s |
| Tema Justiça e Direitos Humanos, jun | 2/5 | 2/5 | 0,39 | 0,06 | 0,24 | 0,70 | 0,87 | 10 | 225 | 53% | 2,1 s |
| `Q575545` Bolsa Família, 01/08–30/09 | — | 2/5 | 0,27 | 0,32 | 0,00 | 0,32 | 0,54 | 2 | 58 | 69% | 0,8 s |
| `Q575545` Bolsa Família, jun | — | 2/5 | 0,34 | 0,14 | 0,13 | 0,44 | 0,98 | 6 | 81 | 11% | 1,1 s |
| `dgb_pe-de-meia` Pé-de-Meia, jun | — | 3/5 | 0,58 | 0,54 | 0,22 | 0,76 | 0,98 | 5 | 130 | 9% | 1,4 s |
| `dgb_pe-de-meia` Pé-de-Meia, 01/04–30/04 | — | indisponível | — | — | — | — | — | — | 0 (Postgres: 132) | — | 0,3 s |
| Tema Saúde, 22/09–05/10 | — | 3/5 | 0,45 | 0,05 | 0,67 | 0,59 | 0,81 | 6 | 93 | 22% | 1,4 s |

Critério de aceite do plano (§11, F5): `Q575545` em ago–set saiu em 0,8 s com o catálogo em
cache e em cerca de 2,0 s a frio (o prazo dos nomes das agências; ver Achados), com 2,3 KB de
Markdown, índice 2/5 com a tabela de dimensões e as republicadoras (69% do volume no defeso) em
seção separada. O smoke `pytest -m live tests/test_live_coherence.py` confere ≤ 3 s e ≤ 5 KB.

## Leitura

1. **O caminho por entidade discrimina e a direção é plausível.** Pé-de-Meia em junho (3/5):
   MEC, Inep e Secretaria-Geral falam do mesmo pacote (Enem 2026, Censo Escolar, MEC/Inep como
   âncoras), com E 0,54 e F 0,76. Bolsa Família em junho (2/5): o MDS publica 52 de 67 artigos
   e os demais citam o programa de passagem (E 0,14). Em ago–set (2/5), só MDS e Fazenda
   emitem, e a Fazenda fala de apostas (E 0,32, T 0, S 0,54).
2. **O caminho por tema não reproduz a ordem do UC-03** (Defesa 4 > Minorias 3 > Justiça 2).
   Os scores ficam comprimidos entre 0,34 e 0,39 (todos 2/5), e Justiça fica no topo pelo
   enquadramento (F 0,70). Há duas causas:
   - o UC-03 julgou **subtemas** (a missão na Venezuela em Defesa; Rio Doce/quilombolas em
     Minorias) lendo até 50 artigos. A tool mede a label L1 inteira no mês, que é um guarda-chuva;
   - no tema, **E fica entre 0,03 e 0,07**: os vetores de entidades de agências diferentes quase
     não se tocam além de lugares genéricos (Brasil, Brasília). Com peso 0,35, E puxa todo tema
     para 1–2.

   Como os rótulos não são gabarito, **nada foi ajustado** por eles.
3. **O tom (S) quase não discrimina.** Fica entre 0,8 e 0,98, porque a comunicação oficial sai
   85–95% positiva. A exceção é quando uma agência traz pauta negativa (Fazenda/apostas: 0,54).
   Isso é coerente com o peso baixo (0,15).
4. **O timing (T) cai em janelas longas.** Em 30–61 dias, emissores esparsos têm poucos dias em
   comum (Jaccard 0,04–0,15). Na janela padrão de 14 dias, ele sobe (Saúde: 0,67).
5. **O aviso de tema é dinâmico.** Saúde em 22/09–05/10 tem 59% dos artigos da janela
   classificados: sai `THEMES_UNCLASSIFIED` (degradado), com a sugestão de usar `entity_id`. Junho
   (≥ 98%) não tem aviso.

## Achados

- **Lacuna do índice de busca (corrigida na tool).** O filtro `entityCanonical` do Typesense
  não tem a marcação antes de ~20/05/2026, o início da janela do `incremental-sync` do B4. Por
  mês, Typesense contra Postgres (`entityCoverage`):
  - Pé-de-Meia: abril 0 contra 132, março 0 contra 34;
  - Bolsa Família: março 28 contra 68, abril 12 contra 33.

  Antes, a tool diria "nenhum artigo". Agora ela compara o `found` com o `entityCoverage` da
  janela (mesma chamada do prior): avisa `INDEXING_LAG` e fica indisponível quando o índice
  tem 0 contra N. **Follow-up:** reindex completo do `entity_canonical` no Typesense.
- **Entidades de agência com QID não são excluídas.** Exemplos: "MDS", "INSS" e "Governo do
  Brasil" aparecem como âncoras compartilhadas, porque a regra do desenho exclui só
  `dgb_{código}` do catálogo. **Follow-up:** mapear agência do catálogo → entidade canônica.
- **Nomes do catálogo são a consulta mais lenta a frio** (`CatalogAgencyNames`, 1,3–3,2 s). A
  tool não espera por eles além de 2 s desde o início: passado esse prazo, a tabela mostra os
  códigos e a carga termina em segundo plano, enchendo o cache de 24 h.

## Decisão

Pesos (0,35/0,25/0,25/0,15) e cortes (0,2/0,4/0,6/0,8) **mantidos e ainda provisórios**.
Revisitar quando houver:

1. reindex completo e o fim do B2/B4 (temas e resumos depois de 26/09);
2. um conjunto rotulado por pessoas da comunicação (10–20 casos, na granularidade de subtema
   ou entidade);
3. uma variante de E para o caminho por tema, como a sobreposição das âncoras (Jaccard) ou
   `sqrt(cos)`, avaliada nesse conjunto antes de virar padrão.
