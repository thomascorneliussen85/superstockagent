// Wire protocol shared with the backend (copilot/backend/app/api/ws.py).
// Timestamps are integer milliseconds since the Unix epoch (UTC).

export const PROTOCOL_VERSION = 1;

export type Timeframe = "1m" | "5m" | "15m" | "1h";
export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h"];

export type FeedState = "starting" | "live" | "stale" | "disconnected";
export type TradingMode = "demo" | "mt5" | "mt5_demo" | "mt5_live";

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
  account: AccountInfo | null;
  warnings: string[];
  serverTime: number;
}

export interface AccountInfo {
  login: number;
  server: string;
  company: string;
  currency: string;
  tradeMode: "demo" | "live";
  leverage: number | null;
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
  tickValue: number | null;
  tickSize: number | null;
  brokerSymbol: string | null;
  currencyAccount: string | null;
}

// ---- Deterministic analysis (backend app/analysis/engine.py) ----
export type TrendLabel = "up" | "down" | "sideways";
export type RsiZone = "overbought" | "oversold" | "bullish" | "bearish" | "neutral";

export interface LevelInfo {
  price: number;
  touches: number;
  highs: number;
  lows: number;
  lastT: number;
}

export interface AnalysisEvent {
  type: "bos_up" | "bos_down" | "breakout_up" | "breakout_down" | "false_breakout_up" | "false_breakout_down";
  level: number;
  tf: Timeframe;
  t: number | null;
}

export interface TfAnalysis {
  tf: Timeframe;
  bars: number;
  closedBars: number;
  insufficient: boolean;
  lastClosedT?: number | null;
  close?: number;
  ema?: Record<"9" | "20" | "50" | "200", number | null>;
  emaStack?: "bull" | "bear" | "mixed" | null;
  aboveEma200?: boolean | null;
  rsi?: number | null;
  rsiPrev?: number | null;
  rsiZone?: RsiZone | null;
  atr?: number | null;
  atrPercentile?: number | null;
  volatility?: "low" | "normal" | "high" | null;
  lastRangeAtr?: number | null;
  supertrend?: { dir: 1 | -1 | null; value: number | null };
  distEma20Atr?: number | null;
  structure?: {
    label: "bullish" | "bearish" | "range" | "unknown";
    highs: "HH" | "LH" | null;
    lows: "HL" | "LL" | null;
    lastHigh: number | null;
    lastLow: number | null;
  };
  trend?: { label: TrendLabel; score: number; votes: Record<"ema" | "supertrend" | "structure" | "ema200", number> };
  levels?: { support: LevelInfo[]; resistance: LevelInfo[] };
  liquidity?: { above: LevelInfo[]; below: LevelInfo[] };
  patterns?: string[];
  events?: AnalysisEvent[];
  tickVolumeRatio?: number | null;
}

export interface SpreadInfo {
  current: number;
  points: number;
  costPerLot: number;
  currency: string;
  median?: number;
  p90?: number;
  ratio?: number | null;
  state: "normal" | "elevated" | "high" | null;
  samples: number;
}

export interface Analysis {
  engine: string;
  computedAt: number;
  tickTime: number | null;
  symbol: string;
  price: { bid: number; ask: number } | null;
  timeframes: Record<Timeframe, TfAnalysis>;
  alignment: { up: number; down: number; sideways: number };
  spread: SpreadInfo | null;
  recentEvents: AnalysisEvent[];
}

// ---- AI commentary (backend app/ai/service.py) ----
export type Bias = "long" | "short" | "neutral" | "avoid";

export interface AiSetup {
  direction: "long" | "short";
  kind: "pullback" | "breakout" | "reversal" | "range" | "none";
  entryLow: number;
  entryHigh: number;
  invalidation: number;
  target: number;
  /** Risk/reward computed by the backend (incl. spread), not by the model. */
  rr: number;
  riskPerOz: number;
  spreadAtCheck: number;
  supporting: string[];
  conflicting: string[];
}

export interface AiComment {
  id: number;
  createdAt: number;
  tickTime: number | null;
  price: { bid: number; ask: number } | null;
  atr1m: number | null;
  summary: string;
  bias: Bias;
  setup: AiSetup | null;
  setupRejected: string | null;
  warnings: string[];
  reasons: string[];
  manual: boolean;
  model: string;
  costNok: number;
  tokens: { in: number; out: number };
}

export interface AiStatus {
  state: "disabled" | "thinking" | "ready";
  reason: string | null;
  note: string | null;
  model: string | null;
  pending: string[];
  cooldownS: number;
  budget: { monthCapNok: number; monthSpentNok: number; daySpentNok: number; dayAllowanceNok: number; callsToday: number };
}

// ---- Account & positions (backend app/account/risk.py), read-only ----
export interface PositionView {
  ticket: number;
  symbol: string;
  type: "buy" | "sell";
  volume: number;
  oz: number;
  digits: number;
  priceOpen: number;
  priceCurrent: number;
  sl: number;
  tp: number;
  profit: number;
  swap: number;
  timeMs: number;
  riskMoney: number | null;
  riskPct: number | null;
  lockedMoney: number | null;
  toSlMoney: number | null;
  distToSl: number | null;
  distToSlAtr: number | null;
  slProgress: number | null;
  distToTp: number | null;
  rMultiple: number | null;
}

export interface RiskAlert {
  key: string;
  level: "critical" | "warn" | "info";
  text: string;
  ticket: number | null;
  kind: "risk" | "sl" | "daily" | "spread";
}

export interface AccountView {
  available: boolean;
  reason?: string;
  account?: {
    login: number;
    currency: string;
    balance: number;
    equity: number;
    profit: number;
    margin: number;
    marginFree: number;
    marginLevel: number;
    tradeMode: "demo" | "live";
  };
  positions?: PositionView[];
  pendingOrders?: number;
  day?: {
    realized: number;
    floating: number;
    result: number;
    startBalance: number;
    limitMoney: number;
    limitPct: number;
    usedPct: number | null;
    openRisk: number;
    anyWithoutSl: boolean;
    closedTrades: number;
  };
  rules?: { maxPerTradePct: number; dailyLossLimitPct: number };
  alerts?: RiskAlert[];
}

// ---- Coach (backend app/coach) ----
export interface Insight {
  id: string;
  kind: "strength" | "weakness" | "habit";
  title: string;
  detail: string;
  strength: "solid" | "foreløpig";
  diff?: number;
  ci?: [number, number];
  unit?: "R" | "money";
}

export interface TradeFeedback {
  position_id: number;
  direction: "long" | "short";
  closeMs: number;
  net: number;
  r: number | null;
  headline: string;
  points: { tone: "good" | "bad" | "warn" | "neutral"; text: string }[];
}

export interface SimilarResult {
  n: number;
  reason?: string;
  winRate?: number;
  winRateCi?: [number, number] | null;
  meanOutcome?: number;
  meanCi?: [number, number] | null;
  unit?: "R" | "money";
  enough?: boolean;
}

export interface CoachPanel {
  minSample: number;
  trades: number;
  insights: Insight[];
  drift: { group: string; status: string; recentMean: number; beforeMean: number; ci: [number, number] }[];
  recommended: { id: string; title: string; oosGain: number | null; oosCi: [number, number] | null }[];
  lastFeedback: TradeFeedback | null;
  similar: { long?: SimilarResult; short?: SimilarResult };
  reviews: { id: number; period: string; label: string }[];
}

export interface ReplayState {
  active: boolean;
  error?: string;
  startMs?: number;
  clockMs?: number;
  speed?: number;
  paused?: boolean;
  ended?: boolean;
  dataQuality?: "ticks" | "bars" | "synthetic";
  account?: {
    balance: number;
    equity: number;
    commissionPerLot: number;
    contractSize: number;
    positions: { id: number; side: "buy" | "sell"; volume: number; entry: number; sl: number | null; tp: number | null; open_ms: number; profit: number; risk_money: number | null }[];
    trades: { id: number; side: "buy" | "sell"; volume: number; entry: number; exit: number; open_ms: number; close_ms: number; net: number; r_multiple: number | null; exit_reason: string; mfe: number; mae: number }[];
  };
  events?: { type: string; fromMs?: number; toMs?: number }[];
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
  | { type: "analysis"; data: Analysis }
  | { type: "ai"; data: AiComment }
  | { type: "account"; data: AccountView }
  | { type: "coach"; data: CoachPanel }
  | { type: "trade_feedback"; data: TradeFeedback }
  | { type: "replay"; data: ServerMessage }
  | { type: "replay_state"; data: ReplayState }
  | { type: "ai_status"; data: AiStatus }
  | { type: "pong"; data: { t: number | null } }
  | { type: "error"; data: { code: string } };

export type ClientMessage =
  | { type: "auth"; token: string }
  | { type: "ping"; t: number }
  | { type: "ai_request" }
  | { type: "replay_start"; startMs: number; speed?: number; balance?: number; commissionPerLot?: number }
  | { type: "replay_control"; action: "pause" | "resume" | "speed" | "jump" | "stop"; value?: number }
  | { type: "replay_order"; side: "buy" | "sell"; volume: number; slDistance: number | null; tpDistance: number | null }
  | { type: "replay_close"; id: number | "all" }
  | { type: "replay_ai" };

const KNOWN = new Set([
  "hello", "status", "heartbeat", "symbol", "tick", "candle", "candles", "analysis", "ai", "ai_status", "account", "coach", "trade_feedback", "replay", "replay_state", "pong", "error",
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
