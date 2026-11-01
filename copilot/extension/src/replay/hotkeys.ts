// Configurable replay hotkeys (pure helpers, unit tested).
export type HotkeyAction = "buy" | "sell" | "closeAll" | "pause" | "jump1m" | "jump15m" | "faster" | "slower";

export const DEFAULT_HOTKEYS: Record<HotkeyAction, string> = {
  buy: "B",
  sell: "S",
  closeAll: "X",
  pause: "Space",
  jump1m: "ArrowRight",
  jump15m: "Shift+ArrowRight",
  faster: "+",
  slower: "-",
};

export const ACTION_LABEL: Record<HotkeyAction, string> = {
  buy: "Kjøp (BUY)",
  sell: "Selg (SELL)",
  closeAll: "Lukk alle",
  pause: "Pause / spill",
  jump1m: "Hopp 1 minutt",
  jump15m: "Hopp 15 minutter",
  faster: "Raskere",
  slower: "Saktere",
};

/** Normalised combo string for a keyboard event, e.g. "Shift+ArrowRight", "B", "Space". */
export function comboOf(e: { key: string; shiftKey: boolean; ctrlKey: boolean; altKey: boolean; metaKey: boolean }): string {
  let k = e.key === " " ? "Space" : e.key.length === 1 ? e.key.toUpperCase() : e.key;
  if (k === "=" && e.shiftKey) k = "+";
  const mods = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && k.length > 1 && k !== "+" && "Shift"].filter(Boolean);
  return [...mods, k].join("+");
}

export function actionFor(combo: string, map: Record<HotkeyAction, string>): HotkeyAction | null {
  return (Object.keys(map) as HotkeyAction[]).find((a) => map[a] === combo) ?? null;
}

export const SPEEDS = [1, 2, 5, 10, 30, 60];

export function nextSpeed(cur: number, dir: 1 | -1): number {
  const i = SPEEDS.findIndex((s) => s >= cur);
  const idx = Math.max(0, Math.min(SPEEDS.length - 1, (i === -1 ? SPEEDS.length - 1 : i) + dir));
  return SPEEDS[idx];
}

/** Money at risk and potential reward for a market order with attached SL/TP (quote currency). */
export function orderRisk(lots: number, contractSize: number, slDist: number, tpDist: number, commissionPerLot: number) {
  const oz = lots * contractSize;
  const fee = commissionPerLot * lots;
  return { oz, risk: slDist * oz + fee, reward: tpDist * oz - fee, rr: slDist > 0 ? (tpDist * oz - fee) / (slDist * oz + fee) : null };
}
