import type { MarketState } from "../../shared/marketState";

/** Shows exactly which data source / broker account the panel is connected to. */
export function AccountCard({ market }: { market: MarketState }) {
  const st = market.status;
  if (!st) return null;
  if (st.synthetic) return null; // demo banner is shown elsewhere
  const acc = st.account;
  if (!acc) {
    return (
      <div className="rounded border border-tv-down/40 bg-tv-down/10 px-2 py-1.5 text-[11px] text-tv-down">
        <b>Ikke koblet til MT5-kontoen.</b> {st.lastError ?? "Venter på MetaTrader 5 …"}
      </div>
    );
  }
  const live = acc.tradeMode === "live";
  return (
    <div className={`rounded border px-2 py-1.5 text-[11px] ${live ? "border-tv-down/50 bg-tv-down/10" : "border-tv-blue/40 bg-tv-blue/10"}`}>
      <div className="flex items-center gap-2">
        <span className={`font-bold ${live ? "text-tv-down" : "text-blue-300"}`}>{live ? "LIVE-KONTO" : "DEMOKONTO"}</span>
        <span className="truncate text-tv-text" title={acc.company}>
          {acc.company || acc.server}
        </span>
      </div>
      <div className="text-tv-muted">
        Server {acc.server} · konto {acc.login} · {acc.currency}
        {acc.leverage ? ` · 1:${acc.leverage}` : ""}
        {market.symbol?.brokerSymbol ? ` · symbol ${market.symbol.brokerSymbol}` : ""}
      </div>
    </div>
  );
}
