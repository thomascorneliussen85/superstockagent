// Pure reducer holding the latest market view. Used by the background worker
// (to hydrate newly opened panels) and by the panel itself.
import type { AiComment, AiStatus, Analysis, CandleMsg, FeedStatus, Hello, ServerMessage, SymbolSpec, TickMsg, Timeframe } from "./protocol";

export const MAX_CANDLES = 300;

export interface MarketState {
  hello: Hello | null;
  status: FeedStatus | null;
  /** Local time the latest status was received (to age lastTickAgeMs locally). */
  statusAt: number | null;
  symbol: SymbolSpec | null;
  tick: TickMsg | null;
  /** Local receive time of the last tick (browser clock). */
  tickAt: number | null;
  candles: Record<Timeframe, CandleMsg[]>;
  analysis: Analysis | null;
  /** Local receive time of the latest analysis. */
  analysisAt: number | null;
  ai: AiComment | null;
  aiStatus: AiStatus | null;
}

export const emptyMarketState = (): MarketState => ({
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
});

export function upsertCandle(list: CandleMsg[], c: CandleMsg, max = MAX_CANDLES): CandleMsg[] {
  const last = list[list.length - 1];
  if (last && last.t === c.t) return [...list.slice(0, -1), c];
  if (last && c.t < last.t) {
    // Late update for an older candle: replace in place if present, never reorder.
    const i = list.findIndex((x) => x.t === c.t);
    if (i === -1) return list;
    const copy = list.slice();
    copy[i] = c;
    return copy;
  }
  const next = [...list, c];
  return next.length > max ? next.slice(next.length - max) : next;
}

export function reduceMarket(state: MarketState, msg: ServerMessage, now: number): MarketState {
  switch (msg.type) {
    case "hello":
      // New session: drop anything from a previous backend run.
      return { ...emptyMarketState(), hello: msg.data };
    case "status":
    case "heartbeat":
      return { ...state, status: msg.data, statusAt: now };
    case "symbol":
      return { ...state, symbol: msg.data };
    case "tick":
      return { ...state, tick: msg.data, tickAt: now };
    case "candle": {
      const tf = msg.data.tf;
      return { ...state, candles: { ...state.candles, [tf]: upsertCandle(state.candles[tf], msg.data) } };
    }
    case "analysis":
      return { ...state, analysis: msg.data, analysisAt: now };
    case "ai":
      return { ...state, ai: msg.data };
    case "ai_status":
      return { ...state, aiStatus: msg.data };
    case "candles": {
      const sorted = [...msg.data.candles].sort((a, b) => a.t - b.t).slice(-MAX_CANDLES);
      return { ...state, candles: { ...state.candles, [msg.data.tf]: sorted } };
    }
    default:
      return state;
  }
}

export type Freshness = "fresh" | "delayed" | "stale" | "none";

/** Classifies how old the latest price is, based on local receive time. */
export function freshness(state: MarketState, now: number, staleMs = 5000): { level: Freshness; ageMs: number | null } {
  if (state.tickAt == null) return { level: "none", ageMs: null };
  let age = Math.max(0, now - state.tickAt);
  // The backend knows when a price is old (e.g. last price before the weekend).
  // Only trust its age while it reports the feed as not live; status messages are
  // not resent on every tick, so in the live state the local receive time is exact.
  const st = state.status;
  if (st && st.state !== "live" && st.lastTickAgeMs != null && state.statusAt != null) {
    age = Math.max(age, st.lastTickAgeMs + (now - state.statusAt));
  }
  if (state.status?.state === "disconnected" || state.status?.state === "stale") return { level: "stale", ageMs: age };
  if (age > staleMs) return { level: "stale", ageMs: age };
  if (age > 2000) return { level: "delayed", ageMs: age };
  return { level: "fresh", ageMs: age };
}
