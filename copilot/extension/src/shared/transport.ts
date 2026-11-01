// How the panel receives data. In the extension this is a chrome.runtime Port
// to the background worker; in the dev harness it is a direct BackendClient.
import { emptyMarketState, reduceMarket, type MarketState } from "./marketState";
import type { ConnState, ServerMessage } from "./protocol";

export type PanelEvent =
  | { kind: "snapshot"; conn: ConnState; detail?: string; market: MarketState }
  | { kind: "conn"; conn: ConnState; detail?: string }
  | { kind: "msg"; msg: ServerMessage }
  | { kind: "toggle" };

export interface PanelTransport {
  subscribe(cb: (ev: PanelEvent) => void): () => void;
  openOptions(): void;
}

export const PORT_NAME = "copilot-panel";

/**
 * Keeps the latest state so that a subscriber attaching late (React mounts
 * after the port already delivered data) or re-attaching always starts from
 * a complete snapshot instead of missing events.
 */
export class PanelRelay {
  private conn: ConnState = "idle";
  private detail: string | undefined;
  private market: MarketState = emptyMarketState();
  private readonly listeners = new Set<(ev: PanelEvent) => void>();

  constructor(private readonly now: () => number = Date.now) {}

  push(ev: PanelEvent): void {
    switch (ev.kind) {
      case "snapshot":
        this.conn = ev.conn;
        this.detail = ev.detail;
        this.market = ev.market;
        break;
      case "conn":
        this.conn = ev.conn;
        this.detail = ev.detail;
        break;
      case "msg":
        this.market = reduceMarket(this.market, ev.msg, this.now());
        break;
    }
    this.listeners.forEach((l) => l(ev));
  }

  subscribe(cb: (ev: PanelEvent) => void): () => void {
    this.listeners.add(cb);
    cb({ kind: "snapshot", conn: this.conn, detail: this.detail, market: this.market });
    return () => this.listeners.delete(cb);
  }
}
