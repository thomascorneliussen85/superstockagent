// Optional Norwegian voice alerts (Web Speech API), with deduplication and
// cooldowns so the panel never chatters. The decision logic is pure and tested;
// only `speak` touches the browser.
import type { MarketState } from "../shared/marketState";
import type { AnalysisEvent } from "../shared/protocol";

export type AlertType = "setup" | "structure" | "spread" | "sl" | "risk";

export interface VoiceSettings {
  enabled: boolean;
  volume: number; // 0..1
  types: Record<AlertType, boolean>;
}

export const DEFAULT_VOICE: VoiceSettings = {
  enabled: false,
  volume: 0.8,
  types: { setup: true, structure: true, spread: true, sl: true, risk: true },
};

export interface Alert {
  type: AlertType;
  key: string;
  text: string;
}

const TF_WORDS: Record<string, string> = { "1m": "ett minutt", "5m": "fem minutter", "15m": "femten minutter", "1h": "én time" };
const EVENT_WORDS: Record<AnalysisEvent["type"], string> = {
  bos_up: "Strukturbrudd opp",
  bos_down: "Strukturbrudd ned",
  breakout_up: "Brudd over nivå",
  breakout_down: "Brudd under nivå",
  false_breakout_up: "Falskt brudd over nivå",
  false_breakout_down: "Falskt brudd under nivå",
};
/** 1m events are too frequent to speak; they stay visual. */
const SPOKEN_EVENT_TFS = new Set(["5m", "15m"]);

const evKey = (e: AnalysisEvent) => `ev:${e.tf}:${e.type}:${e.t}:${e.level}`;

/** Alerts implied by the change from `prev` to `next`. No alerts on the first snapshot. */
export function alertsBetween(prev: MarketState | null, next: MarketState): Alert[] {
  if (!prev) return [];
  const out: Alert[] = [];

  const ai = next.ai;
  if (ai && ai.id !== prev.ai?.id) {
    if (ai.setup) {
      out.push({ type: "setup", key: `ai:${ai.id}`, text: `Mulig ${ai.setup.direction}-oppsett utvikler seg.` });
    } else if (ai.bias === "avoid" && prev.ai?.bias !== "avoid") {
      out.push({ type: "setup", key: `ai:${ai.id}`, text: "Forholdene er dårlige for scalping nå." });
    }
  }

  if (prev.analysis && next.analysis) {
    const seen = new Set(prev.analysis.recentEvents.map(evKey));
    for (const e of next.analysis.recentEvents) {
      if (seen.has(evKey(e)) || !SPOKEN_EVENT_TFS.has(e.tf)) continue;
      out.push({ type: "structure", key: evKey(e), text: `${EVENT_WORDS[e.type]} på ${TF_WORDS[e.tf] ?? e.tf}.` });
    }
    const wasHigh = prev.analysis.spread?.state === "high";
    if (next.analysis.spread?.state === "high" && !wasHigh) {
      out.push({ type: "spread", key: `spread:${next.analysis.computedAt}`, text: "Spreaden er uvanlig høy." });
    }
  }
  // Account / position risk alerts (spoken once per key while the condition lasts).
  const before = new Set((prev.account?.alerts ?? []).map((a) => a.key));
  for (const a of next.account?.alerts ?? []) {
    if (before.has(a.key) || a.level === "info") continue;
    const spoken = spokenRisk(a.key, a.kind);
    if (spoken) out.push(spoken);
  }
  return out;
}

function spokenRisk(key: string, kind: string): Alert | null {
  const k = key.split(":")[0];
  if (kind === "sl") return { type: "sl", key, text: "Stop-lossen nærmer seg." };
  if (k === "nosl") return { type: "risk", key, text: "En åpen posisjon mangler stop-loss." };
  if (k === "risk") return { type: "risk", key, text: "Posisjonen risikerer mer enn din grense." };
  if (key === "daily:reached") return { type: "risk", key, text: "Du har nådd din daglige risikogrense." };
  if (key === "daily:near") return { type: "risk", key, text: "Du er nær din daglige risikogrense." };
  if (k === "corr") return { type: "risk", key, text: "Du har flere korrelerte posisjoner." };
  if (k === "margin") return { type: "risk", key, text: "Marginnivået er lavt." };
  if (kind === "spread") return { type: "spread", key, text: "Spreaden har økt kraftig." };
  return null;
}

export const COOLDOWN_MS: Record<AlertType, number> = {
  setup: 60_000,
  structure: 45_000,
  spread: 120_000,
  sl: 20_000,
  risk: 60_000,
};
const GLOBAL_GAP_MS = 8_000;

/** Drops duplicates, alerts inside their type cooldown, and anything too soon after the last spoken alert. */
export class AlertGate {
  private seen: string[] = [];
  private lastByType: Partial<Record<AlertType, number>> = {};
  private lastAny = -Infinity;

  allow(a: Alert, now: number, settings: VoiceSettings): boolean {
    if (!settings.enabled || !settings.types[a.type]) return false;
    if (this.seen.includes(a.key)) return false;
    if (now - (this.lastByType[a.type] ?? -Infinity) < COOLDOWN_MS[a.type]) return false;
    if (now - this.lastAny < GLOBAL_GAP_MS) return false;
    this.seen.push(a.key);
    if (this.seen.length > 200) this.seen.shift();
    this.lastByType[a.type] = now;
    this.lastAny = now;
    return true;
  }
}

function norwegianVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis?.getVoices() ?? [];
  return (
    voices.find((v) => /^(nb|no|nn)(-|_|$)/i.test(v.lang)) ?? voices.find((v) => /norsk|norwegian/i.test(v.name))
  );
}

export function speak(text: string, volume: number): void {
  const synth = window.speechSynthesis;
  if (!synth) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "nb-NO";
  const v = norwegianVoice();
  if (v) u.voice = v;
  u.volume = Math.max(0, Math.min(1, volume));
  u.rate = 1.05;
  synth.speak(u);
}

export function hasNorwegianVoice(): boolean {
  return !!norwegianVoice();
}
