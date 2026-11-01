import { describe, expect, it } from "vitest";
import { emptyMarketState, freshness, MAX_CANDLES, reduceMarket, upsertCandle } from "./marketState";
import type { CandleMsg, ServerMessage } from "./protocol";

const c = (t: number, close = 1, closed = false): CandleMsg => ({
  symbol: "XAUUSD", tf: "1m", t, o: 1, h: 2, l: 0.5, c: close, n: 1, maxSpread: 0.2, closed,
});

describe("upsertCandle", () => {
  it("replaces the forming candle and appends new ones", () => {
    let l = upsertCandle([], c(0, 1));
    l = upsertCandle(l, c(0, 1.5));
    expect(l).toHaveLength(1);
    expect(l[0].c).toBe(1.5);
    l = upsertCandle(l, c(60_000));
    expect(l.map((x) => x.t)).toEqual([0, 60_000]);
  });
  it("never reorders on late updates and ignores unknown old candles", () => {
    const l = [c(60_000), c(120_000)];
    expect(upsertCandle(l, c(0))).toBe(l);
    expect(upsertCandle(l, c(60_000, 9))[0].c).toBe(9);
  });
  it("caps history length", () => {
    let l: CandleMsg[] = [];
    for (let i = 0; i < MAX_CANDLES + 10; i++) l = upsertCandle(l, c(i * 60_000));
    expect(l).toHaveLength(MAX_CANDLES);
    expect(l[0].t).toBe(10 * 60_000);
  });
});

describe("reduceMarket", () => {
  it("hello resets state from a previous session", () => {
    let s = reduceMarket(emptyMarketState(), { type: "candle", data: c(0) }, 0);
    s = reduceMarket(s, { type: "hello", data: { serverVersion: "x", protocol: 1, mode: "demo", readOnly: true, symbol: "XAUUSD" } }, 0);
    expect(s.candles["1m"]).toHaveLength(0);
    expect(s.hello?.mode).toBe("demo");
  });
  it("records tick receive time and sorts candle snapshots", () => {
    let s = reduceMarket(emptyMarketState(), { type: "tick", data: { symbol: "XAUUSD", t: 1, bid: 1, ask: 1.2, spread: 0.2 } }, 1000);
    expect(s.tickAt).toBe(1000);
    const msg: ServerMessage = { type: "candles", data: { tf: "1m", candles: [c(120_000), c(0), c(60_000)] } };
    s = reduceMarket(s, msg, 0);
    expect(s.candles["1m"].map((x) => x.t)).toEqual([0, 60_000, 120_000]);
  });
});

describe("freshness", () => {
  const withTick = reduceMarket(emptyMarketState(), { type: "tick", data: { symbol: "XAUUSD", t: 1, bid: 1, ask: 1.2, spread: 0.2 } }, 10_000);
  it("classifies by age", () => {
    expect(freshness(emptyMarketState(), 0).level).toBe("none");
    expect(freshness(withTick, 10_500).level).toBe("fresh");
    expect(freshness(withTick, 13_000).level).toBe("delayed");
    expect(freshness(withTick, 16_000).level).toBe("stale");
  });
});

import { PanelRelay, type PanelEvent } from "./transport";

describe("PanelRelay", () => {
  it("gives late subscribers a complete snapshot", () => {
    const r = new PanelRelay(() => 5);
    r.push({ kind: "conn", conn: "connected" });
    r.push({ kind: "msg", msg: { type: "hello", data: { serverVersion: "x", protocol: 1, mode: "demo", readOnly: true, symbol: "XAUUSD" } } });
    r.push({ kind: "msg", msg: { type: "tick", data: { symbol: "XAUUSD", t: 1, bid: 1, ask: 1.2, spread: 0.2 } } });
    const got: PanelEvent[] = [];
    r.subscribe((e) => got.push(e));
    expect(got).toHaveLength(1);
    const snap = got[0];
    expect(snap.kind).toBe("snapshot");
    if (snap.kind === "snapshot") {
      expect(snap.conn).toBe("connected");
      expect(snap.market.hello?.mode).toBe("demo");
      expect(snap.market.tick?.bid).toBe(1);
    }
  });
});

describe("freshness with backend status", () => {
  it("treats an old price as stale even if just received", () => {
    let s = reduceMarket(emptyMarketState(), { type: "tick", data: { symbol: "XAUUSD", t: 1, bid: 1, ask: 1.2, spread: 0.2 } }, 1000);
    s = reduceMarket(s, { type: "status", data: { state: "stale", mode: "mt5_demo", source: "mt5", synthetic: false, symbol: "XAUUSD", lastTickAgeMs: 172_800_000, ticksReceived: 1, reconnects: 0, lastError: null, account: null, warnings: [], serverTime: 0 } }, 1000);
    const f = freshness(s, 1500);
    expect(f.level).toBe("stale");
    expect(f.ageMs).toBeGreaterThan(172_800_000);
  });
});

describe("freshness while live", () => {
  it("does not age a live feed by an old status message", () => {
    let s = reduceMarket(emptyMarketState(), { type: "status", data: { state: "live", mode: "demo", source: "synthetic", synthetic: true, symbol: "XAUUSD", lastTickAgeMs: 20, ticksReceived: 1, reconnects: 0, lastError: null, account: null, warnings: [], serverTime: 0 } }, 0);
    s = reduceMarket(s, { type: "tick", data: { symbol: "XAUUSD", t: 1, bid: 1, ask: 1.2, spread: 0.2 } }, 30_000);
    expect(freshness(s, 30_300)).toEqual({ level: "fresh", ageMs: 300 });
  });
});
