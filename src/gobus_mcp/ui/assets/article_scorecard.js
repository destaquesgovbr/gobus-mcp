// ── article_scorecard.js ── ui://article-scorecard ← gobus_score_article(unique_id, compare_with)
// Nota 0–10 com 3 semáforos (ícone + texto; as cores e os limiares vêm do payload),
// benchmark da agência e da Agência Brasil, comparação lado a lado pela mesma tool
// (compare_with) e pedido de reescrita ao chat. Nota recusada nunca vira número.
const APP_TOOL = "gobus_score_article";
const APP_ICONS = { green: "✓", yellow: "!", red: "✕", gray: "–" };
const APP_STATUS = {
  scored: ["Nota completa", "ok"],
  partial: ["Nota parcial (sem benchmark de concisão)", "warn"],
  refused: ["Nota recusada", "error"],
};

function appScore(value) {
  return value === null || value === undefined ? DOM_DASH : domNumber(value) + "/10";
}

function appLight(light, label) {
  return h("span", { class: "gb-light", "data-light": light || "gray", role: "img", "aria-label": label }, APP_ICONS[light] || APP_ICONS.gray);
}

function appBand(bands, value) {
  if (value === null || value === undefined) return null;
  const list = bands || [];
  const found = list.find((b) => value >= b.lower && value < b.upper);
  return found ? found.key : list.length ? list[list.length - 1].key : null;
}

function appFlesch(article) {
  if (article.flesch === null || article.flesch === undefined) return DOM_DASH;
  let text = domNumber(article.flesch);
  if (article.fleschRaw !== null && article.fleschRaw !== undefined && Math.abs(article.fleschRaw - article.flesch) >= 0.05) {
    text += " (bruto " + domNumber(article.fleschRaw) + ")";
  }
  return text;
}

function appDims(dimensions, prefix) {
  return h("ul", { class: "sc-dims" }, dimensions.map((d) => h("li", { class: "sc-dim", "data-testid": prefix + d.key },
    appLight(d.light, d.label + ": " + (d.score === null ? "indisponível" : appScore(d.score))),
    h("div", null,
      h("div", null, h("strong", null, d.label), " · ", h("span", { class: "gb-num" }, d.score === null ? "indisponível" : appScore(d.score)),
        h("span", { class: "gb-muted gb-small" }, " · peso " + domInt(d.weight * 100) + "%")),
      h("div", { class: "gb-muted gb-small" }, d.detail)))));
}

function appStatusChip(status) {
  const [label, tone] = APP_STATUS[status] || [status, null];
  return domChip(label, tone, "chip-status");
}

function appOverall(sc, testid) {
  return h("div", { class: "sc-overall" },
    appLight(sc.overallLight, "Nota geral"),
    h("span", { class: "gb-big", "data-testid": testid || null }, appScore(sc.overall)));
}

function appBenchmark(sc) {
  const own = sc.benchmark;
  const ref = sc.referenceBenchmark;
  const art = sc.article;
  const rows = [{ label: "Este artigo", value: art.flesch, display: appFlesch(art), band: appBand(sc.bands, art.flesch), testid: "bm-article" }];
  if (own) rows.push({ label: "Mediana de " + own.agencyName, value: own.medianFlesch, display: domNumber(own.medianFlesch), band: appBand(sc.bands, own.medianFlesch), testid: "bm-agency" });
  if (ref && (!own || ref.agencyKey !== own.agencyKey)) rows.push({ label: "Mediana de " + ref.agencyName, value: ref.medianFlesch, display: domNumber(ref.medianFlesch), band: appBand(sc.bands, ref.medianFlesch), testid: "bm-reference" });
  const nodes = [h("h3", null, "Benchmark (90 dias antes da publicação)")];
  if (rows.some((r) => r.value !== null && r.value !== undefined)) {
    const targets = [{ value: sc.targetInstitutional, label: domInt(sc.targetInstitutional) }, { value: sc.targetService, label: domInt(sc.targetService) + " meta" }];
    nodes.push(svgBars(rows, { targets, zoneFrom: sc.targetService, label: "Flesch do artigo contra as medianas do benchmark", testid: "chart-benchmark" }));
  }
  const words = ["Palavras: " + domInt(art.wordCount)];
  if (own) words.push("mediana da agência " + domInt(own.medianWordCount));
  if (ref) words.push(ref.agencyName + " " + domInt(ref.medianWordCount));
  nodes.push(h("p", { class: "gb-small" }, words.join(" · ")));
  const sample = (b) => (b ? b.agencyName + ": " + domInt(b.sampleSize) + " artigos com palavras, " + domInt(b.fleschSampleSize) + " com Flesch" + (b.window ? " (" + domDate(b.window.start) + "–" + domDate(b.window.end) + ")" : "") : null);
  nodes.push(h("p", { class: "gb-muted gb-small" }, [sample(own), sample(ref)].filter(Boolean).join(" · ") || "Sem amostra de benchmark."));
  return h("section", { class: "gb-section", "data-testid": "benchmark" }, nodes);
}

function appSide(key, label, part) {
  const art = part.article;
  return h("article", { class: "sc-side", "data-testid": "side-" + key },
    h("p", { class: "gb-muted gb-small" }, label),
    h("h3", { class: "sc-side-title" }, domArticleLink(art.title, art.url, null)),
    h("p", { class: "gb-sub" }, art.agencyName + " · " + domDate(art.publishedAt)),
    h("div", { class: "gb-row" }, appOverall(part, null), appStatusChip(part.scoreStatus)),
    part.refusalReason ? h("p", { class: "gb-muted gb-small" }, "Nota recusada: " + part.refusalReason) : null,
    appDims(part.dimensions, "cmp-" + key + "-"));
}

async function appCompare(view, sc, suggestion) {
  await view.call(APP_TOOL, { unique_id: sc.article.uniqueId, compare_with: suggestion.uniqueId }, "Comparando com " + suggestion.title + "…");
  const now = view.result && view.result.structuredContent;
  if (now && now.comparison && bridgeCan("updateModelContext")) {
    const a = now.article;
    const b = now.comparison.article;
    bridgeUpdateModelContext("No scorecard, o usuário comparou \"" + a.title + "\" (" + appScore(now.overall) + ") com \"" + b.title + "\" (" + appScore(now.comparison.overall) + ").").catch(() => {});
  }
}

function appRewrite(sc) {
  const art = sc.article;
  const conc = sc.dimensions.find((d) => d.key === "conciseness");
  return "Reescreva o artigo \"" + art.title + "\" (" + art.uniqueId + ", " + art.agencyName + ") para melhorar a legibilidade: nota " + appScore(sc.overall) + ", Flesch " + appFlesch(art) + ", " + (conc ? conc.detail : domInt(art.wordCount) + " palavras") + ". Mantenha os fatos; use frases curtas, palavras simples e voz ativa.";
}

function appRender(sc, view) {
  const art = sc.article;
  const full = document.documentElement.dataset.mode === "fullscreen";
  const nodes = [
    h("header", { class: "gb-head" },
      h("div", null,
        h("h1", { class: "gb-title" }, domArticleLink(art.title, art.url, "article-link")),
        h("p", { class: "gb-sub" }, art.agencyName + " (" + art.agencyKey + ") · " + domDate(art.publishedAt)))),
  ];
  if (sc.comparison) {
    nodes.push(h("section", { class: "sc-compare", "data-testid": "compare" },
      appSide("a", "Este artigo", { article: art, overall: sc.overall, overallLight: sc.overallLight, scoreStatus: sc.scoreStatus, refusalReason: sc.refusalReason, dimensions: sc.dimensions }),
      appSide("b", "Comparado", sc.comparison)));
  } else {
    nodes.push(h("div", { class: "gb-row sc-top" }, appOverall(sc, "overall"), appStatusChip(sc.scoreStatus)));
    if (sc.scoreStatus === "refused") nodes.push(domState("refused", "Nota recusada", sc.refusalReason + ". Nada de nota neutra inventada."));
    nodes.push(appDims(sc.dimensions, "dim-"));
  }
  nodes.push(appBenchmark(sc));
  const extra = sc.comparisonError ? ["Comparação indisponível: " + sc.comparisonError] : [];
  nodes.push(domNotices(sc.notices, extra));
  const suggestions = sc.suggestedComparisons || [];
  const canCall = bridgeCan("serverTools");
  if (full && canCall && suggestions.length && !sc.comparison) {
    nodes.push(h("section", { class: "gb-section", "data-testid": "suggestions" }, h("h3", null, "Comparar com"),
      h("ul", { class: "sc-suggestions" }, suggestions.map((sug, i) => h("li", null,
        domButton(sug.title, () => appCompare(view, sc, sug), "suggestion-" + i, { class: "gb-link" }),
        h("span", { class: "gb-muted gb-small" }, " — " + sug.reason + " · Flesch " + domNumber(sug.flesch)))))));
  }
  const compare = canCall && suggestions.length && !sc.comparison && !full
    ? domButton("Comparar", () => appCompare(view, sc, suggestions[0]), "action-compare", { title: suggestions[0].title })
    : null;
  const rewrite = bridgeCan("message") && sc.scoreStatus !== "refused"
    ? domButton("Pedir reescrita", () => bridgeSendMessage(appRewrite(sc)).catch(bridgeFail), "action-rewrite")
    : null;
  const expand = !full && bridgeCanDisplay("fullscreen")
    ? domButton("Expandir", () => bridgeRequestDisplayMode("fullscreen").then(() => view.refresh()).catch(bridgeFail), "action-expand")
    : null;
  const actions = [compare, rewrite, expand].filter(Boolean);
  if (actions.length) nodes.push(h("div", { class: "gb-actions" }, actions));
  nodes.push(domDetailsTable("Tabela das dimensões", [{ label: "Dimensão" }, { label: "Nota", num: true }, { label: "Peso efetivo", num: true }, { label: "Detalhe" }],
    sc.dimensions.map((d) => [d.label, d.score === null ? "indisponível" : appScore(d.score), d.effectiveWeight === null ? DOM_DASH : domInt(d.effectiveWeight * 100) + "%", d.detail])));
  return nodes;
}

domMount({
  kind: "gobus.scorecard",
  title: "Score editorial",
  loadingText: (args) => "Calculando a nota" + (args.unique_id ? " de " + args.unique_id : "") + "…",
  render: appRender,
});
