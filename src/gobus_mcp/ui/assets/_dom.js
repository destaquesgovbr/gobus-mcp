// ── _dom.js ── DOM só com createElement/textContent (nada de HTML em string), formatação
// pt-BR e peças comuns dos apps (estados, chips, avisos, botões, tabela em <details>).
const DOM_BLOCKED_ATTRS = new Set(["src", "href", "srcdoc", "action", "formaction", "xlink:href"]);

function domSetAttrs(el, attrs) {
  if (!attrs) return;
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "text") el.textContent = String(value);
    else if (key === "style") {
      for (const [prop, v] of Object.entries(value)) el.style.setProperty(prop, String(v));
    } else if (key.slice(0, 2) === "on") {
      if (typeof value !== "function") throw new Error("handler precisa ser função: " + key);
      el.addEventListener(key.slice(2), value);
    } else if (DOM_BLOCKED_ATTRS.has(key)) {
      throw new Error("atributo bloqueado: " + key);
    } else {
      el.setAttribute(key, value === true ? "" : String(value));
    }
  }
}

function domAppend(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  domSetAttrs(el, attrs);
  return domAppend(el, children);
}

function domClear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

// ── formatação ──────────────────────────────────────────────────────────────
const DOM_DASH = "—";
const domFormats = new Map();

function domNumber(value, digits) {
  if (value === null || value === undefined || Number.isNaN(value)) return DOM_DASH;
  const d = digits === undefined ? 1 : digits;
  if (value === 0) value = 0; // -0 vira 0 (nada de "-0,0")
  if (!domFormats.has(d)) {
    domFormats.set(d, new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }));
  }
  return domFormats.get(d).format(value);
}

function domSigned(value, digits) {
  if (value === null || value === undefined) return DOM_DASH;
  return (value > 0 ? "+" : "") + domNumber(value, digits);
}

function domInt(value) {
  return domNumber(value, 0);
}

// "2026-06-30" (dia) ou ISO com hora (convertido para BRT) → "30/06/2026".
const domDateFmt = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric",
});
function domDate(value) {
  if (!value) return DOM_DASH;
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (day) return day[3] + "/" + day[2] + "/" + day[1];
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? DOM_DASH : domDateFmt.format(parsed);
}

function domSpan(range) {
  if (!range) return DOM_DASH;
  return domDate(range.start) + "–" + domDate(range.end) + " (" + range.days + " dias)";
}

function domIsHttps(url) {
  try {
    return new URL(String(url)).protocol === "https:";
  } catch (_) {
    return false;
  }
}

// ── peças comuns ────────────────────────────────────────────────────────────
function domChip(text, tone, testid) {
  return h("span", { class: "gb-chip", "data-tone": tone || null, "data-testid": testid || null }, text);
}

function domButton(label, onClick, testid, extra) {
  return h("button", Object.assign({ type: "button", class: "gb-btn", "data-testid": testid || null, onclick: onClick }, extra || {}), label);
}

// Controle segmentado (opções exclusivas): options = [{value, label}]; a atual fica com
// aria-pressed="true" e não dispara de novo.
function domSegment(options, current, onSelect, testidPrefix, label) {
  return h("div", { class: "gb-segment", role: "group", "aria-label": label || null },
    options.map((o) => h("button", {
      type: "button", class: "gb-btn", "aria-pressed": String(o.value === current),
      "data-testid": testidPrefix + o.value,
      onclick: () => { if (o.value !== current) onSelect(o.value); },
    }, o.label)));
}

// Botão de ação pelo host (ui/message, display mode…): se o host recusar, o botão some.
function domAction(label, run, testid) {
  const button = domButton(label, () => {
    Promise.resolve().then(run).catch((err) => {
      bridgeWarn(err);
      button.hidden = true;
    });
  }, testid);
  return button;
}

// Link de artigo: abre pelo host (ui/open-link) quando ele permite; senão, só o texto.
function domArticleLink(title, url, testid) {
  if (url && domIsHttps(url) && bridgeCan("openLinks")) {
    return h("button", { type: "button", class: "gb-link", "data-testid": testid || null, title: url, onclick: () => bridgeOpenLink(url).catch(bridgeWarn) }, title);
  }
  return h("span", { "data-testid": testid || null }, title);
}

const DOM_SEVERITY_TONE = { info: "info", warn: "warn", error: "error" };
function domNotices(notices, extra) {
  const items = (notices || []).map((n) =>
    h("li", { class: "gb-notice", "data-tone": DOM_SEVERITY_TONE[n.severity] || null, "data-code": n.code || null }, n.message),
  );
  for (const text of extra || []) items.push(h("li", { class: "gb-notice", "data-tone": "warn" }, text));
  return items.length ? h("ul", { class: "gb-notices", "data-testid": "notices" }, items) : null;
}

function domState(kind, title, message) {
  return h("section", { class: "gb-state", "data-tone": kind === "error" ? "error" : null, "data-testid": "state-" + kind },
    h("h2", null, title), message ? h("p", null, message) : null);
}

// Tabela equivalente a um gráfico (acessibilidade e leitura exata), recolhida em <details>.
function domDetailsTable(summary, headers, rows, testid) {
  const head = h("tr", null, headers.map((col) => h("th", { scope: "col", class: col.num ? "gb-num" : null }, col.label)));
  const body = rows.map((row) => h("tr", null, row.map((cell, i) => h("td", { class: headers[i] && headers[i].num ? "gb-num" : null }, cell))));
  return h("details", { class: "gb-details", "data-testid": testid || "table" },
    h("summary", null, summary),
    h("div", { class: "gb-table-wrap" }, h("table", { class: "gb-table" }, h("thead", null, head), h("tbody", null, body))));
}

function domText(result) {
  const content = (result && result.content) || [];
  return content.filter((c) => c && c.type === "text").map((c) => c.text).join("\n\n");
}

// Ciclo comum dos apps: skeleton no tool-input, roteamento do tool-result (erro, sem
// structuredContent, versão incompatível) e render do payload válido.
function domMount(spec) {
  const root = document.getElementById("app");
  const view = {
    root,
    args: {},
    result: null,
    show(state, ...nodes) {
      domClear(root);
      root.dataset.state = state;
      domAppend(root, nodes);
    },
    loading(message) {
      view.show("loading", h("div", { class: "gb-skeleton", "data-testid": "skeleton" }, h("span", { class: "gb-muted" }, message || "Carregando…")));
    },
    // Re-render quando o modo (inline/fullscreen) ou a largura mudam: os gráficos são
    // desenhados na largura real e o inline mostra menos itens.
    refresh() {
      const mode = document.documentElement.dataset.mode || "inline";
      if (view.result && (mode !== view.mode || Math.abs(window.innerWidth - view.width) > 8)) view.render(view.result);
    },
    render(result) {
      view.result = result;
      view.mode = document.documentElement.dataset.mode || "inline";
      view.width = window.innerWidth;
      const data = result && result.structuredContent;
      if (result && result.isError) {
        view.show("error", domState("error", "Erro na consulta", domText(result) || "A tool devolveu erro."));
      } else if (!data || typeof data !== "object") {
        view.show("text", domState("text", spec.title, domText(result) || "Sem dados estruturados."));
      } else if (data.schemaVersion !== 1 || data.kind !== spec.kind) {
        view.show("incompatible", domState("incompatible", "Versão incompatível",
          "Este app entende " + spec.kind + " v1 e recebeu " + (data.kind || "?") + " v" + (data.schemaVersion || "?") + ". Recarregue a conversa.\n\n" + domText(result)));
      } else {
        view.show(data.status || "ok", spec.render(data, view));
      }
    },
    async call(name, args, message) {
      if (!bridgeCan("serverTools")) return;
      const previous = view.result;
      view.loading(message);
      try {
        view.render(await bridgeCallTool(name, args));
      } catch (err) {
        view.render(previous);
        domAppend(root, [domNotices([], ["Falha ao consultar: " + (err && err.message ? err.message : "erro")])]);
      }
    },
  };
  bridgeStart({
    onInput(args) {
      view.args = args || {};
      view.loading(spec.loadingText ? spec.loadingText(view.args) : "Carregando…");
    },
    onResult: (result) => view.render(result),
    onCancel(reason) {
      view.show("cancelled", domState("cancelled", "Consulta cancelada", reason || null));
    },
    onContext: () => view.refresh(),
    onError(err) {
      view.show("error", domState("error", "Erro ao exibir", err && err.message ? err.message : String(err)));
    },
  });
  let resizing = false;
  window.addEventListener("resize", () => {
    if (resizing) return;
    resizing = true;
    requestAnimationFrame(() => { resizing = false; view.refresh(); });
  });
  return view;
}
