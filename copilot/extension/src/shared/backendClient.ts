// WebSocket client for the local backend with auth handshake, keepalive,
// liveness detection and exponential-backoff reconnection.
// Runs in the background service worker (extension) or the dev harness.
import { parseServerMessage, type ClientMessage, type ConnState, type ServerMessage } from "./protocol";

export interface BackendConfig {
  url: string; // e.g. http://127.0.0.1:8765
  token: string;
}

export interface BackendClientEvents {
  onMessage(msg: ServerMessage): void;
  onState(state: ConnState, detail?: string): void;
}

export const PING_INTERVAL_MS = 20_000; // also keeps the MV3 service worker alive (Chrome >= 116)
export const LIVENESS_TIMEOUT_MS = 45_000;
const UNAUTHORIZED_RETRY_MS = 30_000;
const CLOSE_UNAUTHORIZED = 4401;

export function toWsUrl(httpUrl: string): string {
  const u = new URL(httpUrl);
  if (!["127.0.0.1", "localhost", "[::1]"].includes(u.hostname)) {
    throw new Error("Backend URL must point to localhost (127.0.0.1)");
  }
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = "/ws";
  u.search = "";
  return u.toString();
}

export function backoffMs(attempt: number, base = 1000, max = 30_000): number {
  const exp = Math.min(max, base * 2 ** Math.max(0, attempt));
  return Math.round(exp * (0.8 + Math.random() * 0.4)); // jitter
}

export class BackendClient {
  private ws: WebSocket | null = null;
  private cfg: BackendConfig | null = null;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private lastMessageAt = 0;
  private stopped = true;
  state: ConnState = "idle";

  constructor(
    private readonly events: BackendClientEvents,
    private readonly WS: typeof WebSocket = WebSocket,
  ) {}

  start(cfg: BackendConfig): void {
    this.stop();
    this.cfg = cfg;
    this.stopped = false;
    this.attempt = 0;
    if (!cfg.token) {
      this.setState("unauthorized", "Mangler token – åpne innstillingene");
      return;
    }
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close(1000);
      this.ws = null;
    }
    this.setState("idle");
  }

  /** Reconnect immediately (e.g. when a panel becomes visible). */
  kick(): void {
    if (!this.stopped && (this.state === "error" || this.state === "idle") && !this.ws) {
      this.clearTimers();
      this.connect();
    }
  }

  private setState(s: ConnState, detail?: string) {
    this.state = s;
    this.events.onState(s, detail);
  }

  private clearTimers() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.reconnectTimer = null;
    this.pingTimer = null;
  }

  private send(m: ClientMessage) {
    if (this.ws?.readyState === this.WS.OPEN) this.ws.send(JSON.stringify(m));
  }

  private connect() {
    if (!this.cfg) return;
    let url: string;
    try {
      url = toWsUrl(this.cfg.url);
    } catch (e) {
      this.setState("error", (e as Error).message);
      return;
    }
    this.setState("connecting");
    const ws = new this.WS(url);
    this.ws = ws;
    ws.onopen = () => {
      this.setState("authenticating");
      this.send({ type: "auth", token: this.cfg!.token });
    };
    ws.onmessage = (ev) => {
      this.lastMessageAt = Date.now();
      const msg = parseServerMessage(String(ev.data));
      if (!msg) return;
      if (msg.type === "hello") {
        this.attempt = 0;
        this.setState("connected");
        this.startPing();
      }
      this.events.onMessage(msg);
    };
    ws.onerror = () => {
      /* onclose follows and handles reconnection */
    };
    ws.onclose = (ev) => {
      this.ws = null;
      this.clearTimers();
      if (this.stopped) return;
      if (ev.code === CLOSE_UNAUTHORIZED) {
        this.setState("unauthorized", "Ugyldig token");
        this.schedule(UNAUTHORIZED_RETRY_MS);
        return;
      }
      this.setState("error", ev.code === 1008 ? "Origin avvist av backend" : "Ingen kontakt med backend");
      this.schedule(backoffMs(this.attempt++));
    };
  }

  private schedule(ms: number) {
    this.reconnectTimer = setTimeout(() => this.connect(), ms);
  }

  private startPing() {
    this.pingTimer = setInterval(() => {
      if (Date.now() - this.lastMessageAt > LIVENESS_TIMEOUT_MS) {
        // Half-open connection: force a reconnect.
        this.ws?.close(4000);
        return;
      }
      this.send({ type: "ping", t: Date.now() });
    }, PING_INTERVAL_MS);
  }
}
