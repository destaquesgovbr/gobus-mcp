# Casos de uso

O Gobus MCP foi desenhado para cobrir um conjunto de cenários reais de quem trabalha com comunicação governamental, pesquisa e acompanhamento de pautas. Cada caso de uso combina uma ou mais [tools](tools/index.md) e, em quatro deles, há um [prompt composto](#prompts-compostos) pronto que orquestra o fluxo de ponta a ponta.

| UC | Título | Público | Tools envolvidas | Prompt de ativação |
|----|--------|---------|------------------|--------------------|
| UC-01 | Briefing Diário da Agência | Assessora de comunicação | `search_news`, `get_agency_analytics` | "O que o Ministério da Saúde publicou ontem?" |
| UC-02 | Comparativo Inter-Agências | Pesquisador/jornalista | `search_news`, `get_agency_analytics` | "Como Fazenda e Planejamento comunicaram a Reforma Tributária em 2024?" |
| UC-03 | Trajetória de Entidade | Assessora / pesquisador | `resolve_entity`, `get_entity_profile`, `get_entity_network` | "Mostre toda a cobertura do Programa Mais Médicos desde sua criação." |
| UC-04 | Radar de Tendências | Assessora estratégica | `detect_trends`, `search_news` | "Quais temas estão acelerando esta semana?" |
| UC-05 | Geração de Release | Redator de assessoria | `search_news`, `get_article` | "Crie um rascunho de release sobre emprego formal usando artigos do Ministério do Trabalho." |
| UC-06 | Rede Institucional | Jornalista investigativo | `resolve_entity`, `get_entity_network`, `search_news` | "Quais pessoas e projetos aparecem com o Ministério das Comunicações?" |
| UC-07 | Análise de Sentimento | Pesquisador acadêmico | `get_agency_analytics` | "Como evoluiu o sentimento sobre saúde pública durante a pandemia?" |
| UC-08 | Coordenação Cross-Agency | Equipe SECOM | `detect_trends`, `search_news` | "Quais temas foram cobertos por 3+ agências em paralelo sem coordenação no último mês?" |
| UC-09 | Benchmark de Legibilidade | Gestor de conteúdo | `get_agency_analytics`, `search_news` | "Quais órgãos publicam conteúdo mais acessível?" |
| UC-10 | Boletim Semanal | Cidadão comum | `detect_trends`, `search_news` | "O que o governo publicou de mais importante essa semana?" |

## Prompts compostos

Quatro dos casos de uso acima têm **prompts compostos** prontos — fluxos que encadeiam várias tools automaticamente, de modo que uma única mensagem do usuário dispara todo o roteiro de análise:

- [`monitor_agency`](prompts/monitor-agency.md) — atende o **UC-01** (Briefing Diário da Agência)
- [`trace_entity`](prompts/trace-entity.md) — atende o **UC-03** (Trajetória de Entidade)
- [`draft_press_release`](prompts/draft-press-release.md) — atende o **UC-05** (Geração de Release)
- [`weekly_digest`](prompts/weekly-digest.md) — atende o **UC-10** (Boletim Semanal)

Os demais casos de uso não têm prompt dedicado: o LLM os atende combinando tools sob demanda, a partir da pergunta do usuário e do contexto fornecido pelos [resources](resources/agencies.md).
