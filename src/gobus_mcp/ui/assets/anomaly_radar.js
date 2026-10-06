// ── anomaly_radar.js ── ui://anomaly-radar ← gobus_detect_anomalies(sensitivity, domain_filter)
// Card: 8 gauges por domínio (arco externo = pico, interno = silêncio; marcas nos limiares
// que vêm do payload), chips do defeso e dos temas e o total de sinais. Fullscreen (ou host
// sem fullscreen): lista com toggle local pico/silêncio/outros, sensibilidade e domínio
// pela mesma tool, "investigar" por ui/message e seleção por ui/update-model-context.
const APP_TOOL = "gobus_detect_anomalies";
const APP_KIND = {
  sustained_spike: "Pico sustentado",
  sustained_drop: "Queda sustentada",
  coordinated_silence: "Silêncio coordenado",
  concentrated_coverage: "Cobertura concentrada",
  burst: "Rajada",
  new_entity: "Entidade nova",
  calendar_explained: "Explicado pelo calendário",
  normal: "Sem anomalia",
};
// pico = tema em alta e cobertura concentrada; silêncio = queda de tema e silêncio coordenado
const APP_GROUP = {
  sustained_spike: "spikes",
  concentrated_coverage: "spikes",
  sustained_drop: "silences",
  coordinated_silence: "silences",
};
const APP_TABS = [["spikes", "Picos"], ["silences", "Silêncios"], ["others", "Outros"]];
const APP_BAND = { normal: "normal", watch: "atenção", alert: "alerta" };
const APP_BAND_TONE = { watch: "warn", alert: "error" };
const APP_CONFIDENCE = { high: "alta", medium: "média", low: "baixa" };
const APP_SENSITIVITY = { high: "Alta", medium: "Média", low: "Baixa" };
const APP_STATUS = { degraded: "degradados", unavailable: "indisponíveis" };
// mesmos rótulos do Markdown (analytics/render.py FLAG_PT)
const APP_FLAGS = {
  classifier_changed: "troca de classificador no baseline",
  degraded_coverage: "cobertura de classificação parcial",
  recovery: "recuperação pós-defeso",
  resumed_agencies: "inclui agências retomadas",
  owner_activity_unknown: "atividade da dona desconhecida",
  republishers_excluded: "republicadoras excluídas",
  thin_baseline: "baseline pequeno",
};
const APP_GAUGE = { w: 120, h: 68, cx: 60, cy: 60, outer: 50, inner: 37, stroke: 9 };
const appState = { tab: "spikes" };

function appX(value) {
  return value === null || value === undefined ? DOM_DASH : domNumber(value) + "×";
}

function appPlural(n, one, many) {
  return domInt(n) + " " + (n === 1 ? one : many);
}

function appLastDay(iso) {
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? DOM_DASH : domDate(new Date(t - 1).toISOString());
}

function appSpan(win) {
  return domDate(win.start) + "–" + appLastDay(win.end);
}

function appDomainLabel(sc, domain) {
  const found = (sc.domains || []).find((d) => d.domain === domain);
  return found ? found.label : domain;
}

function appArgs(params, overrides) {
  const p = Object.assign({ sensitivity: params.sensitivity, domain_filter: params.domain_filter }, overrides || {});
  const args = { sensitivity: p.sensitivity };
  if (p.domain_filter) args.domain_filter = p.domain_filter;
  return args;
}

// ── sinais ──────────────────────────────────────────────────────────────────
function appEntityDetail(e, days) {
  if (e.windowCount === 0) return "sem menções próprias em " + days + " dias (só republicadoras)";
  const parts = [
    appPlural(e.windowCount, "artigo", "artigos") + " em " + days + " dias",
    appPlural(e.windowAgencies, "agência", "agências"),
    "razão " + appX(e.ratio),
  ];
  const owner = e.owner ? e.owner.agencyName || e.owner.agencyKey : null;
  if (e.kind === "coordinated_silence" && owner) {
    const activity = e.ownerActivityRatio === null ? "produção desconhecida" : "produção " + appX(e.ownerActivityRatio) + " do baseline";
    parts.push("dona: " + owner + " (" + appPlural(e.ownerWindowCount || 0, "menção", "menções") + "; " + activity + ")");
  } else if (e.kind === "burst") {
    parts.push(domInt(Math.round(e.maxDayShare * 100)) + "% num único dia");
  } else if (e.kind === "new_entity") {
    parts.push("sem menções no baseline");
  } else if (owner) {
    parts.push("dona: " + owner);
  }
  return parts.join(" · ");
}

function appItems(sc) {
  const tw = sc.themes.windows;
  const items = (sc.themes.signals || []).map((t) => ({
    id: "theme-" + t.label, source: "theme", name: t.label, kind: t.kind, domain: t.domain,
    severity: t.severity, band: t.band, confidence: t.confidence, flags: t.flags || [], signal: t,
    detail: "fatia " + appX(t.ratioShort) + " em " + tw.short.days + " dias e " + appX(t.ratioLong) + " em " + tw.long.days + " · " + appPlural(t.countShort, "artigo", "artigos") + " em " + tw.short.days + " dias",
  }));
  const days = sc.entities.window.days;
  for (const e of sc.entities.signals || []) {
    items.push({
      id: e.entityId, source: "entity", name: e.name, kind: e.kind, domain: e.domain,
      severity: e.severity, band: e.band, confidence: e.confidence, flags: e.flags || [], signal: e,
      detail: appEntityDetail(e, days),
    });
  }
  return items.sort((a, b) => (a.kind === "normal") - (b.kind === "normal") || b.severity - a.severity);
}

function appGroup(item) {
  return APP_GROUP[item.kind] || "others";
}

// sinais que pedem investigação: tudo menos o explicado pelo calendário e o normal
function appNotable(items) {
  return items.filter((i) => i.kind !== "normal" && i.kind !== "calendar_explained");
}

// ── gauges ──────────────────────────────────────────────────────────────────
function appPoint(r, f) {
  const a = Math.PI * (1 - f);
  return [APP_GAUGE.cx + r * Math.cos(a), APP_GAUGE.cy - r * Math.sin(a)];
}

function appArc(r, from, to) {
  const p0 = appPoint(r, from);
  const p1 = appPoint(r, to);
  return "M " + p0[0].toFixed(2) + " " + p0[1].toFixed(2) + " A " + r + " " + r + " 0 0 1 " + p1[0].toFixed(2) + " " + p1[1].toFixed(2);
}

function appGauge(d, bands, onPick, active) {
  const g = APP_GAUGE;
  const up = d.spikes + d.concentrated;
  const label = d.label + ": pico " + domNumber(d.spikeLevel, 2) + " (" + APP_BAND[d.spikeBand] + "), silêncio " + domNumber(d.silenceLevel, 2) + " (" + APP_BAND[d.silenceBand] + "); " + appPlural(up, "pico", "picos") + ", " + appPlural(d.silences, "silêncio", "silêncios");
  const svg = svgRoot(g.w, g.h, label, null);
  const arcs = [[g.outer, d.spikeLevel, "spike", d.spikeBand], [g.inner, d.silenceLevel, "silence", d.silenceBand]];
  for (const [r, level, kind, band] of arcs) {
    svg.append(s("path", { class: "ar-track", d: appArc(r, 0, 1) }));
    if (level > 0) svg.append(s("path", { class: "ar-arc", "data-kind": kind, "data-band": band, d: appArc(r, 0, Math.min(1, level)) }));
  }
  for (const t of [bands.watch, bands.alert]) {
    const a = appPoint(g.inner - g.stroke / 2 - 2, t);
    const b = appPoint(g.outer + g.stroke / 2 + 2, t);
    svg.append(s("line", { class: "ar-tick", "data-tick": String(t), x1: a[0].toFixed(2), y1: a[1].toFixed(2), x2: b[0].toFixed(2), y2: b[1].toFixed(2) }));
  }
  const body = [
    svg,
    h("div", { class: "ar-gauge-label" }, d.label),
    h("div", { class: "ar-gauge-counts gb-small" }, h("span", { class: "ar-up" }, "▲ " + domInt(up)), " ", h("span", { class: "ar-down" }, "▼ " + domInt(d.silences))),
  ];
  const attrs = {
    class: "ar-gauge", title: label, "data-testid": "gauge-" + d.domain,
    "data-spike-band": d.spikeBand, "data-silence-band": d.silenceBand,
  };
  if (!onPick) return h("div", attrs, body);
  return h("button", Object.assign(attrs, { type: "button", "aria-pressed": String(Boolean(active)), onclick: onPick }), body);
}

function appGauges(sc, view, rich) {
  const current = sc.params.domain_filter || null;
  const pick = (domain) => () => appCall(view, sc, { domain_filter: domain === current ? "" : domain });
  const clickable = rich && bridgeCan("serverTools");
  return [
    h("div", { class: "ar-legend gb-legend", "data-testid": "legend" },
      h("span", null, h("span", { class: "gb-swatch ar-swatch", "data-kind": "spike" }), "pico (tema em alta, cobertura concentrada)"),
      h("span", null, h("span", { class: "gb-swatch ar-swatch", "data-kind": "silence" }), "silêncio (queda de tema, silêncio coordenado)"),
      h("span", null, "marcas: atenção ≥ " + domNumber(sc.severityBands.watch, 2) + " · alerta ≥ " + domNumber(sc.severityBands.alert, 2))),
    h("div", { class: "ar-gauges", "data-testid": "gauges" },
      sc.domains.map((d) => appGauge(d, sc.severityBands, clickable ? pick(d.domain) : null, d.domain === current))),
  ];
}

function appTotals(sc, items) {
  const up = sc.domains.reduce((n, d) => n + d.spikes + d.concentrated, 0);
  const down = sc.domains.reduce((n, d) => n + d.silences, 0);
  const omitted = sc.entities.omitted || {};
  const others = items.filter((i) => appGroup(i) === "others" && i.kind !== "normal").length
    + ["burst", "new_entity", "calendar_explained"].reduce((n, k) => n + (omitted[k] || 0), 0);
  return h("p", { class: "gb-small", "data-testid": "totals" },
    h("strong", null, appPlural(up, "pico", "picos")), " · ", h("strong", null, appPlural(down, "silêncio", "silêncios")),
    " · " + appPlural(others, "outro sinal", "outros sinais") + " (rajadas, entidades novas, calendário)");
}

// ── cabeçalho e avisos ──────────────────────────────────────────────────────
function appSince(sc, key, code) {
  const status = (sc.dataStatus || []).find((d) => d.key === key && d.since);
  if (status) return status.since;
  const notice = (sc.notices || []).find((n) => n.code === code && n.since);
  return notice ? notice.since : null;
}

function appHeader(sc) {
  const cal = sc.calendar;
  const chips = [];
  if (cal.phase === "blackout") chips.push(domChip((cal.label || "Defeso eleitoral") + " · faltam " + appPlural(cal.daysToEnd, "dia", "dias"), "warn", "chip-calendar"));
  else if (cal.phase === "recovery") chips.push(domChip("Recuperação pós-defeso até " + domDate(cal.recoveryUntil), "info", "chip-calendar"));
  if (sc.themes.status !== "ok") {
    const since = appSince(sc, "themes", "THEMES_UNCLASSIFIED");
    chips.push(domChip("Temas " + APP_STATUS[sc.themes.status] + (since ? " desde " + domDate(since) : ""), sc.themes.status === "unavailable" ? "error" : "warn", "chip-themes"));
  }
  if (sc.entities.status !== "ok") chips.push(domChip("Entidades: dados " + APP_STATUS[sc.entities.status], sc.entities.status === "unavailable" ? "error" : "warn", "chip-entities"));
  chips.push(domChip("Sensibilidade " + (APP_SENSITIVITY[sc.params.sensitivity] || sc.params.sensitivity).toLowerCase(), null, "chip-sensitivity"));
  if (sc.params.domain_filter) chips.push(domChip("Domínio: " + appDomainLabel(sc, sc.params.domain_filter), "info", "chip-domain"));
  const tw = sc.themes.windows;
  return h("header", { class: "gb-head" },
    h("div", null,
      h("h1", { class: "gb-title" }, "Radar de anomalias"),
      h("p", { class: "gb-sub" }, "Entidades " + appSpan(sc.entities.window) + " · temas nos últimos " + tw.short.days + " e " + tw.long.days + " dias (janelas móveis)")),
    h("div", { class: "gb-row" }, chips));
}

function appBanner(sc) {
  const cal = sc.calendar;
  let text = null;
  if (cal.phase === "blackout" && cal.blackoutEnd) {
    text = "Defeso eleitoral até " + domDate(cal.blackoutEnd) + ": silêncio de agência calada no defeso aparece como “explicado pelo calendário”, não como silêncio coordenado.";
  } else if (cal.phase === "recovery" && cal.recoveryUntil) {
    text = "Recuperação pós-defeso até " + domDate(cal.recoveryUntil) + ": baselines do período antes do defeso e confiança reduzida em um nível.";
  }
  return text ? h("p", { class: "gb-notice ar-banner", "data-tone": "info", "data-testid": "banner-calendar" }, text) : null;
}

function appNotices(sc, rich) {
  const list = domNotices(sc.notices);
  if (!list || rich) return list;
  return h("details", { class: "gb-details", "data-testid": "notices-details" },
    h("summary", null, "Avisos de dados (" + sc.notices.length + ")"), list);
}

// ── lista (fullscreen) ──────────────────────────────────────────────────────
function appSpark(e, windowDays) {
  const values = e.daily || [];
  if (values.length < 2) return null;
  const owner = e.ownerDaily && e.ownerDaily.length === values.length ? e.ownerDaily : null;
  const W = 140;
  const H = 30;
  const max = Math.max(1, ...values, ...(owner || []));
  const x = (i) => 2 + (i * (W - 4)) / (values.length - 1);
  const y = (v) => H - 2 - (v * (H - 4)) / max;
  const line = (arr) => arr.map((v, i) => x(i).toFixed(1) + "," + y(v).toFixed(1)).join(" ");
  const label = "Menções por dia nos últimos " + values.length + " dias (em destaque, a janela de " + windowDays + ")" + (owner ? "; tracejado: a agência dona" : "");
  const start = x(Math.max(0, values.length - windowDays));
  const svg = s("svg", { class: "ar-spark", viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": label, "data-testid": "spark-" + e.entityId }, s("title", null, label));
  svg.append(s("rect", { class: "ar-spark-window", x: (start - 1).toFixed(1), y: 0, width: (W - start + 1).toFixed(1), height: H }));
  svg.append(s("polyline", { class: "ar-spark-line", points: line(values) }));
  if (owner) svg.append(s("polyline", { class: "ar-spark-owner", points: line(owner) }));
  return svg;
}

function appSeverity(item) {
  return "severidade " + domNumber(item.severity, 2) + " · " + APP_BAND[item.band];
}

function appInvestigate(item, sc) {
  const sig = item.signal;
  const domain = appDomainLabel(sc, item.domain);
  const where = " no radar de anomalias: " + item.detail + "; " + appSeverity(item) + ", confiança " + APP_CONFIDENCE[item.confidence] + ".";
  if (item.source === "theme") {
    return "Investigue o " + APP_KIND[item.kind].toLowerCase() + " do tema \"" + item.name + "\" (" + domain + ")" + where + " Use gobus_search_news com o tema e gobus_detect_trends para ver os artigos e as agências por trás do movimento.";
  }
  return "Investigue o sinal \"" + APP_KIND[item.kind] + "\" de " + item.name + " (" + sig.entityId + ", " + sig.type + ", " + domain + ")" + where + " A janela é " + appSpan(sc.entities.window) + ". Use gobus_get_entity_profile com \"" + item.name + "\" para a cobertura e as entidades relacionadas, e gobus_search_news para os artigos da janela.";
}

function appSelect(item, sc) {
  if (!bridgeCan("updateModelContext")) return;
  const text = "No radar de anomalias, o usuário selecionou " + item.name + " (" + APP_KIND[item.kind] + ", " + appDomainLabel(sc, item.domain) + "): " + item.detail + "; " + appSeverity(item) + ".";
  bridgeUpdateModelContext(text).catch(bridgeWarn);
}

function appFlagText(flags) {
  const labels = flags.map((f) => APP_FLAGS[f]).filter(Boolean);
  return labels.length ? h("div", { class: "gb-small gb-muted" }, labels.join(" · ")) : null;
}

function appItem(item, sc) {
  const sig = item.signal;
  const meta = [APP_KIND[item.kind] || item.kind, appDomainLabel(sc, item.domain)];
  if (item.source === "entity") meta.push(sig.type);
  else meta.push("tema");
  const select = h("button", { type: "button", class: "gb-link ar-name", "data-testid": "select-" + item.id, onclick: () => appSelect(item, sc) }, item.name);
  const explain = item.source === "entity" && sig.explanation ? h("div", { class: "gb-small gb-muted" }, sig.explanation) : null;
  const investigate = bridgeCan("message") && item.kind !== "normal"
    ? domAction("Investigar", () => bridgeSendMessage(appInvestigate(item, sc)), "investigate-" + item.id)
    : null;
  return h("li", { class: "ar-item", "data-testid": "signal-" + item.id, "data-kind": item.kind, "data-band": item.band },
    h("div", { class: "ar-item-head" }, select,
      item.kind !== "normal" ? domChip(appSeverity(item), APP_BAND_TONE[item.band] || null, null) : null,
      domChip("confiança " + APP_CONFIDENCE[item.confidence], null, null)),
    h("div", { class: "gb-muted gb-small" }, meta.join(" · ")),
    h("div", { class: "gb-small" }, item.detail),
    explain,
    appFlagText(item.flags),
    item.source === "entity" ? appSpark(sig, sc.entities.window.days) : null,
    investigate ? h("div", { class: "ar-item-actions" }, investigate) : null);
}

function appList(sc, items, view) {
  const counts = { spikes: 0, silences: 0, others: 0 };
  for (const item of items) counts[appGroup(item)] += 1;
  const tabs = domSegment(APP_TABS.map(([value, label]) => ({ value, label: label + " (" + counts[value] + ")" })), appState.tab,
    (value) => { appState.tab = value; view.render(view.result); }, "tab-", "Tipo de sinal");
  const shown = items.filter((i) => appGroup(i) === appState.tab);
  const omitted = Object.values(sc.entities.omitted || {}).reduce((a, b) => a + b, 0);
  return h("section", { class: "gb-section ar-list-section" },
    h("div", { class: "ar-tabs" }, tabs),
    h("ul", { class: "ar-list", "data-testid": "signals" },
      shown.length ? shown.map((item) => appItem(item, sc)) : h("li", { class: "gb-muted gb-small" }, "Nenhum sinal nesta aba.")),
    omitted ? h("p", { class: "gb-small gb-muted", "data-testid": "omitted" }, "+" + appPlural(omitted, "sinal ficou", "sinais ficaram") + " fora do painel (orçamento do payload); a lista completa está no texto da resposta.") : null);
}

function appCall(view, sc, overrides) {
  const args = appArgs(sc.params, overrides);
  return view.call(APP_TOOL, args, "Recalculando o radar (sensibilidade " + (APP_SENSITIVITY[args.sensitivity] || args.sensitivity).toLowerCase() + ")…");
}

function appControls(sc, view) {
  if (!bridgeCan("serverTools")) return null;
  const options = (sc.sensitivityOptions || []).map((v) => ({ value: v, label: APP_SENSITIVITY[v] || v }));
  const current = sc.params.domain_filter || "ALL";
  const domains = [{ domain: "ALL", label: "Todos" }].concat(sc.domains);
  return h("section", { class: "ar-controls", "data-testid": "controls" },
    h("div", { class: "gb-row" }, h("span", { class: "gb-small gb-muted" }, "Sensibilidade"),
      domSegment(options, sc.params.sensitivity, (v) => appCall(view, sc, { sensitivity: v }), "sens-", "Sensibilidade")),
    h("div", { class: "ar-domains", role: "group", "aria-label": "Domínio" }, domains.map((d) => h("button", {
      type: "button", class: "gb-btn", "data-testid": "domain-" + d.domain, "aria-pressed": String(d.domain === current),
      onclick: () => { if (d.domain !== current) appCall(view, sc, { domain_filter: d.domain === "ALL" ? "" : d.domain }); },
    }, d.label))));
}

// ── tabelas ─────────────────────────────────────────────────────────────────
function appDomainTable(sc) {
  return domDetailsTable("Tabela dos domínios", [
    { label: "Domínio" }, { label: "Picos", num: true }, { label: "Concentradas", num: true }, { label: "Silêncios", num: true },
    { label: "Pico (sev.)", num: true }, { label: "Silêncio (sev.)", num: true },
  ], sc.domains.map((d) => [d.label, domInt(d.spikes), domInt(d.concentrated), domInt(d.silences),
    domNumber(d.spikeLevel, 2) + " " + APP_BAND[d.spikeBand], domNumber(d.silenceLevel, 2) + " " + APP_BAND[d.silenceBand]]));
}

function appSignalTable(sc, items) {
  return domDetailsTable("Tabela dos sinais (" + items.length + ")", [
    { label: "Sinal" }, { label: "Classe" }, { label: "Domínio" }, { label: "Severidade", num: true }, { label: "Confiança" }, { label: "Detalhe" },
  ], items.map((i) => [i.name, APP_KIND[i.kind] || i.kind, appDomainLabel(sc, i.domain), domNumber(i.severity, 2), APP_CONFIDENCE[i.confidence], i.detail]), "table-signals");
}

// ── render ──────────────────────────────────────────────────────────────────
function appRender(sc, view) {
  const full = document.documentElement.dataset.mode === "fullscreen";
  const rich = full || !bridgeCanDisplay("fullscreen");
  const nodes = [appHeader(sc)];
  if (sc.status === "unavailable") {
    const why = [sc.themes.note, sc.entities.note].filter(Boolean).join("\n");
    nodes.push(domState("unavailable", "Radar indisponível", why || "Sem dados de temas nem de entidades."), domNotices(sc.notices));
    if (rich) nodes.push(appControls(sc, view));
    return nodes;
  }
  const items = appItems(sc);
  const notable = appNotable(items);
  if (rich) nodes.push(appControls(sc, view));
  nodes.push(appGauges(sc, view, rich), appTotals(sc, items));
  if (sc.status === "empty") {
    nodes.push(domState("empty", "Nenhum sinal" + (sc.params.domain_filter ? " em " + appDomainLabel(sc, sc.params.domain_filter) : ""), "Nada fora do padrão nesta sensibilidade e neste domínio. Os gauges resumem todos os domínios."));
  } else if (!notable.length && !items.some((i) => i.kind === "calendar_explained")) {
    // só é "nada fora do padrão" com os dois blocos ok; com dado faltando, não se afirma
    nodes.push(sc.status === "ok"
      ? h("p", { class: "gb-small", "data-testid": "quiet" }, "Nada fora do padrão nesta sensibilidade" + (items.length ? ": " + appPlural(items.length, "entidade acompanhada", "entidades acompanhadas") + " sem anomalia." : "."))
      : h("p", { class: "gb-small", "data-testid": "no-signals" }, "Nenhum sinal nos dados disponíveis — com parte dos dados faltando, isso não quer dizer que nada saiu do padrão."));
  }
  // notas dos blocos degradados ou indisponíveis (o porquê do status partial)
  for (const note of [sc.themes.status !== "ok" ? sc.themes.note : null, sc.entities.status !== "ok" ? sc.entities.note : null]) {
    if (note) nodes.push(h("p", { class: "gb-small gb-muted", "data-testid": "block-note" }, note));
  }
  nodes.push(appBanner(sc));
  if (rich) nodes.push(appList(sc, items, view));
  nodes.push(appNotices(sc, rich));
  const expand = !full && bridgeCanDisplay("fullscreen")
    ? domAction("Expandir", () => bridgeRequestDisplayMode("fullscreen").then(() => view.refresh()), "action-expand")
    : null;
  const investigate = bridgeCan("message") && notable.length
    ? domAction("Investigar no chat", () => {
      const top = notable.slice(0, 5).map((i, n) => (n + 1) + ") " + i.name + " — " + APP_KIND[i.kind].toLowerCase() + ", " + i.detail + ", " + appSeverity(i));
      return bridgeSendMessage("No radar de anomalias (sensibilidade " + (APP_SENSITIVITY[sc.params.sensitivity] || sc.params.sensitivity).toLowerCase() + ", domínio " + (sc.params.domain_filter ? appDomainLabel(sc, sc.params.domain_filter) : "todos") + "), os principais sinais são: " + top.join("; ") + ". Investigue as causas com gobus_get_entity_profile (entidades) e gobus_search_news (temas) e diga se algum é explicado pelo calendário do defeso eleitoral.");
    }, "action-investigate")
    : null;
  const actions = [expand, investigate].filter(Boolean);
  if (actions.length) nodes.push(h("div", { class: "gb-actions" }, actions));
  nodes.push(appDomainTable(sc));
  if (rich && items.length) nodes.push(appSignalTable(sc, items));
  return nodes;
}

domMount({
  kind: "gobus.anomalies",
  title: "Radar de anomalias",
  loadingText: (args) => "Calculando o radar de anomalias" + (args.domain_filter ? " (" + args.domain_filter + ")" : "") + "…",
  render: appRender,
});
