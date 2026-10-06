// ── _bridge.js ── MCP Apps (SEP-1865), JSON-RPC 2.0 raw via postMessage, protocolo 2026-01-26.
// Sem SDK: handshake ui/initialize → applyHostContext → ui/notifications/initialized;
// altura por ResizeObserver; handlers de tool-input/result/cancelled, host-context-changed
// e ui/resource-teardown. A API (tools/call, ui/message, ui/open-link,
// ui/update-model-context, ui/request-display-mode) só age se o host anunciar a capacidade.
// Nada de storage do navegador: no sandbox sem same-origin ele lança exceção.
const BRIDGE_PROTOCOL = "2026-01-26";
const BRIDGE_APP = { name: __APP_NAME__, version: __APP_VERSION__ };
const bridgeState = {
  seq: 0,
  pending: new Map(),
  handlers: {},
  ready: false,
  hostCapabilities: {},
  hostContext: {},
  hostInfo: null,
};

function bridgeSend(message) {
  window.parent.postMessage(Object.assign({ jsonrpc: "2.0" }, message), "*");
}

function bridgeRequest(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++bridgeState.seq;
    bridgeState.pending.set(id, { resolve, reject });
    bridgeSend({ id, method, params: params || {} });
  });
}

function bridgeNotify(method, params) {
  bridgeSend({ method, params: params || {} });
}

function bridgeFail(err) {
  console.error("gobus-app:", err && err.message ? err.message : err);
  const onError = bridgeState.handlers.onError;
  if (onError) {
    try { onError(err); } catch (_) { /* sem recursão */ }
  }
}

function bridgeDispatch(name, arg) {
  const fn = bridgeState.handlers[name];
  if (!fn) return;
  try {
    const out = fn(arg);
    if (out && typeof out.catch === "function") out.catch(bridgeFail);
  } catch (err) {
    bridgeFail(err);
  }
}

// Variáveis do host: só nomes --* e sem url()/expression (a CSP bloquearia e sujaria o console).
function bridgeSafeVar(key, value) {
  return /^--[A-Za-z0-9-]+$/.test(key) && typeof value === "string" && !/url\(|expression\(/i.test(value);
}

function bridgeApplyHostContext(ctx, merge) {
  if (!ctx || typeof ctx !== "object") return;
  bridgeState.hostContext = merge ? Object.assign({}, bridgeState.hostContext, ctx) : Object.assign({}, ctx);
  const root = document.documentElement;
  const vars = ctx.styles && ctx.styles.variables;
  if (vars && typeof vars === "object") {
    for (const [key, value] of Object.entries(vars)) {
      if (bridgeSafeVar(key, value)) root.style.setProperty(key, value);
    }
  }
  if (ctx.theme === "light" || ctx.theme === "dark") {
    root.dataset.theme = ctx.theme;
    root.style.colorScheme = ctx.theme;
  }
  if (typeof ctx.displayMode === "string") root.dataset.mode = ctx.displayMode;
  bridgeDispatch("onContext", bridgeState.hostContext);
}

function bridgeOnMessage(event) {
  if (event.source !== window.parent) return;
  const msg = event.data;
  if (!msg || typeof msg !== "object" || msg.jsonrpc !== "2.0") return;
  if (msg.method === undefined) {
    const waiting = bridgeState.pending.get(msg.id);
    if (!waiting) return;
    bridgeState.pending.delete(msg.id);
    if (msg.error) waiting.reject(msg.error);
    else waiting.resolve(msg.result);
    return;
  }
  const params = msg.params || {};
  switch (msg.method) {
    case "ui/notifications/tool-input":
      bridgeDispatch("onInput", params.arguments || {});
      return;
    case "ui/notifications/tool-input-partial":
      return;
    case "ui/notifications/tool-result":
      bridgeDispatch("onResult", params);
      return;
    case "ui/notifications/tool-cancelled":
      bridgeDispatch("onCancel", params.reason || "");
      return;
    case "ui/notifications/host-context-changed":
      bridgeApplyHostContext(params, true);
      return;
    case "ui/resource-teardown":
      bridgeDispatch("onTeardown", params);
      bridgeSend({ id: msg.id, result: {} });
      return;
    case "ping":
      if (msg.id !== undefined) bridgeSend({ id: msg.id, result: {} });
      return;
    default:
      if (msg.id !== undefined) {
        bridgeSend({ id: msg.id, error: { code: -32601, message: "Method not found: " + msg.method } });
      }
  }
}

// Listener antes de qualquer request: nada do host se perde.
window.addEventListener("message", bridgeOnMessage);

function bridgeObserveSize() {
  let scheduled = false;
  let lastWidth = 0;
  let lastHeight = 0;
  const measure = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      // max-content: a altura natural do conteúdo, não a do iframe (senão nunca encolhe)
      const html = document.documentElement;
      const previous = html.style.height;
      html.style.height = "max-content";
      const height = Math.ceil(html.getBoundingClientRect().height);
      html.style.height = previous;
      const width = Math.ceil(window.innerWidth);
      if (width !== lastWidth || height !== lastHeight) {
        lastWidth = width;
        lastHeight = height;
        bridgeNotify("ui/notifications/size-changed", { width, height });
      }
    });
  };
  measure();
  const observer = new ResizeObserver(measure);
  observer.observe(document.documentElement);
  observer.observe(document.body);
}

async function bridgeStart(handlers) {
  bridgeState.handlers = handlers || {};
  let result;
  try {
    result = await bridgeRequest("ui/initialize", {
      protocolVersion: BRIDGE_PROTOCOL,
      appInfo: BRIDGE_APP,
      appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] },
    });
  } catch (err) {
    bridgeFail(err);
    return;
  }
  result = result || {};
  bridgeState.hostInfo = result.hostInfo || null;
  bridgeState.hostCapabilities = result.hostCapabilities || {};
  bridgeApplyHostContext(result.hostContext || {}, false);
  bridgeState.ready = true;
  bridgeNotify("ui/notifications/initialized", {});
  bridgeObserveSize();
}

function bridgeCan(capability) {
  return Boolean(bridgeState.hostCapabilities && bridgeState.hostCapabilities[capability]);
}

function bridgeCanDisplay(mode) {
  const modes = bridgeState.hostContext.availableDisplayModes;
  return Array.isArray(modes) && modes.indexOf(mode) >= 0;
}

function bridgeRefuse(what) {
  return Promise.reject(new Error("host sem " + what));
}

function bridgeCallTool(name, args) {
  if (!bridgeCan("serverTools")) return bridgeRefuse("serverTools");
  return bridgeRequest("tools/call", { name, arguments: args || {} });
}

function bridgeSendMessage(text) {
  if (!bridgeCan("message")) return bridgeRefuse("message");
  return bridgeRequest("ui/message", { role: "user", content: [{ type: "text", text: String(text) }] });
}

function bridgeOpenLink(url) {
  if (!bridgeCan("openLinks")) return bridgeRefuse("openLinks");
  if (!domIsHttps(url)) return Promise.reject(new Error("link não https"));
  return bridgeRequest("ui/open-link", { url });
}

function bridgeUpdateModelContext(text) {
  if (!bridgeCan("updateModelContext")) return bridgeRefuse("updateModelContext");
  return bridgeRequest("ui/update-model-context", { content: [{ type: "text", text: String(text) }] });
}

async function bridgeRequestDisplayMode(mode) {
  if (!bridgeCanDisplay(mode)) throw new Error("modo " + mode + " indisponível no host");
  const result = (await bridgeRequest("ui/request-display-mode", { mode })) || {};
  if (typeof result.mode === "string") document.documentElement.dataset.mode = result.mode;
  return result;
}
