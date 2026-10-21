# monitor_agency

Briefing diário de comunicação para uma agência governamental. Atende o caso de uso [UC-01](../casos-de-uso.md) e é voltado para assessores de comunicação que precisam saber, todo dia, o que o seu órgão publicou e o que está repercutindo.

O prompt chega ao modelo como **uma única mensagem de usuário** (texto) com o roteiro já preenchido: a janela vira datas concretas e as chamadas das tools vêm escritas por extenso.

## Workflow

A janela é de dias **fechados** em horário de Brasília: `[D−days, D−1]`, em que D é hoje. Com `days=1` (o padrão), é só ontem. O prompt guia o LLM por 4 passos:

1. **Busca de publicações do período** — [`gobus_search_news`](../tools/search-news.md) com `query="*"`, `agency_key` e as duas datas da janela, por exemplo `gobus_search_news(query="*", agency_key="mec", date_from="2026-10-20", date_to="2026-10-20", limit=20)`. A busca devolve até 20 artigos por página; acima disso o LLM pagina.
2. **Análise de volume e performance** — [`gobus_get_agency_analytics`](../tools/get-agency-analytics.md) com as mesmas datas: `gobus_get_agency_analytics(agencies=["mec"], date_from="2026-10-20", date_to="2026-10-20", granularity="DAY")`. Os dias do analytics são UTC; a contagem pode diferir em poucos artigos da busca, que usa dias de Brasília. Os passos 1 e 2 são independentes e rodam em paralelo.
3. **Destaques** — análise dos resultados da busca — identifica os artigos de maior impacto (anúncios de programas, valores, prazos e serviços ao cidadão). O `trendingScore` por artigo está nulo no acervo e não é usado.
4. **Resumo narrativo** — síntese — o LLM escreve um briefing executivo de 200-300 palavras cobrindo volume, temas principais, artigos de destaque, sentimento geral e recomendações para a equipe.

O texto pede que cada artigo seja citado como link Markdown `[título](url)`, só com as URLs devolvidas pelas tools.

Quando a janela toca o defeso eleitoral (04/07–25/10/2026) ou a recuperação que o segue (até 29/11/2026), o prompt ganha uma linha de atenção: o volume é menor, há agências caladas e a comparação deve ser feita com janelas equivalentes.

## Como ativar

No Claude, envie:

> "O que o Ministério da Saúde publicou ontem?"

ou

> "Me dá um briefing de comunicação do MEC dos últimos 3 dias."

## Parâmetros

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `agency_key` | Chave (código curto) da agência | `"mec"` |
| `agency_name` | Nome completo da agência (opcional, melhora o texto) | `"Ministério da Educação"` |
| `days` | Dias fechados da janela (default `1` = ontem; limitado a 1–31). Vazio ou inválido cai no padrão | `"3"` |

Os argumentos de prompt chegam do host como texto (o Claude Desktop manda `""` nos opcionais em branco); por isso `days` é declarado como `str` e convertido pelo próprio prompt.
