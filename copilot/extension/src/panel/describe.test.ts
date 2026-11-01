import { describe, expect, it } from "vitest";
import type { Analysis, TfAnalysis } from "../shared/protocol";
import { eventText, no, summarize } from "./describe";

const tf = (over: Partial<TfAnalysis> = {}): TfAnalysis => ({
  tf: "1m",
  bars: 500,
  closedBars: 499,
  insufficient: false,
  rsi: 57.2,
  rsiZone: "bullish",
  atr: 1.4,
  volatility: "normal",
  distEma20Atr: 0.1,
  trend: { label: "up", score: 3, votes: { ema: 1, supertrend: 1, structure: 1, ema200: 0 } },
  levels: { support: [{ price: 3985.2, touches: 2, highs: 1, lows: 1, lastT: 0 }], resistance: [{ price: 3992.4, touches: 1, highs: 1, lows: 0, lastT: 0 }] },
  patterns: [],
  ...over,
});

const analysis = (over: Partial<Analysis> = {}): Analysis => ({
  engine: "2",
  computedAt: 0,
  tickTime: 0,
  symbol: "XAUUSD",
  price: { bid: 3990, ask: 3990.2 },
  timeframes: {
    "1m": tf(),
    "5m": tf({ tf: "5m" }),
    "15m": tf({ tf: "15m", trend: { label: "down", score: -2, votes: { ema: -1, supertrend: -1, structure: 0, ema200: 0 } } }),
    "1h": tf({ tf: "1h", insufficient: true, bars: 12 }),
  },
  alignment: { up: 2, down: 1, sideways: 0 },
  spread: { current: 0.6, points: 60, costPerLot: 60, currency: "USD", ratio: 2.1, state: "elevated", samples: 500 },
  recentEvents: [],
  ...over,
});

describe("summarize", () => {
  const s = summarize(analysis(), "1m");
  it("describes trend, RSI, EMA 20 and levels in Norwegian", () => {
    expect(s[0]).toBe("1m: Opptrend – 3 av 4 trendsignaler er enige.");
    expect(s).toContain("RSI er 57,2 – positivt momentum.");
    expect(s).toContain("Prisen er nær EMA 20.");
    expect(s).toContain("Nærmeste støtte 3985,20, motstand 3992,40.");
  });
  it("flags conflicting timeframes and skips insufficient ones", () => {
    const ctx = s.find((x) => x.startsWith("Andre tidsrammer"))!;
    expect(ctx).toContain("15m nedtrend");
    expect(ctx).not.toContain("1h");
    expect(ctx).toContain("ikke enige");
  });
  it("mentions elevated spread", () => {
    expect(s).toContain("Spreaden er forhøyet (2,1× normalt).");
  });
  it("handles insufficient data", () => {
    expect(summarize(analysis(), "1h")[0]).toContain("For lite historikk");
  });
});

describe("formatting", () => {
  it("uses Norwegian decimal comma", () => {
    expect(no(3985.2)).toBe("3985,20");
    expect(no(null)).toBe("–");
  });
  it("describes events", () => {
    expect(eventText({ type: "false_breakout_up", level: 4001.5, tf: "1m", t: 0 })).toBe("Falskt brudd over 4001,50 (likviditetssveip)");
  });
});

import { formatAge } from "./components/StatusBar";

describe("formatAge", () => {
  it("is readable for every range", () => {
    expect(formatAge(null)).toBe("ingen data");
    expect(formatAge(420)).toBe("420 ms");
    expect(formatAge(2500)).toBe("2,5 s");
    expect(formatAge(5 * 60_000)).toBe("5 min");
    expect(formatAge(3 * 3_600_000)).toBe("3 t");
    expect(formatAge(172_813_100)).toBe("2 d");
  });
});
