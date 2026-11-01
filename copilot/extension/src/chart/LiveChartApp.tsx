import { useEffect, useReducer, useRef, useState } from "react";
import type { BackendClient, BackendConfig } from "../shared/backendClient";
import { emptyMarketState, reduceMarket, type MarketState } from "../shared/marketState";
import type { CandleMsg, ConnState, ServerMessage, Timeframe } from "../shared/protocol";
import { api, connect, loadConfig } from "../pages/conn";
import { ChartView, DEFAULT_OVERLAYS, OverlayToggles, type Overlays } from "../pages/ChartView";
import { no, summarize } from "../panel/describe";

const OVERLAY_KEY = "copilot.chartOverlays";
const reducer = (s: MarketState, m: ServerMessage) => reduceMarket(s, m, Date.now());
const load = <T,>(k: string, d: T): T => {
  try {
    return { ...d, ...JSON.parse(localStorage.getItem(k) ?? "{}") };
  } catch {
    return d;
  }
};

export function LiveChartApp() {
  const [cfg, setCfg] = useState<BackendConfig | null>(null);
  const [conn, setConn] = useState<ConnState>("idle");
  const [market, dispatch] = useReducer(reducer, undefined, emptyMarketState);
  const [tf, setTf] = useState<Timeframe>("1m");
  const [overlays, setOverlays] = useState<Overlays>(() => load(OVERLAY_KEY, DEFAULT_OVERLAYS));
  const client = useRef<BackendClient | null>(null);

  useEffect(() => void loadConfig().then(setCfg), []);
  useEffect(() => {
    if (!cfg) return;
    const c = connect(cfg, (m) => m.type !== "replay" && m.type !== "replay_state" && dispatch(m), setConn);
    client.current = c;
    return () => c.stop();
  }, [cfg]);
  // Longer history than the WebSocket snapshot, loaded once per timeframe.
  useEffect(() => {
    if (!cfg || conn !== "connected") return;
    void api<{ tf: Timeframe; candles: CandleMsg[] }>(cfg, `/api/candles?tf=${tf}&limit=500`).then((r) =>
      dispatch({ type: "candles", data: r }),
    );
  }, [cfg, conn, tf]);

  const setO = (o: Overlays) => {
    setOverlays(o);
    localStorage.setItem(OVERLAY_KEY, JSON.stringify(o));
  };
  const ai = market.ai;
  const a = market.analysis;
  const vp = a?.volumeProfile;
  const d = market.symbol?.digits ?? 2;

  return (
    <div className="copilot-root flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-tv-border bg-tv-panel px-3 py-2 text-xs">
        <b className="text-sm text-tv-text">XAUUSD · live fra MT5</b>
        {(["1m", "5m", "15m", "1h"] as Timeframe[]).map((k) => (
          <button key={k} onClick={() => setTf(k)} className={`rounded px-2 py-0.5 ${tf === k ? "bg-tv-hover text-tv-text" : "text-tv-muted"}`}>
            {k}
          </button>
        ))}
        <OverlayToggles value={overlays} onChange={setO} />
        {market.tick && (
          <span className="tabular ml-auto font-mono text-tv-text">
            {no(market.tick.bid, d)} / {no(market.tick.ask, d)}
          </span>
        )}
        <span className={conn === "connected" ? "text-tv-up" : "text-tv-down"}>{conn === "connected" ? "● tilkoblet" : "● frakoblet"}</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <ChartView candles={market.candles[tf]} tf={tf} analysis={a} ai={ai} overlays={overlays} />
        <aside className="w-[320px] shrink-0 space-y-3 overflow-y-auto border-l border-tv-border p-3 text-xs">
          <section className="space-y-1">
            <div className="flex items-center">
              <h3 className="text-[10px] uppercase tracking-wider text-tv-muted">Siste AI-vurdering</h3>
              <button onClick={() => client.current?.request({ type: "ai_request" })} className="ml-auto rounded bg-tv-blue px-2 py-0.5 text-white">
                Spør AI nå
              </button>
            </div>
            {ai ? (
              <div className="rounded border border-tv-border bg-tv-panel p-2">
                <p className="text-tv-text">{ai.summary}</p>
                {ai.setup ? (
                  <p className={ai.setup.direction === "long" ? "text-tv-up" : "text-tv-down"}>
                    Mulig {ai.setup.direction === "long" ? "KJØP" : "SALG"}: {no(ai.setup.entryLow, d)}–{no(ai.setup.entryHigh, d)} · invalidering {no(ai.setup.invalidation, d)} · mål {no(ai.setup.target, d)} · R/R {no(ai.setup.rr, 1)}
                  </p>
                ) : (
                  <p className="text-tv-muted">Ingen konkret kjøp/salg-sone akkurat nå ({{ long: "heller long", short: "heller short", neutral: "nøytral", avoid: "avvent" }[ai.bias]}).</p>
                )}
                <p className="mt-1 text-[10px] text-tv-muted">{new Date(ai.createdAt).toLocaleTimeString("nb-NO")} · AI-tolkning, ingen garanti</p>
              </div>
            ) : (
              <p className="text-tv-muted">Ingen ennå – kommer automatisk ved viktige hendelser.</p>
            )}
          </section>
          {a && (
            <section className="space-y-1">
              <h3 className="text-[10px] uppercase tracking-wider text-tv-muted">Oppsummering {tf}</h3>
              <ul className="space-y-0.5 text-tv-text">
                {summarize(a, tf, d).map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </section>
          )}
          {vp && (
            <section className="space-y-0.5">
              <h3 className="text-[10px] uppercase tracking-wider text-tv-muted">Volumprofil (tick-volum, siste døgn)</h3>
              <p className="text-tv-text">POC (mest handlet): {no(vp.poc, d)}</p>
              <p className="text-tv-text">Verdiområde 70 %: {no(vp.val, d)} – {no(vp.vah, d)}</p>
              {vp.hvn.length > 0 && <p className="text-tv-text">Andre høyvolumsnivåer: {vp.hvn.map((x) => no(x, d)).join(", ")}</p>}
              <p className="text-[10px] text-tv-muted">Spot-gull har ikke sentralt børsvolum; tick-volum (antall prisendringer) brukes som tilnærming.</p>
            </section>
          )}
          <p className="text-[10px] text-tv-muted">Nivåer, trendlinjer og volum er beregnet av kode. Kjøp/salg-sonene er AI-ens forslag, kontrollert av koden – ikke garantier eller finansiell rådgivning.</p>
        </aside>
      </div>
    </div>
  );
}
