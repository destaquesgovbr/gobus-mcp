# ui://anomaly-radar

**MCP App** de [`gobus_detect_anomalies`](../tools/detect-anomalies.md): radar de anomalias comunicacionais por domínio de política, ciente do defeso eleitoral. Ver [MCP Apps](index.md).

**URI:** `ui://anomaly-radar` · **MIME:** `text/html;profile=mcp-app` · `_meta.ui.prefersBorder: true`
**Dados:** nenhum no HTML. O app desenha o `structuredContent` da tool (`kind: "gobus.anomalies"`, `schemaVersion: 1`, o `AnomalyReport` de `payloads/anomalies.py`). Lido sem a tool, o resource é só o template.

## Card inline

- **8 gauges por domínio**, na ordem fixa do payload (Saúde, Educação, Social, Economia, Segurança, Meio ambiente, Governança, Outros). Cada gauge tem dois arcos de 0 a 1: o externo (laranja) é o **pico** (tema em alta e cobertura concentrada) e o interno (azul) é o **silêncio** (queda de tema e silêncio coordenado). As marcas ficam nos limiares de atenção e alerta que vêm do payload (`severityBands`), e o arco na faixa normal fica esmaecido. Embaixo, ▲ picos e ▼ silêncios.
- **Chips:** defeso eleitoral (dias restantes) ou recuperação pós-defeso (até quando), temas degradados ou indisponíveis "desde dd/mm" (detecção dinâmica, data do `dataStatus`), entidades com dados degradados, sensibilidade e domínio filtrado.
- Total de sinais (picos, silêncios e os outros: rajadas, entidades novas, explicados pelo calendário) e o banner do calendário: no defeso, silêncio de agência calada vira "explicado pelo calendário"; na recuperação, baselines pré-defeso e confiança −1 nível.
- Com os dois blocos ok e nada anômalo: "Nada fora do padrão nesta sensibilidade". Com dado faltando (status `partial`), o app **não** afirma isso: mostra "Nenhum sinal nos dados disponíveis" e o motivo de cada bloco.
- Avisos de dados recolhidos em `<details>`; tabela dos domínios em `<details>`.
- Ações: **Expandir** (fullscreen, se o host oferece) e **Investigar no chat** (`ui/message` com os principais sinais e as tools para investigar).

## Fullscreen e interações

- **Sensibilidade** (alta, média, baixa; opções do payload `sensitivityOptions`) e **domínio** (Todos + os 8, ou clique num gauge) → `tools/call` da mesma tool (`sensitivity`, `domain_filter`). Os gauges continuam resumindo **todos** os domínios mesmo com filtro.
- **Lista com toggle local** (sem nova consulta): Picos, Silêncios e Outros. Cada sinal traz classe, domínio, severidade e faixa, confiança, o detalhe (razões, volume, agências, dona), a explicação e as flags. Entidades têm a **sparkline** de 28 dias (em destaque, a janela; tracejada, a agência dona).
- Clique no nome → `ui/update-model-context` ("o usuário selecionou…"). **Investigar** → `ui/message` sugerindo `gobus_get_entity_profile` (entidade) ou `gobus_search_news` e `gobus_detect_trends` (tema).
- Se o payload foi compactado, o app avisa quantos sinais ficaram fora do painel ("a lista completa está no texto da resposta").
- Em host sem fullscreen, a lista e os controles aparecem no próprio card.

## Estados

| `status` | Quando | O app mostra |
|----------|--------|--------------|
| `ok` | temas e entidades ok | gauges, total e (no fullscreen) a lista |
| `partial` | um bloco degradado ou indisponível (ex.: temas sem classificação desde 26/09; ranking com linhas legadas) | gauges dos dados que existem, chips e o motivo de cada bloco |
| `empty` | nenhum sinal no domínio filtrado | gauges de todos os domínios e "Nenhum sinal em …" |
| `unavailable` | temas e entidades indisponíveis (ex.: graphql-api fora do ar) | "Radar indisponível" com o motivo, sem gauges zerados |

Erro da tool (`isError`), resultado sem `structuredContent` (parâmetro inválido devolve só o texto com as opções), consulta cancelada e payload de versão desconhecida têm estados próprios.

## Payload e orçamento

`compact_anomaly_payload` deixa no `structuredContent` só o que o app desenha:

- sinais de entidade anômalos: os **6** mais severos (`MAX_PAYLOAD_SIGNALS`), com as séries `daily`/`ownerDaily`;
- tendências normais: no máximo **3** (`MAX_PAYLOAD_NORMALS`), sem série;
- o resto vai para `entities.omitted` (contagem por classe). O Markdown do `content` tem todos.

Campos novos (opcionais, `schemaVersion` continua 1): `entities.omitted`, `severityBands {watch, alert}` e `sensitivityOptions`. Com 30 candidatos de nome longo, o payload fica em ~17 KB, com as séries dos 6 exibidos (o G2 media 19,7 KB, já sem séries) e o `content` leva o Markdown inteiro (~9 KB); o `summary` é o mesmo texto até 6 KB. `fit_anomaly_budget` segue como rede de segurança dos 20 KB.
