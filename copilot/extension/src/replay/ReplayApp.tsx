import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { BackendClient, BackendConfig } from "../shared/backendClient";
import { emptyMarketState, reduceMarket, type MarketState } from "../shared/marketState";
import type { ConnState, ReplayState, ServerMessage, Timeframe } from "../shared/protocol";
import { chromeStore, localStore, type KVStore } from "../shared/storage";
import { connect, loadConfig } from "../pages/conn";
import { ChartView, DEFAULT_OVERLAYS, OverlayToggles, type Overlays } from "../pages/ChartView";
import { AnalysisTab } from "../panel/components/AnalysisTab";
import { no } from "../panel/describe";
import { ACTION_LABEL, actionFor, comboOf, DEFAULT_HOTKEYS, nextSpeed, orderRisk, SPEEDS, type HotkeyAction } from "./hotkeys";

const store: KVStore = typeof chrome !== "undefined" && chrome.storage ? chromeStore : localStore;
const TICKET_KEY = "copilot.replayTicket";
const HOTKEY_KEY = "copilot.replayHotkeys";

const hms = (ms?: number) => (ms ? new Date(ms).toLocaleString("nb-NO", { dateStyle: "short", timeStyle: "medium" }) : "–");
const toInputValue = (ms: number) => {
  const d = new Date(ms - new Date(ms).getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 16);
};

function marketReducer(s: MarketState, m: ServerMessage): MarketState {
  return m.type === "hello" ? s : reduceMarket(s, m, Date.now());
}

export function ReplayApp() {
  const [cfg, setCfg] = useState<BackendConfig | null>(null);
  const [conn, setConn] = useState<ConnState>("idle");
  const [market, dispatch] = useReducer(marketReducer, undefined, emptyMarketState);
  const [rs, setRs] = useState<ReplayState>({ active: false });
  const [tf, setTf] = useState<Timeframe>("1m");
  const [start, setStart] = useState(() => toInputValue(Date.now() - 3 * 86_400_000 - (Date.now() % 3_600_000)));
  const [ticket, setTicket] = useState({ lots: 0.1, sl: 2, tp: 4, balance: 10000, commission: 7 });
  const [hotkeys, setHotkeys] = useState(DEFAULT_HOTKEYS);
  const [editing, setEditing] = useState<HotkeyAction | null>(null);
  const [showKeys, setShowKeys] = useState(false);
  const [overlays, setOverlays] = useState<Overlays>(DEFAULT_OVERLAYS);
  const client = useRef<BackendClient | null>(null);

  useEffect(() => {
    void loadConfig().then(setCfg);
    void store.get<typeof ticket>(TICKET_KEY).then((t) => t && setTicket((x) => ({ ...x, ...t })));
    void store.get<typeof DEFAULT_HOTKEYS>(HOTKEY_KEY).then((h) => h && setHotkeys({ ...DEFAULT_HOTKEYS, ...h }));
  }, []);

  useEffect(() => {
    if (!cfg) return;
    const c = connect(
      cfg,
      (m) => {
        if (m.type === "replay") dispatch(m.data);
        else if (m.type === "replay_state") setRs(m.data);
        else if (m.type === "symbol" || m.type === "ai_status") dispatch(m);
      },
      setConn,
    );
    client.current = c;
    return () => c.stop();
  }, [cfg]);

  const send = useCallback((m: Parameters<BackendClient["request"]>[0]) => client.current?.request(m), []);
  const saveTicket = (t: typeof ticket) => {
    setTicket(t);
    void store.set(TICKET_KEY, t);
  };

  const order = useCallback(
    (side: "buy" | "sell") => send({ type: "replay_order", side, volume: ticket.lots, slDistance: ticket.sl || null, tpDistance: ticket.tp || null }),
    [send, ticket],
  );
  const control = useCallback(
    (action: "pause" | "resume" | "speed" | "jump" | "stop", value?: number) => send({ type: "replay_control", action, value }),
    [send],
  );

  // Hotkeys (ignored while typing in a field)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const combo = comboOf(e);
      if (editing) {
        e.preventDefault();
        if (combo !== "Escape") {
          const next = { ...hotkeys, [editing]: combo };
          setHotkeys(next);
          void store.set(HOTKEY_KEY, next);
        }
        setEditing(null);
        return;
      }
      if ((e.target as HTMLElement).closest("input,textarea,select")) return;
      const a = actionFor(combo, hotkeys);
      if (!a || !rs.active) return;
      e.preventDefault();
      if (a === "buy") order("buy");
      else if (a === "sell") order("sell");
      else if (a === "closeAll") send({ type: "replay_close", id: "all" });
      else if (a === "pause") control(rs.paused ? "resume" : "pause");
      else if (a === "jump1m") control("jump", 60_000);
      else if (a === "jump15m") control("jump", 15 * 60_000);
      else if (a === "faster") control("speed", nextSpeed(rs.speed ?? 1, 1));
      else if (a === "slower") control("speed", nextSpeed(rs.speed ?? 1, -1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hotkeys, editing, rs, order, control, send]);

  const begin = () =>
    send({ type: "replay_start", startMs: new Date(start).getTime(), speed: 1, balance: ticket.balance, commissionPerLot: ticket.commission });

  const acc = rs.account;
  const contract = acc?.contractSize ?? market.symbol?.contractSize ?? 100;
  const risk = orderRisk(ticket.lots, contract, ticket.sl, ticket.tp, ticket.commission);
  const tick = market.tick;
  const trades = acc?.trades ?? [];

  return (
    <div className="copilot-root flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-tv-border bg-tv-panel px-3 py-2 text-xs">
        <b className="text-sm text-tv-text">Replay-trening</b>
        <span className="rounded border border-tv-amber/50 bg-tv-amber/15 px-1.5 py-px text-[10px] font-bold text-tv-amber">SIMULERT – INGEN EKTE ORDRE</span>
        <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="rounded border border-tv-border bg-tv-bg px-2 py-1 text-tv-text" />
        <button onClick={begin} disabled={conn !== "connected"} className="rounded bg-tv-blue px-3 py-1 text-white disabled:opacity-40">
          Start herfra
        </button>
        {rs.active && (
          <>
            <button onClick={() => control(rs.paused ? "resume" : "pause")} className="w-20 rounded border border-tv-border px-2 py-1 text-tv-text hover:bg-tv-hover">
              {rs.paused ? "▶ Spill" : "❚❚ Pause"}
            </button>
            {SPEEDS.map((s) => (
              <button key={s} onClick={() => control("speed", s)} className={`rounded px-2 py-1 ${rs.speed === s ? "bg-tv-hover text-tv-text" : "text-tv-muted hover:text-tv-text"}`}>
                {s}×
              </button>
            ))}
            {[
              [60_000, "+1m"],
              [5 * 60_000, "+5m"],
              [15 * 60_000, "+15m"],
              [3_600_000, "+1t"],
            ].map(([ms, l]) => (
              <button key={l} onClick={() => control("jump", ms as number)} className="rounded px-2 py-1 text-tv-muted hover:text-tv-text">
                {l}
              </button>
            ))}
            <button onClick={() => control("stop")} className="rounded px-2 py-1 text-tv-down hover:bg-tv-hover">Avslutt</button>
            <span className="tabular ml-auto font-mono text-sm text-tv-text">{hms(rs.clockMs)}</span>
          </>
        )}
        <button onClick={() => setShowKeys(true)} className="rounded px-2 py-1 text-tv-muted hover:text-tv-text">⌨ Hurtigtaster</button>
      </header>
      {rs.error && <p className="border-b border-tv-down/40 bg-tv-down/10 px-3 py-1 text-xs text-tv-down">{rs.error}</p>}
      {rs.active && rs.dataQuality !== "ticks" && (
        <p className="border-b border-tv-amber/40 bg-tv-amber/10 px-3 py-1 text-xs text-tv-amber">
          {rs.dataQuality === "synthetic"
            ? "Demomodus: syntetiske priser (backend kjører uten MT5)."
            : "Megleren har ikke tick-historikk så langt tilbake – bevegelsen inne i hvert minutt er en forenklet bane fra 1m-lysene."}
        </p>
      )}
      {rs.ended && <p className="border-b border-tv-border bg-tv-panel px-3 py-1 text-xs text-tv-muted">Ingen flere historiske data – replay er ferdig. Se oppsummeringen til høyre.</p>}

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex gap-1 border-b border-tv-border px-2 py-1 text-xs">
            {(["1m", "5m", "15m", "1h"] as Timeframe[]).map((k) => (
              <button key={k} onClick={() => setTf(k)} className={`rounded px-2 py-0.5 ${tf === k ? "bg-tv-hover text-tv-text" : "text-tv-muted"}`}>
                {k}
              </button>
            ))}
            <span className="mx-2" />
            <OverlayToggles value={overlays} onChange={setOverlays} />
            {tick && (
              <span className="tabular ml-auto font-mono text-tv-text">
                Bid {no(tick.bid, 2)} · Ask {no(tick.ask, 2)} · Spread {no(tick.spread, 2)}
              </span>
            )}
          </div>
          <ChartView
            candles={market.candles[tf]}
            tf={tf}
            analysis={market.analysis}
            ai={market.ai && market.ai.reasons.includes("replay") ? market.ai : null}
            overlays={overlays}
            nowMs={rs.clockMs}
            positions={acc?.positions ?? []}
            trades={trades}
          />
          {!rs.active && (
            <p className="p-4 text-sm text-tv-muted">
              Velg et tidspunkt i fortiden og trykk «Start herfra». Lysene bygges sekund for sekund av ekte historiske ticks fra MT5. Analysen og AI-en ser bare
              data fram til replay-klokka – aldri fremtiden.
            </p>
          )}
        </main>

        <aside className="w-[360px] shrink-0 space-y-3 overflow-y-auto border-l border-tv-border p-3 text-xs">
          <section className="space-y-2 rounded border border-tv-border bg-tv-panel p-2">
            <div className="grid grid-cols-3 gap-2">
              <Num label="Lot" value={ticket.lots} step={0.01} onChange={(v) => saveTicket({ ...ticket, lots: v })} />
              <Num label="SL (USD)" value={ticket.sl} step={0.1} onChange={(v) => saveTicket({ ...ticket, sl: v })} />
              <Num label="TP (USD)" value={ticket.tp} step={0.1} onChange={(v) => saveTicket({ ...ticket, tp: v })} />
            </div>
            <p className="text-tv-muted">
              {no(ticket.lots, 2)} lot = {no(risk.oz, 0)} oz · risiko ≈ {no(risk.risk, 0)} USD · mulig gevinst ≈ {no(risk.reward, 0)} USD
              {risk.rr != null && ` · R/R ${no(risk.rr, 2)}`} (inkl. kommisjon {no(ticket.commission, 0)} USD/lot)
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button disabled={!rs.active} onClick={() => order("buy")} className="rounded bg-tv-up py-2 font-semibold text-white disabled:opacity-40">
                BUY {tick ? no(tick.ask, 2) : ""} <span className="font-normal opacity-80">({hotkeys.buy})</span>
              </button>
              <button disabled={!rs.active} onClick={() => order("sell")} className="rounded bg-tv-down py-2 font-semibold text-white disabled:opacity-40">
                SELL {tick ? no(tick.bid, 2) : ""} <span className="font-normal opacity-80">({hotkeys.sell})</span>
              </button>
            </div>
          </section>

          {acc && (
            <section className="space-y-1">
              <p className="text-tv-text">
                Saldo {no(acc.balance, 2)} · Egenkapital <span className={acc.equity >= acc.balance ? "text-tv-up" : "text-tv-down"}>{no(acc.equity, 2)}</span> USD
              </p>
              {acc.positions.map((p) => (
                <div key={p.id} className="flex items-center gap-2 rounded bg-tv-panel px-2 py-1">
                  <b className={p.side === "buy" ? "text-tv-up" : "text-tv-down"}>{p.side === "buy" ? "LONG" : "SHORT"}</b>
                  <span className="text-tv-muted">{p.volume} @ {no(p.entry, 2)}</span>
                  <span className={`ml-auto ${p.profit >= 0 ? "text-tv-up" : "text-tv-down"}`}>{no(p.profit, 2)}</span>
                  <button onClick={() => send({ type: "replay_close", id: p.id })} className="rounded border border-tv-border px-1.5 text-tv-muted hover:text-tv-text">Lukk</button>
                </div>
              ))}
              {acc.positions.length > 1 && (
                <button onClick={() => send({ type: "replay_close", id: "all" })} className="text-tv-muted underline">Lukk alle ({hotkeys.closeAll})</button>
              )}
            </section>
          )}

          <SessionSummary trades={trades} />

          <section className="space-y-1">
            <div className="flex items-center">
              <h3 className="text-[10px] uppercase tracking-wider text-tv-muted">Analyse (bare data fram til replay-klokka)</h3>
              <button disabled={!rs.active} onClick={() => send({ type: "replay_ai" })} className="ml-auto rounded border border-tv-border px-2 py-0.5 text-tv-text disabled:opacity-40">
                Spør AI
              </button>
            </div>
            {market.ai && market.ai.reasons.includes("replay") && (
              <div className="rounded border border-tv-border bg-tv-panel p-2">
                <p className="text-tv-text">{market.ai.summary}</p>
                {market.ai.setup && (
                  <p className="text-tv-muted">
                    Mulig {market.ai.setup.direction} {no(market.ai.setup.entryLow, 2)}–{no(market.ai.setup.entryHigh, 2)}, invalidering {no(market.ai.setup.invalidation, 2)}, mål{" "}
                    {no(market.ai.setup.target, 2)}, R/R {no(market.ai.setup.rr, 1)}
                  </p>
                )}
                <p className="text-[10px] text-tv-muted">{no(market.ai.costNok, 2)} kr</p>
              </div>
            )}
            {market.analysis ? <AnalysisTab market={market} /> : <p className="text-tv-muted">Starter …</p>}
          </section>
        </aside>
      </div>

      {showKeys && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60" onClick={() => setShowKeys(false)}>
          <div className="w-96 space-y-2 rounded border border-tv-border bg-tv-panel p-4 text-xs" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-sm text-tv-text">Hurtigtaster i replay</h2>
            {(Object.keys(ACTION_LABEL) as HotkeyAction[]).map((a) => (
              <div key={a} className="flex items-center">
                <span className="text-tv-text">{ACTION_LABEL[a]}</span>
                <button onClick={() => setEditing(a)} className="ml-auto min-w-24 rounded border border-tv-border px-2 py-0.5 font-mono text-tv-text">
                  {editing === a ? "trykk en tast …" : hotkeys[a]}
                </button>
              </div>
            ))}
            <p className="text-tv-muted">Klikk og trykk ny tast (Esc avbryter). SL og TP legges automatisk på hver ordre. Gjelder bare replay – ekte handler plasseres aldri.</p>
            <button onClick={() => { setHotkeys(DEFAULT_HOTKEYS); void store.set(HOTKEY_KEY, DEFAULT_HOTKEYS); }} className="text-tv-muted underline">Tilbakestill</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Num({ label, value, step, onChange }: { label: string; value: number; step: number; onChange(v: number): void }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-tv-muted">{label}</span>
      <input type="number" min={0} step={step} value={value} onChange={(e) => onChange(Math.max(0, Number(e.target.value)))} className="w-full rounded border border-tv-border bg-tv-bg px-2 py-1 text-tv-text" />
    </label>
  );
}

function SessionSummary({ trades }: { trades: NonNullable<ReplayState["account"]>["trades"] }) {
  if (!trades.length) return null;
  const net = trades.reduce((a, t) => a + t.net, 0);
  const wins = trades.filter((t) => t.net > 0);
  const losses = trades.filter((t) => t.net < 0);
  const gl = -losses.reduce((a, t) => a + t.net, 0);
  const rs = trades.map((t) => t.r_multiple).filter((r): r is number => r != null);
  return (
    <section className="space-y-1">
      <h3 className="text-[10px] uppercase tracking-wider text-tv-muted">Denne økta</h3>
      <p className="text-tv-text">
        {trades.length} handler · <span className={net >= 0 ? "text-tv-up" : "text-tv-down"}>{no(net, 2)} USD</span> · treff {Math.round((wins.length / trades.length) * 100)} %
        {gl > 0 && ` · PF ${no(wins.reduce((a, t) => a + t.net, 0) / gl, 2)}`}
        {rs.length > 0 && ` · snitt ${no(rs.reduce((a, b) => a + b, 0) / rs.length, 2)} R`}
      </p>
      <table className="tabular w-full">
        <tbody>
          {[...trades].reverse().slice(0, 12).map((t) => (
            <tr key={t.id} className="border-t border-tv-border/50">
              <td className={t.side === "buy" ? "text-tv-up" : "text-tv-down"}>{t.side === "buy" ? "L" : "S"}</td>
              <td className="text-tv-muted">{new Date(t.open_ms).toLocaleTimeString("nb-NO")}</td>
              <td>{no(t.entry, 2)}→{no(t.exit, 2)}</td>
              <td className="text-tv-muted">{t.exit_reason}</td>
              <td className={`text-right ${t.net >= 0 ? "text-tv-up" : "text-tv-down"}`}>{no(t.net, 2)}</td>
              <td className="text-right text-tv-muted" title="Beste / verste flytende resultat underveis">{no(t.mfe, 0)}/{no(t.mae, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
