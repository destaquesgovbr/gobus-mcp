// ── readability_dashboard.js ── ui://readability-dashboard ← gobus_get_readability_recommendations
// Ranking: barras do Flesch (0–100) com as metas 30/50 e a faixa-alvo; inline mostra o
// top-8, fullscreen o ranking inteiro. Clique numa agência → a mesma tool com agency_key
// (detalhe: pior/melhor artigo, benchmark da Agência Brasil, recomendações).
const APP_TOOL = "gobus_get_readability_recommendations";
const APP_INLINE_BARS = 8;
const appMemory = { ranking: null };

function appArgs(params, overrides) {
  const p = params || {};
  const args = Object.assign({ days: p.days, limit: p.limit, date_to: p.date_to, agency_key: p.agency_key }, overrides || {});
  for (const key of Object.keys(args)) {
    if (args[key] === null || args[key] === undefined || args[key] === "") delete args[key];
  }
  return args;
}

function appFlesch(row) {
  if (!row || row.flesch === null || row.flesch === undefined) return DOM_DASH;
  let text = domNumber(row.flesch);
  if (row.fleschRaw !== null && row.fleschRaw !== undefined && Math.abs(row.fleschRaw - row.flesch) >= 0.05) {
    text += " (bruto " + domNumber(row.fleschRaw) + ")";
  }
  return text;
}

// "**negrito**" do Markdown das recomendações → <strong>, o resto como texto.
function appInline(text) {
  return String(text).replace(/^\d+\.\s*/, "").split("**").map((part, i) => (i % 2 ? h("strong", null, part) : part));
}

function appAgencyLabel(row) {
  return row.agencyName + (row.isRepublisher ? " (republicadora)" : "");
}

function appHeader(sc, title) {
  const chips = [];
  if (sc.windowShifted && sc.windowNote) chips.push(domChip("Janela efetiva: " + sc.windowNote, "warn", "chip-window"));
  else if (sc.requestedWindow && !sc.effectiveWindow && !sc.error) chips.push(domChip("Sem Flesch no histórico", "error", "chip-window"));
  const cov = sc.coverage;
  if (cov && cov.periodsTotal) chips.push(domChip("Flesch em " + cov.periodsWithData + " de " + cov.periodsTotal + " meses", cov.periodsWithData === cov.periodsTotal ? "ok" : "warn", "chip-coverage"));
  const shown = sc.effectiveWindow || sc.requestedWindow;
  return h("header", { class: "gb-head" },
    h("div", null, h("h1", { class: "gb-title" }, title), shown ? h("p", { class: "gb-sub" }, domSpan(shown)) : null),
    chips.length ? h("div", { class: "gb-row" }, chips) : null);
}

function appLegend(sc) {
  return h("div", { class: "gb-legend", "data-testid": "legend" },
    (sc.bands || []).map((b) => h("span", null, h("span", { class: "gb-swatch", "data-band": b.key }), b.label + " " + domInt(b.lower) + "–" + domInt(b.upper))),
    h("span", null, "Meta ≥" + domInt(sc.targetService) + " serviço · ≥" + domInt(sc.targetInstitutional) + " institucional"),
    h("span", null, "Flesch (fórmula inglesa do textstat), limitado a 0–100"));
}

function appTargets(sc) {
  return [
    { value: sc.targetInstitutional, label: domInt(sc.targetInstitutional) },
    { value: sc.targetService, label: domInt(sc.targetService) + " meta" },
  ];
}

function appActions(nodes) {
  const items = nodes.filter(Boolean);
  return items.length ? h("div", { class: "gb-actions" }, items) : null;
}

function appExpandButton(view) {
  if (document.documentElement.dataset.mode === "fullscreen" || !bridgeCanDisplay("fullscreen")) return null;
  return domButton("Expandir", () => bridgeRequestDisplayMode("fullscreen").then(() => view.refresh()).catch(bridgeFail), "action-expand");
}

async function appOpenAgency(view, sc, row) {
  await view.call(APP_TOOL, appArgs(sc.params, { agency_key: row.agencyKey }), "Carregando " + row.agencyName + "…");
  const detail = view.result && view.result.structuredContent;
  if (detail && detail.agency && bridgeCan("updateModelContext")) {
    const a = detail.agency;
    const text = "No app de legibilidade, o usuário abriu o diagnóstico de " + a.agencyName + " (" + a.agencyKey + "): Flesch " + appFlesch(a) + ", janela " + domSpan(detail.effectiveWindow || detail.requestedWindow) + ".";
    bridgeUpdateModelContext(text).catch(() => {});
  }
}

function appTable(sc, view) {
  const clickable = bridgeCan("serverTools");
  const name = (row) => (clickable
    ? h("button", { type: "button", class: "gb-link", "data-testid": "row-" + row.agencyKey, onclick: () => appOpenAgency(view, sc, row) }, appAgencyLabel(row))
    : appAgencyLabel(row));
  const rows = (sc.agencies || []).map((row, i) => [
    domInt(i + 1), name(row), appFlesch(row), row.bandLabel || DOM_DASH,
    domInt(row.articleCount) + " (" + domInt(row.articlesWithData) + ")", domSigned(row.gapToTarget),
  ]);
  const missing = (sc.agenciesWithoutData || []).map((row) => [DOM_DASH, name(row), DOM_DASH, "sem dado", domInt(row.articleCount) + " (0)", DOM_DASH]);
  const table = domDetailsTable("Tabela do ranking (" + (rows.length + missing.length) + " agências)",
    [{ label: "#" }, { label: "Agência" }, { label: "Flesch", num: true }, { label: "Nível" }, { label: "Artigos (com Flesch)", num: true }, { label: "Gap até 50", num: true }],
    rows.concat(missing));
  const body = table.querySelectorAll("tbody tr");
  (sc.agenciesWithoutData || []).forEach((row, i) => body[rows.length + i].setAttribute("data-testid", "no-data-" + row.agencyKey));
  return table;
}

function appRanking(sc, view) {
  appMemory.ranking = view.result;
  const full = document.documentElement.dataset.mode === "fullscreen";
  const agencies = sc.agencies || [];
  const shown = full ? agencies : agencies.slice(0, APP_INLINE_BARS);
  const clickable = bridgeCan("serverTools");
  const nodes = [appHeader(sc, "Legibilidade por agência")];
  if (shown.length) {
    nodes.push(svgBars(shown.map((row) => ({
      label: appAgencyLabel(row), value: row.flesch, display: appFlesch(row), band: row.band,
      title: appAgencyLabel(row) + ": Flesch " + appFlesch(row) + " (" + (row.bandLabel || "sem faixa") + "), " + domInt(row.articleCount) + " artigos",
      testid: "bar-" + row.agencyKey, onClick: clickable ? () => appOpenAgency(view, sc, row) : null,
    })), { targets: appTargets(sc), zoneFrom: sc.targetService, label: "Flesch por agência, de 0 a 100, com as metas " + sc.targetInstitutional + " e " + sc.targetService, testid: "chart" }));
    nodes.push(appLegend(sc));
    if (shown.length < agencies.length) nodes.push(h("p", { class: "gb-muted gb-small" }, "+" + (agencies.length - shown.length) + " agências no ranking completo"));
  } else {
    nodes.push(domState(sc.status === "unavailable" ? "unavailable" : "empty", "Legibilidade indisponível",
      (sc.windowNote ? sc.windowNote[0].toUpperCase() + sc.windowNote.slice(1) + "." : "Nenhuma agência com Flesch na janela.") + " Valores sem dado aparecem como —, nunca 0."));
  }
  const missing = sc.agenciesWithoutData || [];
  if (missing.length) nodes.push(h("p", { class: "gb-muted gb-small", "data-testid": "without-data" }, "Sem dado de legibilidade (" + missing.length + "): " + missing.slice(0, 6).map((r) => r.agencyName).join(", ") + (missing.length > 6 ? "…" : "")));
  if (sc.benchmark) nodes.push(h("p", { class: "gb-small" }, "Benchmark (Agência Brasil, mesma janela): ", h("strong", null, appFlesch(sc.benchmark)), " · " + (sc.benchmark.bandLabel || "")));
  const omitted = (sc.omittedWithData || 0) + (sc.omittedWithoutData || 0);
  if (omitted) nodes.push(h("p", { class: "gb-muted gb-small" }, omitted + " agências ficaram fora do payload (orçamento); ver o resumo em texto."));
  nodes.push(domNotices(sc.notices));
  const last = sc.windowShifted && sc.effectiveWindow && clickable
    ? domButton("Ver último período com dados", () => view.call(APP_TOOL, appArgs(sc.params, { date_to: sc.effectiveWindow.end }), "Carregando até " + domDate(sc.effectiveWindow.end) + "…"), "action-last-period")
    : null;
  nodes.push(appActions([appExpandButton(view), last]));
  nodes.push(appTable(sc, view));
  return nodes;
}

function appArticle(label, art, testid) {
  if (!art) return null;
  const meta = [domDate(art.publishedAt), "Flesch " + appFlesch(art) + (art.bandLabel ? " (" + art.bandLabel + ")" : "")];
  if (art.wordCount !== null && art.wordCount !== undefined) meta.push(domInt(art.wordCount) + " palavras");
  return h("li", null, h("strong", null, label + ": "), domArticleLink(art.title, art.url, testid), h("div", { class: "gb-muted gb-small" }, meta.join(" · ")));
}

function appAgency(sc, view) {
  const a = sc.agency;
  const nodes = [appHeader(sc, a.agencyName + " (" + a.agencyKey + ")")];
  const section = h("section", { "data-testid": "agency-detail" });
  section.append(h("div", { class: "rd-score" },
    h("div", null, h("div", { class: "gb-big", "data-testid": "agency-flesch" }, appFlesch(a)), h("div", { class: "gb-muted gb-small" }, a.bandLabel ? "Flesch médio · " + a.bandLabel : "Flesch indisponível")),
    h("div", { class: "gb-small" },
      h("div", null, "Gap até a meta de serviço: ", h("strong", { class: "gb-num" }, domSigned(a.gapToTarget))),
      h("div", null, "Artigos: " + domInt(a.articleCount) + " (" + domInt(a.articlesWithData) + " com Flesch)"),
      h("div", null, "Palavras por artigo: " + domInt(a.avgWordCount)))));
  const bars = [{ label: a.agencyName, value: a.flesch, display: appFlesch(a), band: a.band, testid: "cmp-agency" }];
  if (sc.benchmark && sc.benchmark.agencyKey !== a.agencyKey) {
    bars.push({ label: "Agência Brasil (benchmark)", value: sc.benchmark.flesch, display: appFlesch(sc.benchmark), band: sc.benchmark.band, testid: "cmp-benchmark" });
  }
  if (a.flesch !== null && a.flesch !== undefined) {
    section.append(svgBars(bars, { targets: appTargets(sc), zoneFrom: sc.targetService, label: "Flesch da agência contra o benchmark e as metas", testid: "chart-benchmark" }));
  }
  const articles = [appArticle("Pior", sc.worstArticle, "article-worst"), appArticle("Melhor", sc.bestArticle, "article-best")].filter(Boolean);
  if (articles.length) {
    section.append(h("div", { class: "gb-section" }, h("h3", null, "Artigos da amostra (" + domInt(sc.sampleSize) + " com Flesch)"), h("ul", { class: "rd-articles" }, articles)));
  }
  if ((sc.recommendations || []).length) {
    section.append(h("div", { class: "gb-section" }, h("h3", null, "Recomendações de estilo"), h("ol", { class: "rd-recs", "data-testid": "recommendations" }, sc.recommendations.map((r) => h("li", null, appInline(r))))));
  }
  nodes.push(section, domNotices(sc.notices));
  const back = appMemory.ranking ? domButton("Voltar ao ranking", () => view.render(appMemory.ranking), "action-back") : null;
  const ask = bridgeCan("message") && a.flesch !== null
    ? domButton("Pedir reescrita ao chat", () => {
      const worst = sc.worstArticle ? " Comece pela abertura do artigo \"" + sc.worstArticle.title + "\"." : "";
      bridgeSendMessage("Ajude a melhorar a legibilidade dos textos de " + a.agencyName + ": o Flesch médio é " + appFlesch(a) + " (" + a.bandLabel + "), e a meta para serviço ao cidadão é ≥" + domInt(sc.targetService) + ". Reescreva com frases curtas e palavras simples." + worst).catch(bridgeFail);
    }, "action-ask")
    : null;
  nodes.push(appActions([back, ask, appExpandButton(view)]));
  nodes.push(domDetailsTable("Tabela do diagnóstico", [{ label: "Métrica" }, { label: "Valor", num: true }], [
    ["Flesch médio", appFlesch(a)],
    ["Benchmark (Agência Brasil)", appFlesch(sc.benchmark)],
    ["Gap até 50", domSigned(a.gapToTarget)],
    ["Artigos (com Flesch)", domInt(a.articleCount) + " (" + domInt(a.articlesWithData) + ")"],
    ["Palavras por artigo", domInt(a.avgWordCount)],
  ]));
  return nodes;
}

function appRender(sc, view) {
  if (sc.error) {
    return [h("header", { class: "gb-head" }, h("h1", { class: "gb-title" }, "Legibilidade")), domState("param-error", "Parâmetro inválido", sc.error)];
  }
  if (sc.mode === "agency" && sc.agency) return appAgency(sc, view);
  return appRanking(sc, view);
}

domMount({
  kind: "gobus.readability",
  title: "Legibilidade por agência",
  loadingText: (args) => "Carregando legibilidade" + (args.agency_key ? " de " + args.agency_key : "") + "…",
  render: appRender,
});
