// Dev harness: same panel, but talks to the backend directly from the page.
// Usage: http://localhost:5173/?token=<token from backend>
import { createRoot } from "react-dom/client";
import { App } from "../panel/App";
import panelCss from "../panel/panel.css?inline";
import { BackendClient } from "../shared/backendClient";
import { localStore } from "../shared/storage";
import { PanelRelay, type PanelTransport } from "../shared/transport";

const params = new URLSearchParams(location.search);
const token = params.get("token") ?? localStorage.getItem("copilot.devToken") ?? "";
if (params.get("token")) localStorage.setItem("copilot.devToken", token);
const url = params.get("backend") ?? "http://127.0.0.1:8765";

const relay = new PanelRelay();
const client = new BackendClient({
  onMessage: (msg) => relay.push({ kind: "msg", msg }),
  onState: (conn, detail) => relay.push({ kind: "conn", conn, detail }),
});

const transport: PanelTransport = {
  subscribe: (cb) => relay.subscribe(cb),
  openOptions() {
    const t = prompt("Backend-token:", token);
    if (t != null) location.search = `?token=${encodeURIComponent(t)}`;
  },
};

const host = document.getElementById("root")!;
const shadow = host.attachShadow({ mode: "open" });
const style = document.createElement("style");
style.textContent = panelCss;
shadow.appendChild(style);
const container = document.createElement("div");
shadow.appendChild(container);
createRoot(container).render(<App transport={transport} store={localStore} />);
client.start({ url, token });
