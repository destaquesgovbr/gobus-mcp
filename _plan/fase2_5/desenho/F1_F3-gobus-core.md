> Anexo do [PLANO_FASE2_5](../../PLANO_FASE2_5.md) — rascunho de desenho, gerado em 2026-10-05 por agente read-only (wf_4dd686b8-683). IPs e ids de conta redigidos.
> Precedência em conflito: `desenho/integration.md` > rascunhos > `investigacao/critic.md` > demais relatórios.

# Plano F1 + F3 (gobus-mcp): desenho de implementação

Baseei este plano nos 5 relatórios do scratchpad (o `r_critic.md` prevalece nos conflitos) e em verificações read-only feitas agora:

- **Introspecção ao vivo:** `windowAgencies` é `Int!` e `computedAt` é anulável.
- **Testes HTTP read-only na API pública** (latências medidas):
  - `topThemes` + `analyticsKpis` levam ~0,25 s por range.
  - `agencyAnalytics` com as 156 agências: DAY de 01/06 a 06/10 dá 19.968 linhas em ~3,0 s; WEEK dá 1,9 s.
  - Query combinada `entity` + `entityCoverage` + `policyDetails` por entidade: ~0,25 s.
  - `articles.filter.startDate/endDate` respeita offset `-03:00` (176 contra 179 em 30/09).
- **Leitura do resolver `trendingThemes`** (`graphql-api/.../resolvers/analytics.py:240-276`): faz N+1 buscas de `topArticles` mesmo quando o campo não é pedido.
- **`reusable-workflows`:** só tem `cloud-run-deploy.yml` e `composer-deploy-dags.yml`. Não existe workflow de teste Python para reaproveitar.

---

## 0. Sequência e PRs (gobus-mcp)

**PR 1 — `feature/fase2.5-higiene` (F1)**
- Base: `origin/main`.
- Merge e deploy nesta semana, porque `readability_recommendations(agency)` está quebrada em produção.
- Não depende de F0 nem de F2: tudo degrada de forma explícita.

**PR 2 — `feature/fase2.5-analytics` (F3, e F5 se o orquestrador juntar)**
- Base: main já com o PR 1.
- **Em produção até 2026-10-20.** O prazo duro é 24/10, porque a supressão da retomada precisa estar no ar em 26/10.
- F4 consome os modelos `AnomalyReport`/`ForecastReport` definidos aqui. Por isso F3 entra antes de F4.

**Infra:** nenhuma env var nova é obrigatória. Todas têm default no código, então **não há PR em `infra/`** para F1/F3.

---

## 1. Módulos novos (assinaturas)

Todas as funções são puras: recebem `today: date` ou `now: datetime` injetável. Os orquestradores async ficam em `tools/`. Os payloads usam pydantic v2 com `alias_generator=to_camel` e `populate_by_name=True` (camelCase para o JS do F4).

### F1

**`src/gobus_mcp/cache.py`**
```python
class TTLCache:  # async single-flight, clock injetável
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None
    async def get_or_load(self, key: Hashable, loader: Callable[[], Awaitable[T]], ttl: float) -> T  # Lock por chave; exceção não é cacheada
    def invalidate(self, key: Hashable | None = None) -> None
```

**`src/gobus_mcp/readability.py`**
```python
FLESCH_SCALE: Final = "textstat-en"   # fórmula inglesa (textstat sem set_lang) — trocar só junto com F0(g)
FLESCH_MIN, FLESCH_MAX = 0.0, 100.0
TARGET_SERVICE, TARGET_INSTITUTIONAL = 50.0, 30.0
@dataclass(frozen=True) class FleschBand: key: str; label: str; lower: float; color: str
FLESCH_BANDS: tuple[FleschBand, ...]  # 0-25 muito difícil · 25-50 difícil · 50-75 médio · 75-100 fácil (tabela ÚNICA)
@dataclass(frozen=True) class FleschValue: raw: float | None; value: float | None; clamped: bool
def clamp_flesch(raw: float | None) -> FleschValue
def flesch_band(v: float | None) -> FleschBand | None
def describe_flesch(v: FleschValue | float | None) -> str        # "33.5 (difícil)" | "indisponível"
@dataclass(frozen=True) class Coverage: value: float | None; covered_articles: int; total_articles: int; clamped_rows: int
    @property def ratio(self) -> float | None
def weighted_metric(rows: Iterable[Mapping], key: str, *, weight_key="articleCount", clamp=False) -> Coverage  # IGNORA null
def last_period_with_data(rows: Iterable[Mapping], key: str) -> str | None
```

**`src/gobus_mcp/agency_catalog.py`**
- Fontes: `agencies{code label isRepublisher}`, `topAgencies(range:{days},limit)` e nomes via `agencyAnalytics(MONTH, 365d, metrics:[VOLUME]){agencyKey agencyName}`.
- Cache: TTL de 24 h.
```python
@dataclass(frozen=True) class Agency: code: str; name: str; is_republisher: bool
@dataclass(frozen=True) class AgencyCheck: ok: bool; code: str; suggestions: list[str]
class AgencyCatalog:
    def __init__(self, client, *, cache: TTLCache | None = None, ttl: float = 86_400)
    async def all(self) -> list[Agency]
    async def get(self, code: str) -> Agency | None
    async def name(self, code: str) -> str                    # fallback = code (label==code em 156/156)
    async def republishers(self) -> frozenset[str]             # isRepublisher ∪ {"radioagencia_nacional"}
    async def validate(self, code: str) -> AgencyCheck         # difflib.get_close_matches(cutoff=0.6): trabalho→trabalho-e-emprego
    async def active(self, days: int = 90, limit: int = 20, *, include_republishers=True) -> list[str]
```

**`src/gobus_mcp/data_status.py`**
- Avaliadores puros, compartilhados pelo health e pelas tools.
- Os incidentes conhecidos servem só para a redação ("desde dd/mm"). A **detecção é dinâmica**.
```python
Status = Literal["ok", "degradado", "indisponivel"]
class DataStatus(BaseModel): key: str; status: Status; since: date | None = None; note: str; metric: dict[str, float | int | None] = {}
KNOWN_INCIDENTS: Mapping[str, Incident]  # temas/resumo/sentimento_classificacao: 2026-09-26; legibilidade: 2026-06-30; sentimento_analytics, trending_artigo, ranking_entidades: sem data
def theme_coverage_status(classified: int, total: int, *, days: int) -> DataStatus   # <0.5 indisponivel; <0.8 degradado
def entity_ranking_status(rows: list[dict], *, now: datetime) -> DataStatus          # last_run_share, stale(>7d), zero_baseline(vr/wc≥100)
def share_status(key: str, covered: int, total: int, *, dead=0.1, degraded=0.8) -> DataStatus
def sentiment_analytics_status(rows: list[dict]) -> DataStatus  # avgSentimentScore todo null c/ articleCount>0 → indisponivel (F0c); pctPositive é fração 0..1
def typesense_lag_status(typesense_count: int, postgres_count: int) -> DataStatus
async def theme_coverage(client, days: int, *, cache: TTLCache) -> tuple[int, int]  # Σ topThemes(days,100) / analyticsKpis(days).total; TTL 10 min
```

### F3

**`src/gobus_mcp/calendar.py`**
```python
BRT = ZoneInfo("America/Sao_Paulo")   # + dependência tzdata
@dataclass(frozen=True) class BlackoutPeriod: start: date; end: date; normalization_days: int; label: str
BLACKOUTS: tuple[BlackoutPeriod, ...] = (BlackoutPeriod(date(2026,7,4), date(2026,10,25), 28, "Defeso eleitoral 2026"),)
@dataclass(frozen=True) class DateRange: start: date; end: date        # inclusivo
def now_brt() -> datetime
def reference_date(now: datetime) -> date                              # D (dia corrente em BRT)
def closed_window(days: int, today: date) -> DateRange                  # [D-days, D-1]
def brt_bounds(r: DateRange) -> tuple[str, str]                         # ("…T00:00:00-03:00", "(end+1)T00:00:00-03:00") p/ articles
def utc_day_bounds(r: DateRange) -> tuple[str, str]                     # entityCoverage: dateTo exclusivo; agencyAnalytics DAY: inclusivo
def phase(day: date, periods=BLACKOUTS) -> Literal["normal", "defeso", "normalizacao"]
def calendar_context(today: date, periods=BLACKOUTS) -> CalendarContext
def baseline_for(window: DateRange, baseline_days: int, today: date, periods=BLACKOUTS) -> DateRange
    # normal/defeso: [start-baseline_days, start-1]; normalização: mesma fase = pré-defeso [period.start-baseline_days, period.start-1]
```

**`src/gobus_mcp/agency_activity.py`**
- Uma chamada `agencyAnalytics(agencies: as 156, DAY, metrics:[VOLUME])`, de `min(D-90, defeso.start-28)` até `D-1`.
- `timeout=30`, cache de 6 h com chave `(D)`, single-flight.
```python
@dataclass(frozen=True) class AgencyActivity:
    key: str; name: str | None; last_active: date | None; silent_since: date | None  # ≥14 dias zerados até D-1
    resumed_on: date | None; pre_daily_mean: float; series: Mapping[date, int]
@dataclass(frozen=True) class ActivitySnapshot:
    by_agency: Mapping[str, AgencyActivity]; platform_daily: Mapping[date, int]
    silenced: frozenset[str]; resumed: frozenset[str]; start: date; end: date
def summarize_activity(rows: list[dict], *, today: date, silence_min_days: int = 14, periods=BLACKOUTS) -> ActivitySnapshot
def activity_ratio(a: AgencyActivity, window: DateRange, baseline: DateRange) -> float | None  # média diária janela / baseline
class AgencyActivityService:
    def __init__(self, client, catalog: AgencyCatalog, *, cache: TTLCache | None = None, ttl: float = 21_600)
    async def snapshot(self, today: date) -> ActivitySnapshot   # falha → levanta; o chamador degrada (perfil default)
```

**`src/gobus_mcp/domains.py`**
```python
class Domain(StrEnum): ECONOMIC, SOCIAL, EDUCATION, ENVIRONMENT, GOVERNANCE, HEALTH, SECURITY   # = valores vivos de policies.domain
def parse_domain(s: str) -> Domain | None   # "" → None; aliases PT (saude, educacao, meio_ambiente…); inválido → ValueError
AGENCY_DOMAIN: Mapping[str, Domain]   # curado (saude/anvisa/ebserh→HEALTH; mec/inep/fnde/capes→EDUCATION; pf/prf/mj/defesa→SECURITY; fazenda/receitafederal/cvm→ECONOMIC; mma/ibama/icmbio/ana→ENVIRONMENT; mds/inss/mdh/mulheres→SOCIAL; gestao/cgu/casacivil/secom→GOVERNANCE …)
THEME_DOMAIN: Mapping[str, Domain]    # as 25 labels L1 vivas ("Saúde"→HEALTH, "Segurança Pública"→SECURITY, "Política Econômica"→ECONOMIC …)
def entity_domain(entity_type: str, policy_domain: str | None, owner_key: str | None) -> Domain | None  # POLICY→policyDetails.domain; senão AGENCY_DOMAIN[dona]
```

**`src/gobus_mcp/analytics/ratios.py`**
```python
def laplace_ratio(w: int, W: float, b: int, B: float, alpha: float = 1.0) -> float          # ((w+α)/W)/((b+α)/B)
@dataclass(frozen=True) class GrowthRatio: ratio: float; window_count: int; baseline_prev_count: int; is_new: bool
def true_growth_ratio(window_count: int, baseline_count_incl: float, window_days: int, baseline_days: int, *, alpha=1.0) -> GrowthRatio
    # remove a sobreposição: b_prev = max(round(b_incl) - w, 0); razão sobre (B-W) dias
def ratio_from_trending_row(row: dict, window_days: int, baseline_days: int) -> GrowthRatio   # b_incl = baselineDailyAvg·B (detect_trends/agency_summary)
@dataclass(frozen=True) class ThemeWindowStat: label: str; w: int; b_prev: int; total_w: int; total_prev: int
def theme_stats(counts_w: Mapping[str,int], counts_b: Mapping[str,int], totals_w: int, totals_b: int) -> dict[str, ThemeWindowStat]
def share_of_voice_ratio(s: ThemeWindowStat, *, k_themes: int, alpha=1.0) -> float
    # ((w+α)/(T_w+αK)) / ((b_prev+α)/(T_prev+αK)) — cancela fim de semana, dia parcial, atraso do Typesense e queda do defeso
def per_day_log_rate(ratio: float, window_days: int, baseline_days: int) -> float           # ln(r)/Δt, Δt = B/2 (3/14→7; 7/28→14; 21/84→42)
def severity(score: float, threshold: float) -> float                                       # clamp(ln(score)/ln(4·thr), 0, 1)
```

**`src/gobus_mcp/analytics/weekday.py`**
```python
DEFAULT_WEEKDAY_PROFILE = {0:1.0,1:1.0,2:1.0,3:1.0,4:1.0,5:0.26,6:0.12}  # set/2026: 189/dia útil, sáb ~50, dom ~23
def weekday_profile(platform_daily: Mapping[date,int], today: date, *, lookback_days=56, min_days=28) -> dict[int, float]
def effective_days(r: DateRange, profile: Mapping[int,float]) -> float
def weekday_normalize(count: int, r: DateRange, profile: Mapping[int,float]) -> float   # count / effective_days
def expected_platform_volume(day: date, profile, *, level_by_phase: Mapping[str, float], periods=BLACKOUTS) -> float
```

**`src/gobus_mcp/analytics/themes.py`**
```python
@dataclass(frozen=True) class Sensitivity: ratio: float; window_agencies: int; silence_ratio: float; min_count: int
SENSITIVITY = {"high": Sensitivity(1.3, 8, 1.5, 3), "medium": Sensitivity(1.5, 5, 2.0, 5), "low": Sensitivity(2.0, 3, 3.0, 8)}
def classified_coverage(total: int, classified: int) -> float | None
def classify_sustained(short: Mapping[str, ThemeWindowStat], long: Mapping[str, ThemeWindowStat], *, sens: Sensitivity,
                       k_themes: int, coverage_ok: bool) -> list[ThemeSignal]
    # pico: r_short≥thr E r_long≥thr E w_short≥min_count; queda: ambos ≤1/thr E b_prev≥min_count. Hoje o "pico" vale com growth≥0.5 e pega até tema em queda
```

**`src/gobus_mcp/analytics/entities.py`**
```python
@dataclass(frozen=True) class CoverageStats:
    by_agency_window: Mapping[str,int]; by_agency_baseline: Mapping[str,int]; by_agency_owner_period: Mapping[str,int]
    window_count: int; baseline_count: int; window_agencies: int; distinct_days: int; max_day_share: float  # sem republicadoras
    republisher_window_count: int
def coverage_stats(rows: list[dict], *, window: DateRange, baseline: DateRange, owner_period: DateRange,
                   republishers: frozenset[str]) -> CoverageStats
def owner_agency(entity_agency_key: str | None, stats: CoverageStats, *, min_share=0.3, min_articles=3) -> OwnerInfo | None
    # agencyKey se ≠ null; senão argmax em owner_period=[D-90, D-8], excluindo republicadoras
def silence_score(others_ratio: float, owner_entity_ratio: float, owner_activity_ratio: float | None) -> float
    # = others_ratio / max(owner_entity_ratio / max(owner_activity_ratio or 1, 0.05), 0.1)
    # refina o BLUEPRINT ("volumeRatioEntidade ÷ atividadeAgênciaDona"): a atividade da dona é a relativa ao próprio volume total
def classify_entity(stats, owner, *, owner_activity: AgencyActivity | None, cal: CalendarContext, sens: Sensitivity,
                    resumed: frozenset[str], window: DateRange, baseline: DateRange) -> EntitySignal
```
Ordem de precedência de `classify_entity`:
1. `rajada`: `max_day_share` ≥ 0,8. Caso Censo: 57 de 60 artigos no mesmo dia.
2. `entidade_nova`: `baseline_count` == 0.
3. `explicado_calendario`, em dois casos:
   - a dona está em `silenced` com `activity_ratio` < 0,2 durante o defeso;
   - na normalização, ≥50% da janela vem de agências em `resumed`.
4. `silencio_coordenado`, quando todas as condições valem:
   - `others_ratio` ≥ `sens.silence_ratio`;
   - a dona tem `owner_w` == 0, ou `owner_rel` ≤ 0,25;
   - `owner_activity_ratio` ≥ 0,5;
   - a dona tinha `owner_b` ≥ 3.
5. `cobertura_concentrada`: `ratio` ≥ `sens.ratio`, `window_agencies` < `sens.window_agencies` e `distinct_days` ≥ 2.
6. Caso contrário, `normal`.

**`src/gobus_mcp/analytics/forecast.py`**
```python
WEIGHTS = {"3": 0.5, "7": 0.3, "21": 0.2}; WINDOWS = {"3": 14, "7": 28, "21": 84}
def composite(rates: Mapping[str, float | None], weights=WEIGHTS) -> float | None   # média ponderada RENORMALIZADA nas janelas presentes (taxa log/dia)
def momentum(rates: Mapping[str, float | None], *, delta=math.log(1.10)/7) -> tuple[Literal["acelerando","desacelerando","estavel","indeterminado"], float | None]
    # a = k3-k7 (fallback k7-k21); as taxas são por dia e comparáveis entre si
def confidence(windows_ok: int, count7: int, min_coverage: float, phase: str) -> Literal["alta","media","baixa"]  # −1 nível na normalização
def project(share_now: float, k: float, *, start: date, horizon_days: int, profile, level_by_phase, phi=0.9,
            k_sigma: float | None = None) -> Projection
    # s(t)=s0·exp(k·φ(1−φ^t)/(1−φ)), multiplicador em [0.2, 5]; esperado(t)=s(t)·P(dia); intervalo = cenários k±σ + Poisson 1.96√E
def clamp_horizon(h: int) -> tuple[int, str | None]   # 1..28, com aviso
```

**`src/gobus_mcp/analytics/models.py`** (contrato da seção 3) e **`analytics/render.py`**:
```python
def render_anomalies_markdown(r: AnomalyReport) -> str
def render_forecast_markdown(r: ForecastReport) -> str
```

**Orquestradores** (em `tools/`, retornam o modelo; a tool em F3 continua devolvendo `str`):
```python
async def build_anomaly_report(client, *, sensitivity="medium", domain_filter="", catalog, activity, now=None, max_candidates=30) -> AnomalyReport
async def detect_anomalies(client, sensitivity="medium", domain_filter="", *, catalog, activity, now=None) -> str
async def build_forecast_report(client, *, horizon_days=21, limit=5, activity, now=None) -> ForecastReport
async def forecast_trends(client, horizon_days=21, limit=5, *, activity, now=None) -> str
```

**Queries novas** (constantes estáticas, todas com nome de operação):
- `_THEME_RANGE_QUERY($days)`: `topThemes(range:{days:$days}, limit:100){label count}` mais `analyticsKpis(range:{days:$days}){total}`. Uma chamada por range, em gather.
  - Substitui o `trendingThemes`, que tem N+1 de `topArticles`, nas duas tools.
  - É a mesma recuperação de "razão sem sobreposição" decidida para o forecast, só que sem o arredondamento de 3 casas.
  - `true_growth_ratio` continua sendo a função genérica, via adapter, para `detect_trends`/`agency_summary`, que precisam de `agencyKey`.
- `_TRENDING_ENTITIES_QUERY`: `trendingEntities(limit:50)` com `computedAt`.
- `_ENTITY_CONTEXT_QUERY($id,$from,$to)`: `entity{entityId agencyKey type}`, `entityCoverage(DAY)` e `policyDetails{domain}`.
  - Uma chamada por candidato, com `Semaphore(8)` e `gather(return_exceptions=True)`.
  - Cache de 30 min com chave `(id, D)`.
- `_THEME_AGENCY_SHARE_QUERY`: `part: articles(limit:1, filter:{themeLabel, agencies, startDate, endDate}){found}` mais `all: …`.
  - Só na normalização e só para picos (até 8).

**Orçamento de latência de `detect_anomalies`:** ~1–1,5 s com cache quente; ~4–5 s a frio, por causa do snapshot de atividade (~3 s).

---

## 2. Mudanças por arquivo existente

### F1

**`src/gobus_mcp/client.py:14-30`**
- `__init__(url, api_key="", timeout=10.0, *, max_concurrency=8, retries=1, transport: httpx.AsyncBaseTransport | None = None)`.
- `httpx.AsyncClient` compartilhado, criado lazy **por event loop** (guarda o id do loop e recria se mudar, para os testes e o `fastmcp.Client` em memória), com `Limits`.
- `Semaphore(max_concurrency)`.
- `execute(query, variables=None, *, timeout=None)`.
- Uma retentativa com jitter de 0,3–0,6 s em `httpx.TransportError` e 502/503/504. Nunca em 4xx nem em `errors[]`.
- Nova exceção `GobusUpstreamError` com mensagem pt-BR.
- `aclose()`.

**`src/gobus_mcp/config.py:4-8`:** `max_concurrency: int = 8`, opcional.

**`src/gobus_mcp/tools/get_readability_recommendations.py`**
- `:5-9`: remover `_ACTIVE_AGENCIES`; usar `catalog.active(days, limit=40)`.
- `:34-51`: trocar `_SEARCH_QUERY` (`search(limit:)` inválido; `query:""` é rejeitada) por `_ARTICLES_QUERY` = `articles(limit:250, filter:{agencies:[$a], startDate, endDate}, sort:DATE){found articles{uniqueId title url publishedAt features{readabilityFlesch wordCount}}}`.
  - O pior artigo é escolhido no cliente pelo Flesch clampado mínimo.
  - Se a janela não tiver Flesch, uma segunda chamada vai ao `last_period_with_data` de `agencyAnalytics(MONTH, 365d)`, com a nota "dados de MM/AAAA".
- `:54-65`: substituir pelo `readability.flesch_band`.
- `:113`: receber `now`/`today`.
- `:141`: `or 0.0` vira `weighted_metric(..., clamp=True)`. Agências sem dado vão para a seção "Sem dado de legibilidade".
- `:170`: tirar o "~33.5". O benchmark passa a ser `agencia_brasil` na mesma janela, ou omitido.
- `:183-188`: chamar em gather com o analytics.
- `agency_key` passa por `catalog.validate`, com sugestão.

**`src/gobus_mcp/tools/score_article.py`**
- `:48-51`: concisão vira `None` sem wc ou sem benchmark (hoje vale 5).
- `:64-74`: densidade só com `wordCount`; sem ele, `None`.
- `:77-84`: benchmark via `weighted_metric` (ignora null).
- `:122`: `today` injetável.
- `:138-139`: média ponderada **renormalizada** das dimensões disponíveis. Sem Flesch e sem wc: "Nota indisponível — artigo sem métricas de legibilidade/tamanho (features paradas desde 30/06/2026)". Acaba a nota constante 5,6.
- `:147`: o nome vem de `agencyName`, ou do catálogo (hoje sai "[pf] pf").

**`src/gobus_mcp/tools/get_article.py:75-77`**
- `if flesch:` vira `is not None`, com `describe_flesch` (clamp e "valor bruto").
- Um `summary` que comece com `[MOCK]` vira "resumo indisponível". O helper `sanitize_summary` também é usado em `search_news.py:66`.

**`src/gobus_mcp/tools/get_agency_analytics.py`**
- `:40`: `["mec","ms"]` vira `["mec","saude"]`.
- `:73-84`:
  - com `avgSentimentScore is None`, mostrar "sentimento indisponível" (o `pctPositive` 0,0 é artefato do F0c);
  - Flesch pela faixa única;
  - null mostrado como "indisponível".

**`src/gobus_mcp/tools/get_agency_summary.py`**
- `:36-37`: `today` injetável.
- `:39-51`: gather.
- `:69-75`: `weighted_metric`/`describe_flesch`.
- Temas vazios com `theme_coverage(7)` < 0,5 geram o aviso "temas sem classificação desde 26/09".
- Validar `agency_key`.

**`src/gobus_mcp/tools/detect_trends.py:71`**
- A mensagem "Nenhum tema em crescimento" vira o aviso de indisponibilidade quando a cobertura estiver abaixo do limiar.
- Em F3, `:80` passa a exibir `ratio_from_trending_row` (razão sem sobreposição).

**`src/gobus_mcp/resources/readability_report.py`**
- `:7-11`: lista fixa vira `catalog.active(90, 20)`.
- `:41`: `today` injetável.
- `:63-77`: null fica null, sem virar 0. `gapToTarget` é null quando não há dado. Novos campos `coverage`, `scale: "textstat-en"`, `schemaVersion: 2` e `dataStatus`.

**`src/gobus_mcp/resources/readability_dashboard.py`**
- `:6-10` e `:110-146`: usar o mesmo agregador de readability e o catálogo.
- `:221-223`: escapar `</` no JSON.
- `:246`: aplicar `html.escape`.
- `:58-64`: barra com o valor clampado.
- O HTML, o `Chart` falso e o template ficam para F4.

**`src/gobus_mcp/resources/health_pipelines.py`** (reescrita)
- `fetch_health_pipelines(client, *, catalog, activity, now=None) -> str`.
- Um `_HEALTH_SAMPLE_QUERY` com aliases: `recent: articles(limit:100, últimos 7d, sort:DATE){found articles{summary theme1Level1Label features{readabilityFlesch wordCount trendingScore entities{canonicalId}}}}`, `withSentiment: articles(limit:1, filter:{sentiment:[positive,negative,neutral]})`, `kpis7`, `themes7`, `trending: trendingEntities(limit:50){computedAt volumeRatio windowCount}` e `yesterday: articles(limit:1, D-1 UTC){found}`.
- Mais `agencyAnalytics` das 3 agências mais ativas (via catálogo) e o snapshot de atividade (lag e agências silenciadas).
- Chaves de saída: `temas`, `resumo`, `sentimento_classificacao`, `sentimento_analytics`, `entidades_ner`, `legibilidade`, `word_count`, `trending_artigo`, `ranking_entidades`, `typesense_lag`, `atividade_agencias`. Cada uma com `{status, since, note, metric}`, mais `schemaVersion: 2` e `calendar`.
- O bug de escala (`:45`, limiar 5,0 em `pctPositive`, que é fração) e o falso OK de Flesch (`:50-57`, `:94`) desaparecem.

**`src/gobus_mcp/resources/agencies.py:3-23`**
- Usar o catálogo: nome humano, código e uma seção "Republicadoras".
- Query nomeada: `query Agencies`.

**`src/gobus_mcp/server.py`**
- `:1-31`: novos imports.
- `:61-65`: `_client` com `max_concurrency`; criar `_catalog = AgencyCatalog(_client)` e `_activity = AgencyActivityService(_client, _catalog)`.
- `:70,96,111,128,157,182,206,234,254,274,299,316,334`: `@mcp.tool()` vira `@mcp.tool(output_schema=None)`.
  - Efeito no Claude Code: o modelo recebe o Markdown cru no `content`, e não `{"result":"…"}` escapado. São menos tokens e o formato chega preservado.
  - Em F4, as 4 tools-app trocam para `app=AppConfig(...)` com `-> ToolResult` (o que também desliga o schema automático).
- `:254-271`: corrigir a docstring (benchmark calculado, estado "indisponível").
- `:251,271,346`: passar `_catalog`.
- `:381,387`: `@mcp.resource(..., mime_type="application/json")`.
- `:351-354,387-390`: passar catálogo e atividade.

**`src/gobus_mcp/prompts/*.py`**
- Trocar as referências sem prefixo por `gobus_*`:
  - `monitor_agency.py:17,20,23`
  - `trace_entity.py:20,23,25-26,30,33`
  - `weekly_digest.py:10,13,16,18-19`
  - `draft_press_release.py:17,20`
- `weekly_digest.py:13`: o passo "ordenado por view_count" sai, porque `viewCount` está 99,8% nulo.
- Os nomes registrados dos prompts (`prompt_*`) **ficam como estão**. Renomear quebraria os slash-commands `/mcp__gobus__prompt_*`. Se o usuário quiser `gobus_*` também nos nomes, usar `@mcp.prompt(name="gobus_…")` em commit próprio.

**`.claude/skills/gobus.md:13-40`:** nomes de tool com prefixo `gobus_` (arquivo versionado).

**`tests/conftest.py:6-16`**
- Manter o `FakeGraphQLClient`.
- Adicionar `route(operation_name, response | callable(variables))`, que extrai o nome da operação por regex. Necessário para gather e semáforo, porque a ordem de `side_effect` fica frágil.
- Fixtures `fake_catalog` (156 agências do fixture), `fake_activity(snapshot)` e `fixed_now` (padrão `2026-10-05T12:00-03:00`).

### F3

**`src/gobus_mcp/tools/detect_anomalies.py`** (reescrita, `:1-126`)
- Remove `_THEMES_QUERY` e o `_SENSITIVITY` inline.
- Fluxo:
  1. Em paralelo: 4 ranges de temas (3, 21, 7, 28), `trendingEntities(50)`, `activity.snapshot(D)` e `catalog.republishers()`.
  2. Candidatos: até 30, ordenados por `computedAt` desc e `trendingScore` desc. **Inclui linhas antigas**, porque o sinal é recalculado.
  3. Contexto por entidade, com janela fechada `[D-7, D-1]` e baseline de 28 dias via `baseline_for`. `entityCoverage` vai de `min(D-90, baseline.start)` até `D`.
  4. Só na normalização: atribuição de picos de tema a agências retomadas.
  5. Funções puras, depois `AnomalyReport` e `render`.
- Cada bloco tem try/except próprio: `status: "indisponivel"` com o motivo, sem derrubar a tool.

**`src/gobus_mcp/tools/forecast_trends.py`** (reescrita, `:1-113`)
- 6 ranges (3, 14, 7, 28, 21, 84) mais o snapshot (perfil e nível por fase).
- Janela com cobertura abaixo de 0,5 é excluída; entre 0,5 e 0,8 fica degradada (confiança no máximo "baixa").
- `horizon_days` entra de fato na projeção (`clamp_horizon`).

**`src/gobus_mcp/server.py`**
- `:299-313`: `gobus_detect_anomalies(sensitivity: str = "medium", domain_filter: str = "")`. A docstring lista os 7 domínios, os aliases PT, as categorias de sinal e o defeso.
- `:316-331`: docstring de `horizon_days` (efetivo, 1–28, default 21), a explicação de SoV e a correção de dia útil.
- Sensibilidade inválida devolve Markdown de erro com as opções.

**`src/gobus_mcp/tools/get_agency_summary.py`/`detect_trends.py`:** passam a usar `ratio_from_trending_row`.

**Fora de escopo (backlog, não expandir):**
- agregação mensal do `get_policy_lifecycle` (problema do live-probe);
- `articlesTimeline`.

---

## 3. Contrato de saída (Markdown e modelo reutilizado por F4)

**Convenções do payload:**
- `schemaVersion: 1`, chaves camelCase, enums ASCII.
- `summary` = Markdown completo, idêntico ao `content` (exigência para o Claude Code ver o resultado em F4).
- Até 20 KB: `max_candidates=30`, `limit` ≤ 15, `daily` ≤ 28 pontos.

### `AnomalyReport` (`analytics/models.py`)
```python
class CalendarContext(_M): phase: Literal["normal","defeso","normalizacao"]; label: str | None; start: date | None; end: date | None
    normalizationEnd: date | None; daysToEnd: int | None; silencedAgencies: int | None; resumedAgencies: int | None; note: str | None
class Window(_M): kind: Literal["fechada","movel"]; start: datetime; end: datetime; days: int          # end exclusivo; fechada termina em D 00:00 BRT
class ThemeSignal(_M): label: str; domain: Domain | None; kind: Literal["pico_sustentado","queda_sustentada"]
    ratioShort: float; ratioLong: float; ratioShortRaw: float | None; ratioLongRaw: float | None   # SoV vs só-sem-sobreposição (toggle F4 sem nova chamada)
    countShort: int; countLong: int; shareLong: float; severity: float; confidence: Literal["alta","media","baixa"]; flags: list[str]
class OwnerInfo(_M): agencyKey: str; agencyName: str | None; method: Literal["agencyKey","cobertura"]; share: float | None
class EntitySignal(_M): entityId: str; name: str; type: str; domain: Domain | None
    kind: Literal["silencio_coordenado","cobertura_concentrada","rajada","entidade_nova","explicado_calendario","normal"]
    windowCount: int; baselineCount: int; windowAgencies: int; distinctDays: int; maxDayShare: float
    ratio: float; upstreamVolumeRatio: float | None; upstreamComputedAt: datetime | None
    owner: OwnerInfo | None; ownerWindowCount: int | None; ownerActivityRatio: float | None; silenceScore: float | None
    severity: float; explanation: str | None; flags: list[str]   # "republicadoras_excluidas","retomada","linha_upstream_antiga"
class ThemesBlock(_M): status: Status; note: str | None; windows: dict[Literal["short","long"], Window]
    classifiedCoverage: dict[Literal["short","long"], float | None]; signals: list[ThemeSignal]
class EntitiesBlock(_M): status: Status; note: str | None; window: Window; baseline: Window; candidates: int
    upstream: dict  # {lastRunAt, rowsTotal, rowsLastRun, rowsStale}
    signals: list[EntitySignal]
class DomainSummary(_M): domain: Domain; label: str; peaks: int; silences: int; concentrated: int; maxSeverity: float   # gauges do anomaly-radar
class AnomalyReport(_M):
    schemaVersion: Literal[1] = 1; tool: Literal["gobus_detect_anomalies"] = "gobus_detect_anomalies"
    generatedAt: datetime; referenceDate: date; params: dict  # {sensitivity, domainFilter}
    thresholds: dict  # {ratio, windowAgencies, silenceRatio, minCount}
    calendar: CalendarContext; dataStatus: list[DataStatus]; themes: ThemesBlock; entities: EntitiesBlock
    domains: list[DomainSummary]; summary: str
```

**Markdown de `detect_anomalies`.** Mantém os headers que os testes fatiam (`### Picos Sustentados`, `### Cobertura Concentrada`, `### Tendências Normais`):
```
## Detector de Anomalias Comunicacionais
**Referência:** 28/09–04/10/2026 (janelas fechadas em 04/10 23:59, America/Sao_Paulo) · **Sensibilidade:** medium · **Domínio:** todos
**Calendário:** defeso eleitoral (04/07–25/10/2026) — faltam 20 dias · 39 agências sem publicar há ≥14 dias
> **Avisos de dados**
> - Temas: **indisponível** — sem classificação desde 26/09/2026 (0% dos artigos dos últimos 7 dias classificados).
> - Entidades: **degradado** — ranking upstream com linhas antigas (correção F2 pendente); sinais recalculados via entityCoverage.
### Picos Sustentados
### Silêncio Coordenado
### Cobertura Concentrada
### Explicado pelo Calendário
### Rajadas e Entidades Novas
### Tendências Normais
### Metodologia
```
- Linha de entidade: `**Nome** (TIPO, domínio) · 12 artigos/7d em 3 agências e 4 dias · razão 3,4× · dona: saude (0 menções; produção total 0,9× do baseline) · score 6,2`.
- **Nenhum `volumeRatio` do upstream aparece no corpo.** O valor só entra como `upstreamVolumeRatio` no payload.

### `ForecastReport`
```python
class WindowRatio(_M): ratio: float; ratioRaw: float; windowCount: int; baselinePrevCount: int; share: float; perDayRate: float
    status: Status; classifiedCoverage: float | None
class Projection(_M): horizonDays: int; expectedArticles: float; low: float; high: float; shareNow: float; shareAtHorizon: float
    daily: list[dict]  # [{date, expected}]
class ForecastTheme(_M): label: str; domain: Domain | None; windows: dict[Literal["3","7","21"], WindowRatio | None]
    perDayRate: float; weeklyMultiplier: float; momentum: Literal["acelerando","desacelerando","estavel","indeterminado"]
    acceleration: float | None; confidence: Literal["alta","media","baixa"]; projection: Projection; flags: list[str]
class ForecastReport(_M):
    schemaVersion: Literal[1] = 1; tool: Literal["gobus_forecast_trends"] = "gobus_forecast_trends"
    generatedAt: datetime; referenceDate: date; params: dict  # {horizonDaysRequested, horizonDays, limit}
    calendar: CalendarContext; dataStatus: list[DataStatus]
    windows: dict[str, dict]   # {"3": {kind:"movel", days:3, baselineDays:14, classifiedCoverage, status}, ...}
    platform: dict             # {weekdayProfile: {"0":1.0,…,"6":0.12}, levelByPhase: {"defeso":136.0,"normal":205.0}, profileSource: "snapshot"|"default"}
    themes: list[ForecastTheme]; summary: str
```

**Markdown de `forecast_trends`:**
```
## Forecast de Tendências — Horizonte 21 dias (05/10 → 25/10/2026)
**Calendário:** o horizonte cruza o fim do defeso (25/10) — volume esperado sobe de ~136 para ~205 artigos/dia a partir de 26/10.
> Avisos (janelas excluídas ou degradadas por cobertura de classificação)
| Tema | Ritmo (×/semana) | Momentum | Confiança | Artigos esperados (21d) | Janelas |
### Metodologia   (razão sem sobreposição + share-of-voice; janelas móveis do Typesense; projeção amortecida φ=0,9)
```

### Degradação enquanto F0/F2 não estão em produção (automática, sem flag manual)

**Temas**
- A cobertura de classificação é medida por janela (`Σ topThemes / analyticsKpis.total`):
  - menos de 0,5 → **indisponível**, com aviso "desde 26/09";
  - entre 0,5 e 0,8 → **degradado** (confiança "baixa").
- Hoje: 3d/7d em 0% e 21d em ~60%. O forecast mostra só os resultados da janela de 21d, como degradados.
- Depois do F0(a), o SoV usa denominador **classificado**. O buraco de 26/09 até o fix não distorce a razão; ele só reduz a cobertura até sair das janelas.
- Recomendar ao F0(a) o reprocessamento retroativo dessa lacuna.

**Entidades**
- Não dependem da correção do F2: os sinais são recalculados por `entityCoverage` com Laplace.
- Antes do F2: status "degradado" com `upstream.rowsStale`.
- Depois do F2: o status vira OK sozinho, pelos critérios de `entity_ranking_status`.
- Não pedir `baselineCount` do F2 antes que o snapshot do SDL o contenha (o teste de contrato barra).

**Flesch, wordCount e sentimento:** estado "indisponível" com a data do incidente. **Nunca 0.**

**Snapshot de atividade falhou:** usar `DEFAULT_WEEKDAY_PROFILE` e `profileSource:"default"`, com aviso. A tool não falha.

### Após 25/10 (fase `normalizacao`, de 26/10 a 22/11)

- **Entidades:** baseline da mesma fase (pré-defeso: 06/06 a 03/07) via `baseline_for`.
- **Janela dominada por agências retomadas:** classe `explicado_calendario`, com a flag `retomada`, desde que o sinal não se sustente sem elas. Se se sustentar, o sinal fica e recebe a flag.
- **Picos de tema:** atribuição via `_THEME_AGENCY_SHARE_QUERY`. Com ≥50% vindo de agências retomadas, o pico é rebaixado.
- **Confiança:** cai um nível em tudo.
- **Forecast:** usa `levelByPhase["normal"]` a partir de 26/10.
- **Risco residual:** se o F2 atrasar, os 50 candidatos do upstream podem ser tomados por entidades com bc=0 vindas das agências retomadas. A tool continua correta, mas pode perder anomalias reais. Isso reforça o prazo do F2.

---

## 4. Plano de testes (TDD: commit `test: … (red)` e depois `feature:/fix: … (green)`)

**Infra de teste**
- `today`/`now` injetáveis: **sem freezegun/time-machine**.
- HTTP via `httpx.MockTransport`: **sem respx**.
- Dev-deps novas: só `graphql-core` (contrato) e `ruff` (passa a ser instalado de fato). O `playwright` fica para F4, com marker `ui`.
- `pyproject`:
  - `markers = ["live: consulta a graphql-api de produção (fora do CI)", "ui: render headless (F4)"]`
  - `addopts = "-m 'not live and not ui'"`
  - `asyncio_default_fixture_loop_scope = "function"`

**Fixtures (`tests/fixtures/graphql/`)**
- `agencies_2026-10-05.json`: 156 agências reais.
- `theme_ranges_2026-10-05.json`: `topThemes`/`kpis` reais de 3/7/14/21/28/84; registram o estado degradado atual.
- `trending_entities_2026-10-05.json`: as 50 linhas reais.
- `tests/factories.py`: `make_activity_rows(spec, start, end)`, `make_coverage_rows(...)`, `make_theme_counts(...)` e `make_snapshot(...)`.

**Teste de contrato (`tests/contract/`)**
- **Origem do SDL:** snapshot de **introspecção ao vivo** commitado em `tests/contract/schema.graphql`, gerado por `scripts/refresh_graphql_schema.py` (httpx + `graphql.get_introspection_query` / `build_client_schema` / `print_schema`).
  - Não usar `graphql-api/docs/reference/schema.graphql`: está desatualizado (096f57a, sem `policies`).
- `test_graphql_contract.py`:
  - coleta, via `pkgutil.walk_packages`, toda constante `*_QUERY` de `gobus_mcp`;
  - faz `graphql.parse` + `graphql.validate` contra o snapshot;
  - exige operação nomeada.
  - **Red inicial:** o `_SEARCH_QUERY` do readability falha.
- Override `GOBUS_SCHEMA_SDL=../graphql-api/docs/reference/schema.graphql`, regerado com `scripts/export_schema.py` no branch do F2. Serve para pré-validar o gobus contra o schema do PR upstream antes do deploy dele.
- `@pytest.mark.live test_snapshot_igual_ao_live`: diff de introspecção, fora do CI.

**Casos F1**

| Arquivo | Casos |
|---|---|
| `tests/test_cache.py` | single-flight (2 `get_or_load` concorrentes → loader 1×); TTL com clock falso; exceção não cacheada |
| `tests/test_client.py` | sucesso; `errors[]` → `GobusGraphQLError`; 503 → retry → ok; 400 sem retry; timeout → `GobusUpstreamError`; reuso do AsyncClient; override de timeout por chamada |
| `tests/test_readability.py` | parametrizado: clamp (−125.1→0, −0.1→0, 33.5, 100.2→100, None); bordas de faixa 0/24.99/25/50/75; `weighted_metric` ignora null e reporta cobertura; `describe_flesch(None)=="indisponível"` |
| `tests/test_agency_catalog.py` | 1 fetch dentro do TTL; refresh após TTL; `validate("trabalho")` sugere `trabalho-e-emprego`; republicadoras; `active()` usa `topAgencies` |
| `test_tools/test_get_readability_recommendations.py` (ajustar) | modo agência usa `articles(` e não `search(`; pior artigo escolhido no cliente; fallback ao último mês com dado; ranking com seção "sem dado"; benchmark dinâmico. **Reescrever** `:54-59`: −22.9 vira 0.0 "muito difícil (valor bruto −22.9)" |
| `test_tools/test_score_article.py` | sem Flesch e sem wc → "Nota indisponível" e nenhum "5.6"; densidade só com wc; renormalização com 1 dimensão; cabeçalho com nome |
| `test_tools/test_get_article.py`, `test_analytics_tools.py` | Flesch 0 exibido; negativo clampado; sentimento "indisponível" com `avgSentimentScore` null; `[MOCK]` oculto |
| `test_tools/test_get_agency_summary.py`, `test_detect_trends` (novo) | aviso de temas indisponíveis com cobertura 0 |
| `test_resources/test_readability_report.py` | null fica null; gap null; cobertura; agências dinâmicas |
| `test_resources/test_health_pipelines.py` (reescrever; o `pctPositive: 10.0` da linha 39 está na escala errada) | temas indisponíveis; legibilidade **morta com tudo null**; `sentimento_analytics` morto (fração 0..1); ranking degradado com linhas antigas ou bc=0; lag degradado; chaves e `schemaVersion: 2` |
| `tests/test_server.py` (novo, `fastmcp.Client(mcp)` em memória, `_client`/`_catalog` via monkeypatch) | 13 tools com `outputSchema is None` e nome `gobus_*`; `call_tool` devolve `structured_content is None` e texto Markdown; MIME `application/json` nos 2 resources e `text/html;profile=mcp-app` no `ui://`; prompts sem nome de tool sem prefixo; todo `gobus_\w+` citado existe |

**Casos F3**

| Arquivo | Casos |
|---|---|
| `tests/test_calendar.py` | `phase`: 03/07 normal, 04/07 defeso, 25/10 defeso, 26/10 normalização, 22/11 normalização, 23/11 normal; `closed_window(7, 05/10)` = 28/09..04/10; `brt_bounds` com `-03:00`; `baseline_for` na normalização = 06/06..03/07; períodos injetados |
| `tests/test_agency_activity.py` | `last_active`; `silent_since` (≥14 zeros); `resumed_on`; `platform_daily`; agência sem linhas |
| `tests/analytics/test_ratios.py` | `true_growth_ratio`: caso do resolver w=b=21 (growth 4,0) vira `is_new`; arredondamento 0,107·28 → 3; guarda b_incl<w; `share_of_voice_ratio` ≈1 em crescimento proporcional; **cenário segunda-feira**: share constante dá SoV ≈1 com razão bruta ≈0,4; `per_day_log_rate` com Δt 7/14/42 |
| `tests/analytics/test_weekday.py` | perfil sintético (190/50/23) → {1,…,0.26,0.12}; fallback com menos de 28 dias; `effective_days` sáb–seg ≈1,38; `expected_platform_volume` troca de nível em 26/10 |
| `tests/analytics/test_themes.py` | pico só com as 2 janelas; só a curta não conta; queda; `min_count`; tabela de sensibilidade; cobertura <0,5 → sem sinais e indisponível |
| `tests/analytics/test_entities.py` | dona por `agencyKey`; dona por cobertura **excluindo** `agencia_brasil`; sem dona; `silencio_coordenado`; dona calada no defeso → `explicado_calendario`; rajada (57/60); entidade nova; concentrada (≥2 dias); retomada dominando na normalização; `entity_domain` e filtro |
| `tests/analytics/test_forecast.py` | `composite` renormalizado (só 7 e 21: 0,6/0,4); `momentum` nos 4 estados; `project`: H=7 diferente de H=21, fim de semana menor, cruzar 25/10 usa o nível pré-defeso, limites do amortecimento; `clamp_horizon`; `confidence` com rebaixamento |
| `test_tools/test_detect_anomalies.py` (reescrever, fake com `route`) | estado de 05/10 com fixtures reais: temas indisponíveis com aviso "26/09" e **nenhum "8571" no Markdown**; pico integrado; silêncio integrado; `domain_filter` (válido e inválido); `AnomalyReport.model_validate`; `summary == markdown`; JSON < 20 KB; cenário `now=2026-10-30` (retomada suprimida) |
| `test_tools/test_forecast_trends.py` (reescrever) | `horizon_days` muda a saída; janela excluída por cobertura; colunas da tabela; validação do payload |
| `@pytest.mark.live tests/live/test_smoke.py` | `build_*` contra produção, só verificação de forma (rodar local antes do merge) |

---

## 5. Deps e infra do repo (PR 1)

**`pyproject.toml`**
- main:
  - `fastmcp = ">=3.4.2,<3.5"`;
  - `httpx = ">=0.28.1,<1"`;
  - `tzdata = ">=2025.2"`, por garantia de `zoneinfo` na imagem slim.
- `[tool.poetry.group.dev]`:
  - `pytest = "^9.1"` e `pytest-asyncio = "^1.4"`, **atualizados antes do lock** para não rebaixar a venv;
  - `ruff` na versão corrente;
  - `graphql-core = "^3.2"`.
- `[tool.poetry.group.docs] optional = true` com `mkdocs-material`.
- `[tool.ruff.lint] extend-select = ["I"]`.
- Ordem: editar → `poetry lock` (Poetry 2.0.1, igual ao do lock atual) → `source .venv/bin/activate && poetry install --with dev,docs`.
- Conferir `fastmcp 3.4.2`, `pytest 9.1.x` e `pytest-asyncio 1.4.x`. `poetry check --lock` precisa passar.

**`Dockerfile`** (multi-stage, a partir do lock)
- Builder com `pip install poetry==2.0.1`, `POETRY_VIRTUALENVS_IN_PROJECT=true`, `COPY pyproject.toml poetry.lock`, `poetry install --only main --no-root`, `COPY src/`, `poetry install --only main`.
- Runtime copia `/app/.venv` e `/app/src`; `PATH=/app/.venv/bin:$PATH`; mesmo `CMD`/`EXPOSE`.
- Novo `.dockerignore`: `.venv`, `tests`, `site`, `_plan`, `_experiments`, `.git`, `.claude`.
- Validar localmente com `docker build` e `docker run -e PORT=8080`, depois `curl /mcp` (initialize).

**`.github/workflows/test.yaml`** (novo; não existe workflow Python reutilizável em `reusable-workflows`)
- Gatilhos: `pull_request` em main, `push` em `feature/**` e `workflow_call`.
- Job `test`: setup-python 3.12 → `pipx install poetry==2.0.1` → `poetry check --lock` → `poetry install --with dev` → `ruff check src tests` → `ruff format --check src tests` → `pytest -q`.
- Job `docs`: `poetry install --only docs` → `mkdocs build --strict`.
- Ponto de extensão para o F4: job `apps-conformance` com MCPJam.

**`.github/workflows/deploy.yaml`**
- Adicionar o job `ci: uses: ./.github/workflows/test.yaml`; o `deploy` ganha `needs: ci`.
- Incluir `poetry.lock` em `paths`.

**`Makefile`:** alvos `test`, `lint`, `format`, `schema-snapshot` (`scripts/refresh_graphql_schema.py`), `smoke-live` (`pytest -m live`) e `docs-deploy`.

**`.mcp.json` do repo**
- Trocar o `/sse` remoto por **stdio local**: `{"command": ".venv/bin/python3.12", "args": ["-m","gobus_mcp"], "env": {"GOBUS_GRAPHQL_URL": "https://destaquesgovbr-graphql-api-klvx64dufq-rj.a.run.app/graphql"}}`. Quem desenvolve o servidor testa o código local.
- O remoto `/mcp` fica documentado para consumidores (Claude Desktop e conector do claude.ai).
- Ação manual fora do repo, para o usuário: o `~/.claude.json` ainda aponta para `/sse`.

**Commit mecânico inicial:** `chore: aplicar ruff format e ruff check --fix`, antes dos commits de teste, para o diff funcional ficar legível.

---

## 6. Higiene git (ordem; sem Co-Authored-By; mensagens em português)

1. Rodar `git fetch --prune`. Criar as tags de backup antes de mexer:
   - `backup/main-pre-squash-2026-10-05` em `ede3e5c`;
   - `backup/docs-mkdocs` em `a4fd7d3`;
   - `backup/fase2-analytics` em `7021868`.
2. `git switch -c feature/fase2.5-higiene origin/main`.
   - Leva o trabalho não commitado sem conflito: a árvore de `feature/fase2-analytics` é igual a `origin/main`, exceto o `CLAUDE.md`, que não está modificado.
3. `git restore docs/deploy.md`. A troca "HTTP → SSE" está errada e é descartada; o texto correto entra no commit de docs (passo 9).
4. Revisar `_plan/PLANO_V2.md:1283` e `_plan/STATUS_NER_BACKFILL.md:107` antes do commit. Eles contêm o IP do Cloud SQL (`<IP-CLOUD-SQL>`) e o repositório é AGPL, provavelmente público: redigir ou confirmar com o usuário. O grep por segredos não achou nada.
5. `git add -A _plan && git commit -m "chore: versionar planos em _plan/ e renomear PLANO.md para PLANO_V1.md"`.
   - O conteúdo é idêntico, então o git registra como rename.
6. `git add _experiments docs/experimentos mkdocs.yml && git commit -m "docs: versionar experimentos (BLUEPRINT v3) e nav de experimentos"`.
7. Adicionar `.claude/handoffs/` ao `.gitignore`, em commit `chore:`.
8. `git cherry-pick -n 7021868`, editar e commitar como `docs: corrigir gotchas do schema no CLAUDE.md`:
   - `baseDailyAvg` → `baselineDailyAvg`;
   - "`themeCode` sempre null";
   - "o baseline de `trendingThemes` inclui a janela";
   - `search` não tem `limit`; `articles` aceita até 250;
   - `endDate`/`dateTo` exclusivos e dias da API em UTC;
   - `agencies.label == code`;
   - "7 resources" (`:108`);
   - instalação de dev com `poetry install --with dev` (`:42,:70`);
   - seção MCP: Desktop/claude.ai em `/mcp`, `/sse` só por compatibilidade, Claude Code via stdio;
   - convenções novas: `output_schema=None` nas tools não-app, `today` injetável, null ≠ 0, escala Flesch `textstat-en`, janelas fechadas em D−1 BRT.
9. Seguir com os commits de deps/CI e os pares TDD da seção 4. Os docs vão no fim do PR.
10. Depois do merge do PR 1:
    - `git branch -f main origin/main` (os 3 commits pré-squash já estão incorporados e protegidos pela tag);
    - `git branch -D docs/mkdocs feature/fase1-docs-mcp-local feature/fase2-analytics`;
    - `git push origin --delete feature/fase1-docs-mcp-local feature/fase2-analytics` (PRs #6 e #7 já mergeados).

**Issue #3**
- `gh issue edit 3` com corpo novo:
  - `UPDATE news SET summary = NULL WHERE summary LIKE '[MOCK] Resumo gerado para teste local%'` (**4.600 linhas reais**, de 24/09/2025 a 27/02/2026), conferindo `SELECT count(*)` antes;
  - **sem DELETE**;
  - reindexação via `data-platform` workflow `typesense-maintenance-sync.yaml` (`incremental-sync`, `start_date=2025-09-24`, `end_date=2026-02-28`);
  - regenerar os resumos depois do F0(a).
- No gobus, o filtro defensivo `sanitize_summary` já cobre o problema.

---

## 7. Docs a atualizar

**PR 1**
- `docs/deploy.md`: HTTP stateless `/mcp` mais compat `/sse`+`/messages`; Dockerfile a partir do lock; gate de CI; `paths` com `poetry.lock`; env vars geridas pelo Terraform; `GOBUS_MAX_CONCURRENCY` opcional.
- `docs/quickstart.md`: `.mcp.json` stdio local e remoto `/mcp`.
- `docs/index.md:31` e `docs/arquitetura.md:5`: 13 tools, 7 resources, 4 prompts. Em `arquitetura.md`, também `cache`/`agency_catalog`/`readability`/`data_status`.
- `docs/tools/index.md`: tabela com 13 tools.
- Páginas novas em `docs/tools/`: `get-agency-summary.md`, `get-readability-recommendations.md`, `get-policy-lifecycle.md`, `score-article.md`.
- Páginas novas em `docs/resources/`: `readability-report.md`, `health-pipelines.md` (chaves e regras de status), `readability-dashboard.md`.
- `docs/dados/estado-dos-pipelines.md`: incidentes conhecidos, como o "indisponível" aparece em cada tool, escala de Flesch.
- `docs/prompts/*.md`: nomes `gobus_*`.
- `mkdocs.yml`: entradas de nav para todas as páginas (o CI roda `mkdocs build --strict`).
- `CLAUDE.md` (passo 8 da seção 6).
- `.claude/skills/gobus.md`.

**PR 2**
- `docs/tools/detect-anomalies.md` e `docs/tools/forecast-trends.md`: contrato, categorias, sensibilidade, domínios, metodologia (Laplace, SoV, janelas, defeso e normalização) e exemplos do payload.
- `CLAUDE.md`: arquitetura com `calendar`, `agency_activity`, `domains`, `analytics/`.
- `mkdocs.yml`.
- Em `_experiments/uc-2026-06-30-v3/BLUEPRINT.md`, marcar como desatualizados os trechos `:59` (dona via `responsibleAgencies`, que está vazio) e `:60` (`weekendCorrection` substituído por SoV).
- Republicar o gh-pages (`make docs-deploy`) depois de cada merge.

**Validação antes de cada merge (local-first):**
- Reiniciar o MCP stdio do workspace, que já aponta para `.venv`.
- Chamar `gobus_get_readability_recommendations("saude")`, `gobus_score_article` (um artigo de junho e um recente), `gobus_detect_anomalies`, `gobus_forecast_trends(horizon_days=7)` e o resource `gobus://health/pipelines`.
- Rodar `pytest -m live`.
- Colar as saídas na descrição do PR.
- Depois de 25/10: conferir a supressão da retomada em 27/10 e em 03/11.

### Critical Files for Implementation
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/server.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/tools/detect_anomalies.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/tools/forecast_trends.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/resources/health_pipelines.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/tools/get_readability_recommendations.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/src/gobus_mcp/client.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/tests/conftest.py
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/pyproject.toml
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/Dockerfile
- /Users/nitai/dev/destaquesgovbr/gobus-mcp/.github/workflows/deploy.yaml
