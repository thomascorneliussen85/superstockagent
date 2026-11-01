// Content script: mounts the panel inside a closed-off Shadow DOM so neither
// TradingView's CSS nor ours leak across. Does not read or modify the chart.
import { createRoot } from "react-dom/client";
import { App } from "../panel/App";
import panelCss from "../panel/panel.css?inline";
import { chromeStore } from "../shared/storage";
import { PORT_NAME, PanelRelay, type PanelEvent, type PanelTransport } from "../shared/transport";

const HOST_ID = "ai-trading-copilot-root";

function createPortTransport(): PanelTransport {
  const relay = new PanelRelay();
  let retry = 500;

  const connect = () => {
    if (!chrome.runtime?.id) return; // extension reloaded/removed: context invalidated
    const port = chrome.runtime.connect({ name: PORT_NAME });
    port.onMessage.addListener((ev: PanelEvent) => {
      retry = 500;
      relay.push(ev);
    });
    // The MV3 worker can be suspended; reconnect to wake it.
    port.onDisconnect.addListener(() => {
      relay.push({ kind: "conn", conn: "connecting", detail: "Kobler til bakgrunnstjeneste…" });
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 10_000);
    });
  };
  connect();

  return {
    subscribe: (cb) => relay.subscribe(cb),
    openOptions() {
      void chrome.runtime.sendMessage({ kind: "open-options" });
    },
  };
}

function mount() {
  if (document.getElementById(HOST_ID)) return;
  const host = document.createElement("div");
  host.id = HOST_ID;
  // Zero-size fixed host; the panel inside positions itself.
  host.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;z-index:2147483000;";
  document.documentElement.appendChild(host);
  const shadow = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = panelCss;
  shadow.appendChild(style);
  const container = document.createElement("div");
  shadow.appendChild(container);
  createRoot(container).render(<App transport={createPortTransport()} store={chromeStore} />);
}

mount();
