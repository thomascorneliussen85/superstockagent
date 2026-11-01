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
  const age = formatAge(f.ageMs);

  const st = data.market.status;
  const problem =
    data.conn === "connected" && st && (st.state === "disconnected" || st.warnings.length > 0)
      ? st.state === "disconnected"
        ? st.lastError ?? "Datakilden er frakoblet"
        : st.warnings[0]
      : null;
  const stale = data.conn === "connected" && st?.state === "stale";

  return (
    <>
      {problem && (
        <div className={`shrink-0 border-t px-2 py-1 text-[11px] ${st?.state === "disconnected" ? "border-tv-down/40 bg-tv-down/10 text-tv-down" : "border-tv-amber/40 bg-tv-amber/10 text-tv-amber"}`}>
          {problem}
        </div>
      )}
      {stale && !problem && (
        <div className="shrink-0 border-t border-tv-amber/40 bg-tv-amber/10 px-2 py-1 text-[11px] text-tv-amber">
          Ingen nye priser – markedet kan være stengt, eller MT5 har mistet forbindelsen.
        </div>
      )}
    <footer className="flex shrink-0 items-center gap-2 border-t border-tv-border bg-tv-panel px-2 py-1 pr-4 text-[11px] text-tv-muted">
      <span title={data.connDetail} className="truncate">
        {data.conn !== "connected" ? (
          <>
            Backend: {CONN_TEXT[data.conn].toLowerCase()}
            {data.connDetail ? ` – ${data.connDetail}` : ""}
          </>
        ) : st?.synthetic ? (
          "Demodata"
        ) : st?.account ? (
          <span className="text-tv-text">MT5: {st.account.company || st.account.server}</span>
        ) : (
          <span className="text-tv-down">MT5: ikke tilkoblet</span>
        )}
      </span>
      <span className="ml-auto shrink-0">
        Data: <span className={fCls}>{age}</span>
      </span>
      {data.market.hello?.readOnly && (
        <span className="shrink-0 rounded border border-tv-border px-1" title="Backend kan ikke plassere, endre eller lukke handler">
          KUN LESING
        </span>
      )}
    </footer>
    </>
  );
}

export function formatAge(ms: number | null): string {
  if (ms == null) return "ingen data";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)} min`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)} t`;
  return `${Math.floor(ms / 86_400_000)} d`;
}
