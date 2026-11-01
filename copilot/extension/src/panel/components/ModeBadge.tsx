import type { MarketState } from "../../shared/marketState";

/** Always-visible indicator of where the data comes from. Live is never ambiguous. */
export function ModeBadge({ market }: { market: MarketState }) {
  // The status message carries the resolved mode (MT5 reports demo vs live account).
  const mode = market.status?.mode ?? market.hello?.mode;
  if (!mode) return null;
  const cfg =
    mode === "mt5_live"
      ? { text: "LIVE", cls: "bg-tv-down/20 text-tv-down border-tv-down/50" }
      : mode === "mt5_demo"
        ? { text: "MT5 DEMO", cls: "bg-tv-blue/20 text-blue-300 border-tv-blue/50" }
        : mode === "mt5"
          ? { text: "MT5 …", cls: "bg-tv-panel text-tv-muted border-tv-border" }
          : { text: "SIMULERT", cls: "bg-tv-amber/15 text-tv-amber border-tv-amber/50" };
  return (
    <span
      className={`rounded border px-1 py-px text-[10px] font-bold tracking-wider ${cfg.cls}`}
      title={mode === "demo" ? "Syntetiske demodata – ikke ekte markedspriser" : `Modus: ${mode}`}
    >
      {cfg.text}
    </span>
  );
}
