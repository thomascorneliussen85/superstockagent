// Turns the deterministic analysis into short Norwegian sentences.
// Rule-based text only - Phase 3 adds LLM commentary on top of the same data.
import type { Analysis, AnalysisEvent, RsiZone, TfAnalysis, Timeframe, TrendLabel } from "../shared/protocol";
import { TIMEFRAMES } from "../shared/protocol";

export const no = (v: number | null | undefined, d = 2): string =>
  v == null || !Number.isFinite(v) ? "–" : v.toFixed(d).replace(".", ",").replace("-", "−");

export const TREND_TEXT: Record<TrendLabel, string> = {
  up: "Opptrend",
  down: "Nedtrend",
  sideways: "Sideveis / uklar",
};

export const RSI_TEXT: Record<RsiZone, string> = {
  overbought: "overkjøpt",
  oversold: "oversolgt",
  bullish: "positivt momentum",
  bearish: "negativt momentum",
  neutral: "nøytralt momentum",
};

export const PATTERN_TEXT: Record<string, string> = {
  doji: "doji (ubesluttsomhet)",
  bullish_pin: "bullish pin bar (avvisning nedover)",
  bearish_pin: "bearish pin bar (avvisning oppover)",
  bullish_engulfing: "bullish engulfing",
  bearish_engulfing: "bearish engulfing",
  inside_bar: "inside bar",
};

export const STRUCTURE_TEXT = {
  bullish: "høyere topper og bunner",
  bearish: "lavere topper og bunner",
  range: "blandet struktur (range)",
  unknown: "for få svingpunkter",
} as const;

export function eventText(e: AnalysisEvent, digits = 2): string {
  const lv = no(e.level, digits);
  switch (e.type) {
    case "bos_up":
      return `Strukturbrudd opp – lukket over siste topp ${lv}`;
    case "bos_down":
      return `Strukturbrudd ned – lukket under siste bunn ${lv}`;
    case "breakout_up":
      return `Brudd over nivå ${lv}`;
    case "breakout_down":
      return `Brudd under nivå ${lv}`;
    case "false_breakout_up":
      return `Falskt brudd over ${lv} (likviditetssveip)`;
    case "false_breakout_down":
      return `Falskt brudd under ${lv} (likviditetssveip)`;
  }
}

function trendSentence(a: TfAnalysis): string | null {
  if (!a.trend) return null;
  const v = a.trend.votes;
  const total = 4;
  const agree =
    a.trend.label === "up"
      ? Object.values(v).filter((x) => x > 0).length
      : a.trend.label === "down"
        ? Object.values(v).filter((x) => x < 0).length
        : null;
  return agree == null
    ? `${a.tf}: ${TREND_TEXT[a.trend.label]} – trendsignalene spriker.`
    : `${a.tf}: ${TREND_TEXT[a.trend.label]} – ${agree} av ${total} trendsignaler er enige.`;
}

/** Short factual summary for one timeframe plus multi-timeframe context. */
export function summarize(analysis: Analysis, tf: Timeframe, digits = 2): string[] {
  const a = analysis.timeframes[tf];
  if (!a || a.insufficient) return [`${tf}: For lite historikk til å analysere ennå (${a?.bars ?? 0} lys).`];
  const out: string[] = [];
  const t = trendSentence(a);
  if (t) out.push(t);

  if (a.rsi != null && a.rsiZone) out.push(`RSI er ${no(a.rsi, 1)} – ${RSI_TEXT[a.rsiZone]}.`);

  if (a.distEma20Atr != null) {
    const d = a.distEma20Atr;
    if (Math.abs(d) <= 0.3) out.push("Prisen er nær EMA 20.");
    else out.push(`Prisen ligger ${no(Math.abs(d), 1)} ATR ${d > 0 ? "over" : "under"} EMA 20.`);
  }

  const sup = a.levels?.support[0];
  const res = a.levels?.resistance[0];
  if (sup || res) {
    const parts = [];
    if (sup) parts.push(`støtte ${no(sup.price, digits)}`);
    if (res) parts.push(`motstand ${no(res.price, digits)}`);
    out.push(`Nærmeste ${parts.join(", ")}.`);
  }

  if (a.patterns && a.patterns.length > 0) {
    out.push(`Siste lukkede lys: ${a.patterns.map((p) => PATTERN_TEXT[p] ?? p).join(", ")}.`);
  }

  if (a.volatility === "high") out.push(`Volatiliteten er høy (ATR ${no(a.atr, digits)}).`);
  else if (a.volatility === "low") out.push(`Volatiliteten er lav (ATR ${no(a.atr, digits)}).`);

  const others = TIMEFRAMES.filter((x) => x !== tf)
    .map((x) => analysis.timeframes[x])
    .filter((x): x is TfAnalysis => !!x && !x.insufficient && !!x.trend);
  if (others.length) {
    const labels = others.map((x) => `${x.tf} ${TREND_TEXT[x.trend!.label].toLowerCase()}`);
    const dirs = new Set([a.trend?.label, ...others.map((x) => x.trend!.label)].filter((x) => x !== "sideways"));
    const conflict = dirs.has("up") && dirs.has("down");
    out.push(`Andre tidsrammer: ${labels.join(", ")}.${conflict ? " Tidsrammene er ikke enige." : ""}`);
  }

  const s = analysis.spread;
  if (s?.state === "high") out.push(`Spreaden er høy (${no(s.ratio ?? null, 1)}× normalt).`);
  else if (s?.state === "elevated") out.push(`Spreaden er forhøyet (${no(s.ratio ?? null, 1)}× normalt).`);
  return out;
}
