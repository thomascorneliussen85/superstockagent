import { freshness, type MarketState } from "../../shared/marketState";
import type { ConnState } from "../../shared/protocol";
import { useNow } from "../usePanel";

const CONN_TEXT: Record<ConnState, string> = {
  idle: "Ikke tilkoblet",
  connecting: "Kobler til…",
  authenticating: "Autentiserer…",
  connected: "Tilkoblet",
  unauthorized: "Ikke autorisert",
  error: "Frakoblet",
};

export function StatusBar({ data }: { data: { conn: ConnState; connDetail?: string; market: MarketState } }) {
  const now = useNow();
  const f = freshness(data.market, now);
  const fCls =
    f.level === "fresh" ? "text-tv-up" : f.level === "delayed" ? "text-tv-amber" : f.level === "stale" ? "text-tv-down" : "text-tv-muted";
  const age = f.ageMs == null ? "ingen data" : f.ageMs < 1000 ? `${f.ageMs} ms` : `${(f.ageMs / 1000).toFixed(1)} s`;

  return (
    <footer className="flex shrink-0 items-center gap-2 border-t border-tv-border bg-tv-panel px-2 py-1 pr-4 text-[11px] text-tv-muted">
      <span title={data.connDetail}>
        {CONN_TEXT[data.conn]}
        {data.conn !== "connected" && data.connDetail ? ` – ${data.connDetail}` : ""}
      </span>
      <span className="ml-auto">
        Data: <span className={fCls}>{age}</span>
      </span>
      {data.market.hello?.readOnly && (
        <span className="rounded border border-tv-border px-1" title="Backend kan ikke plassere, endre eller lukke handler">
          KUN LESING
        </span>
      )}
    </footer>
  );
}
