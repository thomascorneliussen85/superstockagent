// MV3 service worker. Owns the single WebSocket to the local backend and
// relays data to every TradingView tab's panel through runtime Ports.
//
// Why here and not in the content script: requests from content scripts are
// subject to TradingView's Content-Security-Policy and carry the page's
// origin. The service worker has the extension origin
// (chrome-extension://<id>), which the backend validates.
import { BackendClient, type BackendConfig } from "../shared/backendClient";
import { emptyMarketState, reduceMarket, type MarketState } from "../shared/marketState";
import type { ConnState } from "../shared/protocol";
import { DEFAULT_BACKEND, KEYS, chromeStore } from "../shared/storage";
import { PORT_NAME, type PanelEvent, type PortRequest } from "../shared/transport";

const ports = new Set<chrome.runtime.Port>();
let market: MarketState = emptyMarketState();
let conn: ConnState = "idle";
let connDetail: string | undefined;
let idleStopTimer: ReturnType<typeof setTimeout> | null = null;

function broadcast(ev: PanelEvent) {
  for (const p of ports) {
    try {
      p.postMessage(ev);
    } catch {
      ports.delete(p);
    }
  }
}

const client = new BackendClient({
  onMessage(msg) {
    market = reduceMarket(market, msg, Date.now());
    broadcast({ kind: "msg", msg });
  },
  onState(state, detail) {
    conn = state;
    connDetail = detail;
    broadcast({ kind: "conn", conn: state, detail });
  },
});

async function loadConfig(): Promise<BackendConfig> {
  return { ...DEFAULT_BACKEND, ...((await chromeStore.get<BackendConfig>(KEYS.backend)) ?? {}) };
}

async function ensureRunning() {
  if (idleStopTimer) {
    clearTimeout(idleStopTimer);
    idleStopTimer = null;
  }
  if (client.state === "idle") client.start(await loadConfig());
  else client.kick();
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PORT_NAME) return;
  ports.add(port);
  port.postMessage({ kind: "snapshot", conn, detail: connDetail, market } satisfies PanelEvent);
  void ensureRunning();
  port.onMessage.addListener((req: PortRequest) => {
    if (req?.kind === "client" && req.msg?.type === "ai_request") client.request(req.msg);
  });
  port.onDisconnect.addListener(() => {
    ports.delete(port);
    if (ports.size === 0) {
      // No TradingView tabs open: release the connection after a grace period.
      idleStopTimer = setTimeout(() => {
        client.stop();
        market = emptyMarketState();
      }, 60_000);
    }
  });
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.kind === "open-page" && ["journal", "replay"].includes(msg.page)) {
    void chrome.tabs.create({ url: chrome.runtime.getURL(`${msg.page}/${msg.page}.html`) });
    sendResponse({ ok: true });
  }
  if (msg?.kind === "open-options") {
    void chrome.runtime.openOptionsPage();
    sendResponse({ ok: true });
  }
  return false;
});

// Restart the connection whenever the user saves new settings.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[KEYS.backend] && ports.size > 0) {
    market = emptyMarketState();
    void loadConfig().then((cfg) => client.start(cfg));
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-panel") broadcastToActiveTab({ kind: "toggle" });
});

chrome.action.onClicked.addListener(() => broadcastToActiveTab({ kind: "toggle" }));

function broadcastToActiveTab(ev: PanelEvent) {
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab?.id) return;
    for (const p of ports) if (p.sender?.tab?.id === tab.id) p.postMessage(ev);
  });
}
