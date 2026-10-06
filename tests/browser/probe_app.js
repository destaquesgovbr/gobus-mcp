// App de sonda (só nos testes): mostra no DOM o que o bridge entrega e expõe a API do
// bridge em botões, para os testes acionarem pelo iframe.
const probeRoot = document.getElementById("app");

function probeSet(id, value) {
  let el = probeRoot.querySelector('[data-testid="' + id + '"]');
  if (!el) {
    el = h("pre", { "data-testid": id });
    probeRoot.append(el);
  }
  el.textContent = typeof value === "string" ? value : JSON.stringify(value);
}

async function probeRun(id, fn) {
  try {
    probeSet(id, (await fn()) || "ok");
  } catch (err) {
    probeSet(id, "erro: " + (err && err.message ? err.message : JSON.stringify(err)));
  }
}

function probeButton(id, label, fn) {
  probeRoot.append(
    h("button", { type: "button", "data-testid": id, onclick: () => probeRun(id + "-out", fn) }, label),
  );
}

domClear(probeRoot);
probeRoot.dataset.state = "ok";
probeButton("call", "callTool", () => bridgeCallTool("gobus_probe", { x: 1 }));
probeButton("message", "sendMessage", () => bridgeSendMessage("olá"));
probeButton("link-https", "openLink https", () => bridgeOpenLink("https://www.gov.br/x"));
probeButton("link-http", "openLink http", () => bridgeOpenLink("http://www.gov.br/x"));
probeButton("context", "updateModelContext", () => bridgeUpdateModelContext("contexto"));
probeButton("fullscreen", "fullscreen", () => bridgeRequestDisplayMode("fullscreen"));
probeButton("grow", "crescer", () => {
  probeRoot.append(h("div", { "data-testid": "tall", style: { height: "600px" } }, "alto"));
  return "ok";
});
probeButton("caps", "capacidades", () =>
  JSON.stringify({ tools: bridgeCan("serverTools"), full: bridgeCanDisplay("fullscreen") }),
);

bridgeStart({
  onInput: (args) => probeSet("input", args),
  onResult: (result) => probeSet("result", result),
  onCancel: (reason) => probeSet("cancelled", reason || ""),
  onContext: (ctx) => probeSet("context-theme", ctx.theme || ""),
  onTeardown: () => probeSet("teardown", "ok"),
});
