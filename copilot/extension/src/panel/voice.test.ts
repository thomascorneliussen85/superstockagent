import { describe, expect, it } from "vitest";
import { emptyMarketState, type MarketState } from "../shared/marketState";
import type { AiComment, Analysis, AnalysisEvent } from "../shared/protocol";
import { AlertGate, alertsBetween, DEFAULT_VOICE } from "./voice";

const analysis = (events: AnalysisEvent[], spread: "normal" | "high" = "normal"): Analysis => ({
  engine: "x", computedAt: events.length, tickTime: 0, symbol: "XAUUSD", price: null,
  timeframes: {} as Analysis["timeframes"], alignment: { up: 0, down: 0, sideways: 0 },
  spread: { current: 0.3, points: 30, costPerLot: 30, currency: "USD", state: spread, samples: 100 },
  recentEvents: events,
});
const ai = (id: number, withSetup = true): AiComment => ({
  id, createdAt: 0, tickTime: 0, price: null, atr1m: 1, summary: "", bias: "long", warnings: [], reasons: [],
  manual: false, model: "m", costNok: 0, tokens: { in: 0, out: 0 }, setupRejected: null,
  setup: withSetup ? { direction: "long", kind: "pullback", entryLow: 1, entryHigh: 2, invalidation: 0, target: 4, rr: 2, riskPerOz: 1, spreadAtCheck: 0.2, supporting: [], conflicting: [] } : null,
});
const st = (over: Partial<MarketState>): MarketState => ({ ...emptyMarketState(), ...over });
const ev = (tf: AnalysisEvent["tf"], t: number): AnalysisEvent => ({ type: "bos_up", level: 4000, tf, t });

describe("alertsBetween", () => {
  it("is silent on the first snapshot", () => {
    expect(alertsBetween(null, st({ ai: ai(1) }))).toEqual([]);
  });
  it("speaks a new AI setup once", () => {
    const a = alertsBetween(st({ ai: ai(1) }), st({ ai: ai(2) }));
    expect(a).toEqual([{ type: "setup", key: "ai:2", text: "Mulig long-oppsett utvikler seg." }]);
    expect(alertsBetween(st({ ai: ai(2) }), st({ ai: ai(2) }))).toEqual([]);
  });
  it("speaks new 5m/15m events but not 1m, and spread turning high", () => {
    const prev = st({ analysis: analysis([ev("5m", 1)]) });
    const next = st({ analysis: analysis([ev("1m", 3), ev("5m", 2), ev("5m", 1)], "high") });
    const a = alertsBetween(prev, next);
    expect(a.map((x) => x.text)).toEqual(["Strukturbrudd opp på fem minutter.", "Spreaden er uvanlig høy."]);
  });
});

describe("AlertGate", () => {
  const on = { ...DEFAULT_VOICE, enabled: true };
  it("respects enabled, type toggles, dedupe and cooldowns", () => {
    const g = new AlertGate();
    const a = { type: "setup" as const, key: "k1", text: "x" };
    expect(g.allow(a, 0, DEFAULT_VOICE)).toBe(false); // voice off by default
    expect(g.allow(a, 0, on)).toBe(true);
    expect(g.allow(a, 100_000, on)).toBe(false); // duplicate key
    expect(g.allow({ ...a, key: "k2" }, 30_000, on)).toBe(false); // setup cooldown 60 s
    expect(g.allow({ type: "spread", key: "s", text: "y" }, 3_000, on)).toBe(false); // global gap 8 s
    expect(g.allow({ type: "spread", key: "s", text: "y" }, 9_000, on)).toBe(true);
    expect(g.allow({ ...a, key: "k3" }, 70_000, { ...on, types: { ...on.types, setup: false } })).toBe(false);
  });
});
