// Wire protocol shared with the backend (copilot/backend/app/api/ws.py).
// Timestamps are integer milliseconds since the Unix epoch (UTC).

export const PROTOCOL_VERSION = 1;

export type Timeframe = "1m" | "5m" | "15m" | "1h";
export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h"];

export type FeedState = "starting" | "live" | "stale" | "disconnected";
export type TradingMode = "demo" | "mt5_demo" | "mt5_live";

export interface Hello {
  serverVersion: string;
  protocol: number;
  mode: TradingMode;
  readOnly: boolean;
  symbol: string;
}

export interface FeedStatus {
  state: FeedState;
  mode: TradingMode;
  source: string;
  synthetic: boolean;
  symbol: string;
  lastTickAgeMs: number | null;
  ticksReceived: number;
  reconnects: number;
  lastError: string | null;
  serverTime: number;
}

export interface SymbolSpec {
  symbol: string;
  digits: number;
  point: number;
  contractSize: number;
  volumeMin: number;
  volumeStep: number;
  volumeMax: number;
  currencyProfit: string;
  description: string;
  source: string;
}

export interface TickMsg {
  symbol: string;
  t: number;
  bid: number;
  ask: number;
  spread: number;
}

export interface CandleMsg {
  symbol: string;
  tf: Timeframe;
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  n: number;
  maxSpread: number;
  closed: boolean;
}

export type ServerMessage =
  | { type: "hello"; data: Hello }
  | { type: "status"; data: FeedStatus }
  | { type: "heartbeat"; data: FeedStatus }
  | { type: "symbol"; data: SymbolSpec }
  | { type: "tick"; data: TickMsg }
  | { type: "candle"; data: CandleMsg }
  | { type: "candles"; data: { tf: Timeframe; candles: CandleMsg[] } }
  | { type: "pong"; data: { t: number | null } }
  | { type: "error"; data: { code: string } };

export type ClientMessage = { type: "auth"; token: string } | { type: "ping"; t: number };

const KNOWN = new Set([
  "hello", "status", "heartbeat", "symbol", "tick", "candle", "candles", "pong", "error",
]);

/** Parses and minimally validates a server frame. Returns null for unknown/malformed input. */
export function parseServerMessage(raw: string): ServerMessage | null {
  try {
    const m = JSON.parse(raw);
    if (m && typeof m === "object" && typeof m.type === "string" && KNOWN.has(m.type) && "data" in m) {
      return m as ServerMessage;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** Connection state of the extension <-> backend link (distinct from feed state). */
export type ConnState = "idle" | "connecting" | "authenticating" | "connected" | "unauthorized" | "error";
