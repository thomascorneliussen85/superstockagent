var T = Object.defineProperty;
var M = (e, t, n) => t in e ? T(e, t, { enumerable: !0, configurable: !0, writable: !0, value: n }) : e[t] = n;
var i = (e, t, n) => M(e, typeof t != "symbol" ? t + "" : t, n);
const b = /* @__PURE__ */ new Set([
  "hello",
  "status",
  "heartbeat",
  "symbol",
  "tick",
  "candle",
  "candles",
  "analysis",
  "ai",
  "ai_status",
  "account",
  "coach",
  "trade_feedback",
  "replay",
  "replay_state",
  "pong",
  "error"
]);
function A(e) {
  try {
    const t = JSON.parse(e);
    if (t && typeof t == "object" && typeof t.type == "string" && b.has(t.type) && "data" in t)
      return t;
  } catch {
  }
  return null;
}
const _ = 2e4, E = 45e3, L = 3e4, v = 4401;
function N(e) {
  const t = new URL(e);
  if (!["127.0.0.1", "localhost", "[::1]"].includes(t.hostname))
    throw new Error("Backend URL must point to localhost (127.0.0.1)");
  return t.protocol = t.protocol === "https:" ? "wss:" : "ws:", t.pathname = "/ws", t.search = "", t.toString();
}
function D(e, t = 1e3, n = 3e4) {
  const s = Math.min(n, t * 2 ** Math.max(0, e));
  return Math.round(s * (0.8 + Math.random() * 0.4));
}
class O {
  constructor(t, n = WebSocket) {
    i(this, "ws", null);
    i(this, "cfg", null);
    i(this, "attempt", 0);
    i(this, "reconnectTimer", null);
    i(this, "pingTimer", null);
    i(this, "lastMessageAt", 0);
    i(this, "stopped", !0);
    i(this, "state", "idle");
    this.events = t, this.WS = n;
  }
  start(t) {
    if (this.stop(), this.cfg = t, this.stopped = !1, this.attempt = 0, !t.token) {
      this.setState("unauthorized", "Mangler token – åpne innstillingene");
      return;
    }
    this.connect();
  }
  stop() {
    this.stopped = !0, this.clearTimers(), this.ws && (this.ws.onclose = null, this.ws.close(1e3), this.ws = null), this.setState("idle");
  }
  /** Reconnect immediately (e.g. when a panel becomes visible). */
  kick() {
    !this.stopped && (this.state === "error" || this.state === "idle") && !this.ws && (this.clearTimers(), this.connect());
  }
  setState(t, n) {
    this.state = t, this.events.onState(t, n);
  }
  clearTimers() {
    this.reconnectTimer && clearTimeout(this.reconnectTimer), this.pingTimer && clearInterval(this.pingTimer), this.reconnectTimer = null, this.pingTimer = null;
  }
  send(t) {
    var n;
    return ((n = this.ws) == null ? void 0 : n.readyState) !== this.WS.OPEN ? !1 : (this.ws.send(JSON.stringify(t)), !0);
  }
  /** Send an application message (not auth/ping). Returns false when not connected. */
  request(t) {
    return this.state === "connected" && this.send(t);
  }
  connect() {
    if (!this.cfg) return;
    let t;
    try {
      t = N(this.cfg.url);
    } catch (s) {
      this.setState("error", s.message);
      return;
    }
    this.setState("connecting");
    const n = new this.WS(t);
    this.ws = n, n.onopen = () => {
      this.setState("authenticating"), this.send({ type: "auth", token: this.cfg.token });
    }, n.onmessage = (s) => {
      this.lastMessageAt = Date.now();
      const a = A(String(s.data));
      a && (a.type === "hello" && (this.attempt = 0, this.setState("connected"), this.startPing()), this.events.onMessage(a));
    }, n.onerror = () => {
    }, n.onclose = (s) => {
      if (this.ws = null, this.clearTimers(), !this.stopped) {
        if (s.code === v) {
          this.setState("unauthorized", "Ugyldig token"), this.schedule(L);
          return;
        }
        this.setState("error", s.code === 1008 ? "Origin avvist av backend" : "Ingen kontakt med backend"), this.schedule(D(this.attempt++));
      }
    };
  }
  schedule(t) {
    this.reconnectTimer = setTimeout(() => this.connect(), t);
  }
  startPing() {
    this.pingTimer = setInterval(() => {
      var t;
      if (Date.now() - this.lastMessageAt > E) {
        (t = this.ws) == null || t.close(4e3);
        return;
      }
      this.send({ type: "ping", t: Date.now() });
    }, _);
  }
}
const f = 500, d = () => ({
  hello: null,
  status: null,
  statusAt: null,
  symbol: null,
  tick: null,
  tickAt: null,
  candles: { "1m": [], "5m": [], "15m": [], "1h": [] },
  analysis: null,
  analysisAt: null,
  ai: null,
  aiStatus: null,
  account: null,
  coach: null,
  feedback: null
});
function U(e, t, n = f) {
  const s = e[e.length - 1];
  if (s && s.t === t.t) return [...e.slice(0, -1), t];
  if (s && t.t < s.t) {
    const l = e.findIndex((w) => w.t === t.t);
    if (l === -1) return e;
    const h = e.slice();
    return h[l] = t, h;
  }
  const a = [...e, t];
  return a.length > n ? a.slice(a.length - n) : a;
}
function C(e, t, n) {
  switch (t.type) {
    case "hello":
      return { ...d(), hello: t.data };
    case "status":
    case "heartbeat":
      return { ...e, status: t.data, statusAt: n };
    case "symbol":
      return { ...e, symbol: t.data };
    case "tick":
      return { ...e, tick: t.data, tickAt: n };
    case "candle": {
      const s = t.data.tf;
      return { ...e, candles: { ...e.candles, [s]: U(e.candles[s], t.data) } };
    }
    case "analysis":
      return { ...e, analysis: t.data, analysisAt: n };
    case "ai":
      return { ...e, ai: t.data };
    case "ai_status":
      return { ...e, aiStatus: t.data };
    case "account":
      return { ...e, account: t.data };
    case "coach":
      return { ...e, coach: t.data };
    case "trade_feedback":
      return { ...e, feedback: t.data };
    case "candles": {
      const s = [...t.data.candles].sort((a, l) => a.t - l.t).slice(-f);
      return { ...e, candles: { ...e.candles, [t.data.tf]: s } };
    }
    default:
      return e;
  }
}
const I = {
  async get(e) {
    return (await chrome.storage.local.get(e))[e];
  },
  async set(e, t) {
    await chrome.storage.local.set({ [e]: t });
  }
}, k = {
  backend: "copilot.backend"
}, R = { url: "http://127.0.0.1:8765", token: "" }, W = "copilot-panel", r = /* @__PURE__ */ new Set();
let c = d(), m = "idle", g, u = null;
function p(e) {
  for (const t of r)
    try {
      t.postMessage(e);
    } catch {
      r.delete(t);
    }
}
const o = new O({
  onMessage(e) {
    c = C(c, e, Date.now()), p({ kind: "msg", msg: e });
  },
  onState(e, t) {
    m = e, g = t, p({ kind: "conn", conn: e, detail: t });
  }
});
async function S() {
  return { ...R, ...await I.get(k.backend) ?? {} };
}
async function P() {
  u && (clearTimeout(u), u = null), o.state === "idle" ? o.start(await S()) : o.kick();
}
chrome.runtime.onConnect.addListener((e) => {
  e.name === W && (r.add(e), e.postMessage({ kind: "snapshot", conn: m, detail: g, market: c }), P(), e.onMessage.addListener((t) => {
    var n;
    (t == null ? void 0 : t.kind) === "client" && ((n = t.msg) == null ? void 0 : n.type) === "ai_request" && o.request(t.msg);
  }), e.onDisconnect.addListener(() => {
    r.delete(e), r.size === 0 && (u = setTimeout(() => {
      o.stop(), c = d();
    }, 6e4));
  }));
});
chrome.runtime.onMessage.addListener((e, t, n) => ((e == null ? void 0 : e.kind) === "open-page" && ["journal", "replay", "chart"].includes(e.page) && (chrome.tabs.create({ url: chrome.runtime.getURL(`${e.page}/${e.page}.html`) }), n({ ok: !0 })), (e == null ? void 0 : e.kind) === "open-options" && (chrome.runtime.openOptionsPage(), n({ ok: !0 })), !1));
chrome.storage.onChanged.addListener((e, t) => {
  t === "local" && e[k.backend] && r.size > 0 && (c = d(), S().then((n) => o.start(n)));
});
chrome.commands.onCommand.addListener((e) => {
  e === "toggle-panel" && y({ kind: "toggle" });
});
chrome.action.onClicked.addListener(() => y({ kind: "toggle" }));
function y(e) {
  chrome.tabs.query({ active: !0, currentWindow: !0 }, ([t]) => {
    var n, s;
    if (t != null && t.id)
      for (const a of r) ((s = (n = a.sender) == null ? void 0 : n.tab) == null ? void 0 : s.id) === t.id && a.postMessage(e);
  });
}
