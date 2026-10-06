// ── forecast_radar.js ── ui://forecast-radar ← gobus_forecast_trends(horizon_days, limit)
// Card: radar do ritmo semanal dos temas em escala log2 (anel 1× = baseline; fora dele o
// tema ganha espaço) com o polígono da fatia no horizonte, top-3 com momentum e artigos
// esperados, chips do calendário e das janelas. Fullscreen (ou host sem fullscreen):
// horizonte pela mesma tool (opções do payload) e as razões por janela.
const APP_TOOL = "gobus_forecast_trends";
const APP_INLINE_AXES = 8;
const APP_TOP = 3;
const APP_MOMENTUM = {
  accelerating: ["↑", "acelerando"],
  decelerating: ["↓", "desacelerando"],
  stable: ["→", "estável"],
  undetermined: ["?", "indeterminado"],
};
const APP_CONFIDENCE = { high: "alta", medium: "média", low: "baixa" };
const APP_WINDOW_STATUS = { ok: "ok", degraded: "degradada", unavailable: "indisponível" };

function appX(value, digits) {
  return value === null || value === undefined ? DOM_DASH : domNumber(value, digits === undefined ? 1 : digits) + "×";
}

function appPct(value) {
  return value === null || value === undefined ? DOM_DASH : domInt(value * 100) + "%";
}

function appPlural(n, one, many) {
  return domInt(n) + " " + (n === 1 ? one : many);
}

// "AAAA-MM-DD" + n dias → "AAAA-MM-DD" (em UTC: só o calendário, sem fuso)
function appDay(iso, add) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return null;
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + (add || 0))).toISOString().slice(0, 10);
}

function appRhythm(t) {
  return t.weeklyMultiplier === null ? DOM_DASH : appX(t.weeklyMultiplier, 2) + "/semana";
}

function appMomentum(t) {
  return APP_MOMENTUM[t.momentum] || ["?", t.momentum];
}

function appExpected(p) {
  return p ? "≈ " + domInt(p.expectedArticles) + " artigos em " + p.horizonDays + " dias (" + domInt(p.low) + "–" + domInt(p.high) + ")" : "sem projeção";
}

// fatia no fim do horizonte ÷ fatia atual (o segundo polígono do radar)
function appProjected(t) {
  const p = t.projection;
  return p && p.shareNow > 0 ? p.shareAtHorizon / p.shareNow : null;
}

function appMult(v) {
  return (v >= 1 ? domInt(v) : "1/" + domInt(1 / v)) + "×";
}

function appWindowKeys(sc) {
  return Object.keys(sc.windows || {});
}

// ── radar ───────────────────────────────────────────────────────────────────
function appRadar(themes, width) {
  const W = Math.max(240, Math.min(width, 600));
  const H = Math.min(W, 400);
  const cx = W / 2;
  const cy = H / 2;
  const R = H / 2 - 28;
  const side = W / 2 - R - 12; // espaço dos rótulos laterais
  const named = side >= 60;
  const values = themes.map((t) => t.weeklyMultiplier);
  const projected = themes.map(appProjected);
  const logs = values.concat(projected).filter((v) => v !== null && v > 0).map((v) => Math.abs(Math.log2(v)));
  const L = Math.min(4, Math.max(1, Math.ceil(Math.max(0, ...logs) - 1e-9)));
  const radius = (v) => R * Math.max(0, Math.min(1, (Math.log2(v) + L) / (2 * L)));
  const n = themes.length;
  const at = (i, r) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };
  const label = "Ritmo semanal de " + appPlural(n, "tema", "temas") + " em escala log2: o anel 1× é o baseline; fora dele o tema ganha espaço, dentro perde";
  const svg = svgRoot(W, H, label, "radar");
  for (let k = -L + 1; k <= L; k++) {
    const v = Math.pow(2, k);
    const r = radius(v);
    svg.append(s("circle", { class: k === 0 ? "fr-ring fr-ring-1x" : "fr-ring", cx, cy, r: r.toFixed(2), "data-testid": k === 0 ? "ring-1x" : null }));
    // rótulo logo dentro do anel (o externo fica sem, para não brigar com o eixo de cima)
    if (k < L) svg.append(s("text", { class: "gb-axis fr-ring-label", x: (cx + 4).toFixed(1), y: (cy - r + 11).toFixed(1) }, appMult(v)));
  }
  themes.forEach((t, i) => {
    const end = at(i, R);
    svg.append(s("line", { class: "fr-axis", "data-testid": "axis-" + i, x1: cx, y1: cy, x2: end[0].toFixed(2), y2: end[1].toFixed(2) }));
    const pos = at(i, R + 10);
    const anchor = Math.abs(pos[0] - cx) < 4 ? "middle" : pos[0] > cx ? "start" : "end";
    const text = String(i + 1) + (named ? " " + svgFit(t.label, side - 18) : "");
    svg.append(s("text", { class: "fr-label", x: pos[0].toFixed(1), y: (pos[1] + 4).toFixed(1), "text-anchor": anchor }, s("title", null, t.label), text));
  });
  const points = (list) => list.map((v, i) => (v === null || v <= 0 ? null : at(i, radius(v))));
  const polygon = (pts, cls) => {
    if (n >= 3 && pts.every(Boolean)) svg.append(s("polygon", { class: cls, points: pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ") }));
  };
  const proj = points(projected);
  const now = points(values);
  polygon(proj, "fr-proj");
  polygon(now, "fr-now");
  proj.forEach((p, i) => {
    if (p) svg.append(s("circle", { class: "fr-proj-dot", cx: p[0].toFixed(2), cy: p[1].toFixed(2), r: 2.5, "data-testid": "proj-" + i }));
  });
  now.forEach((p, i) => {
    if (!p) return;
    const t = themes[i];
    svg.append(s("circle", {
      class: "fr-dot", "data-momentum": t.momentum, cx: p[0].toFixed(2), cy: p[1].toFixed(2), r: 4,
      "data-testid": "point-" + i, "data-label": t.label, "data-value": String(t.weeklyMultiplier),
    }, s("title", null, (i + 1) + ". " + t.label + ": " + appRhythm(t) + ", " + appMomentum(t)[1])));
  });
  return { svg, named };
}

function appRadarBlock(themes) {
  const { svg, named } = appRadar(themes, svgWidth());
  const legend = h("div", { class: "gb-legend", "data-testid": "legend" },
    h("span", null, h("span", { class: "gb-swatch fr-swatch", "data-kind": "now" }), "ritmo (×/semana)"),
    h("span", null, h("span", { class: "gb-swatch fr-swatch", "data-kind": "proj" }), "fatia no fim do horizonte ÷ fatia de hoje"),
    h("span", null, "anel tracejado: 1× (baseline), escala log2"));
  const names = named ? null : h("ol", { class: "fr-axes gb-small", "data-testid": "axes-legend" }, themes.map((t) => h("li", null, t.label)));
  return h("div", { class: "fr-chart" }, svg, legend, names);
}

function appSpark(daily, label) {
  const values = daily.map((d) => d.expected);
  const W = 140;
  const H = 26;
  const max = Math.max(...values, 1e-9);
  const x = (i) => 2 + (i * (W - 4)) / (values.length - 1);
  const y = (v) => H - 2 - (v * (H - 4)) / max;
  const text = "Artigos esperados por dia de " + label + " (" + values.length + " dias; fim de semana e feriado mais baixos)";
  return s("svg", { class: "fr-spark", viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": text },
    s("title", null, text),
    s("polyline", { class: "fr-spark-line", points: values.map((v, i) => x(i).toFixed(1) + "," + y(v).toFixed(1)).join(" ") }));
}

// ── top-3, seleção e pedido ao chat ─────────────────────────────────────────
function appSelect(sc, t) {
  if (!bridgeCan("updateModelContext")) return;
  const text = "No radar de tendências, o usuário selecionou o tema " + t.label + ": ritmo " + appRhythm(t) + ", " + appMomentum(t)[1] + ", confiança " + APP_CONFIDENCE[t.confidence] + "; " + appExpected(t.projection) + ".";
  bridgeUpdateModelContext(text).catch(bridgeWarn);
}

function appTop(sc, themes) {
  return h("ol", { class: "fr-top", "data-testid": "top" }, themes.slice(0, APP_TOP).map((t, i) => {
    const [icon, text] = appMomentum(t);
    const p = t.projection;
    return h("li", { class: "fr-top-item", "data-testid": "top-" + i },
      h("div", { class: "fr-top-head" },
        h("span", { class: "fr-rank" }, String(i + 1)),
        h("button", { type: "button", class: "gb-link fr-name", "data-testid": "select-" + i, onclick: () => appSelect(sc, t) }, t.label),
        h("span", { class: "fr-momentum", "data-momentum": t.momentum, "data-testid": "momentum-" + i }, icon + " " + text)),
      h("div", { class: "gb-small" }, "ritmo " + appRhythm(t) + " · confiança " + APP_CONFIDENCE[t.confidence]),
      h("div", { class: "gb-small gb-muted" }, appExpected(p)),
      p && p.daily && p.daily.length > 1 ? appSpark(p.daily, t.label) : null);
  }));
}

function appExplain(sc) {
  const horizon = sc.params.horizon_days;
  const last = domDate(appDay(sc.referenceDate, horizon - 1));
  const top = sc.themes.slice(0, APP_TOP).map((t, i) => (i + 1) + ") " + t.label + " — ritmo " + appRhythm(t) + ", " + appMomentum(t)[1] + ", confiança " + APP_CONFIDENCE[t.confidence] + ", " + appExpected(t.projection));
  const off = appWindowKeys(sc).filter((k) => sc.windows[k].status !== "ok").map((k) => "janela " + k + " " + APP_WINDOW_STATUS[sc.windows[k].status]);
  return "Explique o radar de tendências do Gobus (horizonte de " + horizon + " dias, até " + last + "): " + top.join("; ") + "." + (off.length ? " Atenção: " + off.join(", ") + "." : "") + " Quais temas devem ganhar espaço na pauta, com que confiança, e o que o calendário (defeso eleitoral) muda nisso?";
}

// ── cabeçalho, chips e tabelas ──────────────────────────────────────────────
function appHeader(sc) {
  const horizon = sc.params.horizon_days;
  const requested = sc.params.horizon_days_requested;
  const ref = sc.referenceDate;
  const cal = sc.calendar;
  const chips = [];
  if (cal.phase === "blackout") chips.push(domChip((cal.label || "Defeso eleitoral") + " · faltam " + appPlural(cal.daysToEnd, "dia", "dias"), "warn", "chip-calendar"));
  else if (cal.phase === "recovery") chips.push(domChip("Recuperação pós-defeso até " + domDate(cal.recoveryUntil), "info", "chip-calendar"));
  for (const key of appWindowKeys(sc)) {
    const w = sc.windows[key];
    if (w.status === "ok") continue;
    chips.push(domChip("Janela " + key + " " + APP_WINDOW_STATUS[w.status] + " (cobertura " + appPct(w.classifiedCoverage) + ")", w.status === "unavailable" ? "error" : "warn", "chip-window-" + key));
  }
  chips.push(domChip("Horizonte " + horizon + " dias" + (requested !== undefined && requested !== null && requested !== horizon ? " (pedido: " + requested + ")" : ""), null, "chip-horizon"));
  return h("header", { class: "gb-head" },
    h("div", null,
      h("h1", { class: "gb-title" }, "Radar de tendências"),
      h("p", { class: "gb-sub" }, "Projeção de " + domDate(ref) + " a " + domDate(appDay(ref, horizon - 1)) + " · janelas móveis de " + appWindowKeys(sc).join(", ") + " (share-of-voice)")),
    h("div", { class: "gb-row" }, chips));
}

function appBanner(sc) {
  const cal = sc.calendar;
  const horizon = sc.params.horizon_days;
  const last = appDay(sc.referenceDate, horizon - 1);
  const levels = (sc.platform && sc.platform.levelByPhase) || {};
  let text = null;
  if (cal.phase === "blackout" && cal.blackoutEnd && cal.blackoutEnd >= sc.referenceDate && cal.blackoutEnd <= last) {
    const change = levels.normal > levels.blackout
      ? "o volume esperado sobe de ~" + domInt(levels.blackout) + " para ~" + domInt(levels.normal) + " artigos por dia útil"
      : "o volume esperado fica em ~" + domInt(levels.normal) + " artigos por dia útil";
    text = "O horizonte cruza o fim do defeso (" + domDate(cal.blackoutEnd) + "): " + change + " a partir de " + domDate(appDay(cal.blackoutEnd, 1)) + ".";
  } else if (cal.phase === "recovery" && cal.recoveryUntil) {
    text = "Recuperação pós-defeso até " + domDate(cal.recoveryUntil) + ": confiança reduzida em um nível.";
  }
  return text ? h("p", { class: "gb-notice fr-banner", "data-tone": "info", "data-testid": "banner-calendar" }, text) : null;
}

function appThemeTable(sc) {
  const keys = appWindowKeys(sc);
  const headers = [{ label: "Tema" }, { label: "Ritmo", num: true }, { label: "Momentum" }, { label: "Confiança" }, { label: "Esperados" }]
    .concat(keys.map((k) => ({ label: k, num: true })));
  const rows = sc.themes.map((t) => [t.label, appRhythm(t), appMomentum(t)[1], APP_CONFIDENCE[t.confidence], appExpected(t.projection)]
    .concat(keys.map((k) => (t.windows[k] ? appX(t.windows[k].ratio) : DOM_DASH))));
  return domDetailsTable("Tabela dos temas (" + sc.themes.length + ")", headers, rows, "table");
}

function appWindowTable(sc) {
  const keys = appWindowKeys(sc);
  return domDetailsTable("Janelas e pesos", [
    { label: "Janela" }, { label: "Baseline", num: true }, { label: "Peso", num: true }, { label: "Peso efetivo", num: true },
    { label: "Cobertura", num: true }, { label: "Status" }, { label: "Dias úteis", num: true },
  ], keys.map((k) => {
    const w = sc.windows[k];
    return [k, w.baselineDays + " dias", domNumber(w.weight, 2), domNumber(w.effectiveWeight, 2), appPct(w.classifiedCoverage), APP_WINDOW_STATUS[w.status], domNumber(w.businessDays)];
  }), "table-windows");
}

function appHorizon(sc, view) {
  if (!bridgeCan("serverTools")) return null;
  const options = (sc.horizonOptions || []).map((d) => ({ value: d, label: d + " dias" }));
  return h("div", { class: "gb-row fr-controls", "data-testid": "controls" },
    h("span", { class: "gb-small gb-muted" }, "Horizonte"),
    domSegment(options, sc.params.horizon_days, (d) => view.call(APP_TOOL, { horizon_days: d, limit: sc.params.limit }, "Projetando " + d + " dias…"), "horizon-", "Horizonte"));
}

// ── render ──────────────────────────────────────────────────────────────────
function appRender(sc, view) {
  const full = document.documentElement.dataset.mode === "fullscreen";
  const rich = full || !bridgeCanDisplay("fullscreen");
  const nodes = [appHeader(sc)];
  if (rich) nodes.push(appHorizon(sc, view));
  if (sc.status === "unavailable") {
    const why = (sc.dataStatus || []).filter((d) => d.status !== "ok").map((d) => d.message).join("\n");
    nodes.push(domState("unavailable", "Forecast indisponível", why || "Nenhuma janela com cobertura de classificação suficiente."), domNotices(sc.notices));
    if (rich) nodes.push(appWindowTable(sc));
    return nodes;
  }
  if (!sc.themes.length) {
    nodes.push(domState("empty", "Nenhum tema com dados suficientes", "As janelas têm cobertura de classificação, mas nenhum tema tem artigos suficientes para calcular a razão."), domNotices(sc.notices));
    if (rich) nodes.push(appWindowTable(sc));
    return nodes;
  }
  const themes = rich ? sc.themes : sc.themes.slice(0, APP_INLINE_AXES);
  nodes.push(appRadarBlock(themes), appTop(sc, sc.themes), appBanner(sc));
  if (!rich && sc.themes.length > themes.length) nodes.push(h("p", { class: "gb-small gb-muted" }, "+" + appPlural(sc.themes.length - themes.length, "tema", "temas") + " no fullscreen"));
  nodes.push(rich ? domNotices(sc.notices) : (sc.notices.length ? h("details", { class: "gb-details", "data-testid": "notices-details" }, h("summary", null, "Avisos (" + sc.notices.length + ")"), domNotices(sc.notices)) : null));
  const expand = !full && bridgeCanDisplay("fullscreen")
    ? domAction("Expandir", () => bridgeRequestDisplayMode("fullscreen").then(() => view.refresh()), "action-expand")
    : null;
  const explain = bridgeCan("message") ? domAction("Explicar no chat", () => bridgeSendMessage(appExplain(sc)), "action-explain") : null;
  const actions = [expand, explain].filter(Boolean);
  if (actions.length) nodes.push(h("div", { class: "gb-actions" }, actions));
  nodes.push(appThemeTable(sc));
  if (rich) nodes.push(appWindowTable(sc));
  return nodes;
}

domMount({
  kind: "gobus.forecast",
  title: "Radar de tendências",
  loadingText: (args) => "Projetando tendências" + (args.horizon_days ? " para " + args.horizon_days + " dias" : "") + "…",
  render: appRender,
});
