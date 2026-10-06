// ── _svg.js ── gráficos em SVG à mão (createElementNS), desenhados na largura real do
// container (re-render quando a largura muda). Todo gráfico tem role="img" e <title>; a
// tabela equivalente fica em <details> (domDetailsTable). Cores vêm de classes CSS.
const SVG_NS = "http://www.w3.org/2000/svg";
const SVG_CHAR_PX = 6.6; // largura média de um caractere a 12px (para truncar rótulos)

function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.slice(0, 2) === "on") {
      if (typeof value !== "function") throw new Error("handler precisa ser função: " + key);
      el.addEventListener(key.slice(2), value);
    } else if (DOM_BLOCKED_ATTRS.has(key)) {
      throw new Error("atributo bloqueado: " + key);
    } else {
      el.setAttribute(key, String(value));
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function svgFit(text, maxPx) {
  const value = String(text);
  const max = Math.max(4, Math.floor(maxPx / SVG_CHAR_PX));
  return value.length <= max ? value : value.slice(0, max - 1) + "…";
}

function svgRoot(width, height, label, testid) {
  return s("svg", {
    class: "gb-chart", viewBox: "0 0 " + width + " " + height, width, height,
    role: "img", "aria-label": label, "data-testid": testid || null,
  }, s("title", null, label));
}

function svgWidth(fallback) {
  const app = document.getElementById("app");
  const style = app ? getComputedStyle(app) : null;
  const pad = style ? parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) : 32;
  const width = app ? app.clientWidth - pad : 0;
  return Math.max(200, Math.floor(width || fallback || 560));
}

// Barras horizontais 0..max. rows: [{label, value|null, display, band, title, testid, onClick}].
// opts: {width, max, targets: [{value, label}], zoneFrom, label, testid}.
function svgBars(rows, opts) {
  const o = Object.assign({ max: 100, targets: [], rowHeight: 34, width: svgWidth() }, opts || {});
  const W = o.width;
  const top = 4;
  const axis = 18;
  const H = top + rows.length * o.rowHeight + axis;
  const x = (v) => Math.max(0, Math.min(W, (W * v) / o.max));
  const svg = svgRoot(W, H, o.label || "Gráfico de barras", o.testid);
  const plotTop = top;
  const plotBottom = top + rows.length * o.rowHeight;
  if (o.zoneFrom !== undefined && o.zoneFrom !== null) {
    svg.append(s("rect", { class: "gb-target-zone", x: x(o.zoneFrom), y: plotTop, width: W - x(o.zoneFrom), height: plotBottom - plotTop }));
  }
  rows.forEach((row, i) => {
    const y = top + i * o.rowHeight;
    const valueText = row.display !== undefined ? row.display : domNumber(row.value);
    const valueWidth = String(valueText).length * SVG_CHAR_PX + 8;
    const g = s("g", {
      class: row.onClick ? "gb-bar-row" : null, "data-testid": row.testid || null,
      onclick: row.onClick || null,
    }, s("title", null, row.title || row.label + ": " + valueText));
    g.append(
      s("text", { x: 0, y: y + 12 }, svgFit(row.label, W - valueWidth)),
      s("text", { x: W, y: y + 12, "text-anchor": "end", class: row.value === null ? "gb-axis" : null }, valueText),
      s("rect", { class: "gb-track", x: 0, y: y + 17, width: W, height: 10, rx: 3 }),
    );
    if (row.value !== null && row.value !== undefined) {
      g.append(s("rect", { class: "gb-bar", "data-band": row.band || null, x: 0, y: y + 17, width: Math.max(row.value > 0 ? 2 : 0, x(row.value)), height: 10, rx: 3 }));
    }
    svg.append(g);
  });
  for (const t of o.targets) {
    svg.append(s("line", { class: "gb-target", x1: x(t.value), x2: x(t.value), y1: plotTop, y2: plotBottom + 2 }));
  }
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * o.max);
  for (const tick of ticks) {
    const anchor = tick === 0 ? "start" : tick === o.max ? "end" : "middle";
    const target = o.targets.find((t) => t.value === tick);
    svg.append(s("text", { class: "gb-axis", x: x(tick), y: H - 3, "text-anchor": anchor }, target && target.label ? target.label : domInt(tick)));
  }
  return svg;
}
