import { Fragment, useCallback, useEffect, useState } from "react";
import type { BackendConfig } from "../shared/backendClient";
import { api, loadConfig } from "../pages/conn";
import { BarChart, LineChart } from "../pages/charts";
import { no } from "../panel/describe";

type Tab = "oversikt" | "analyse" | "handler" | "coach" | "gjennomganger";
const TABS: [Tab, string][] = [
  ["oversikt", "Oversikt"],
  ["analyse", "Analyse"],
  ["handler", "Handler"],
  ["coach", "Coach"],
  ["gjennomganger", "Gjennomganger"],
];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

const d = (ms: number | null) => (ms ? new Date(ms).toLocaleString("nb-NO", { dateStyle: "short", timeStyle: "short" }) : "–");
const money = (v: number | null | undefined) => (v == null ? "–" : no(v, 2));
const pct = (v: number | null | undefined) => (v == null ? "–" : `${no(v * 100, 1)} %`);
const ci = (c: [number, number] | null | undefined, f: (v: number) => string) => (c ? `${f(c[0])} – ${f(c[1])}` : "–");
const pnl = (v: number) => (v > 0 ? "text-tv-up" : v < 0 ? "text-tv-down" : "text-tv-text");

export function JournalApp() {
  const [cfg, setCfg] = useState<BackendConfig | null>(null);
  const [tab, setTab] = useState<Tab>("oversikt");
  const [days, setDays] = useState<number | null>(30);
  const [direction, setDirection] = useState<string>("");
  const [setup, setSetup] = useState<string>("");
  const [stats, setStats] = useState<Any>(null);
  const [trades, setTrades] = useState<Any[]>([]);
  const [coach, setCoach] = useState<Any>(null);
  const [reviews, setReviews] = useState<Any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => void loadConfig().then(setCfg), []);

  const load = useCallback(async () => {
    if (!cfg) return;
    setError(null);
    const q = new URLSearchParams();
    if (days) q.set("days", String(days));
    if (direction) q.set("direction", direction);
    if (setup) q.set("setup", setup);
    try {
      const [s, t, c, r] = await Promise.all([
        api<Any>(cfg, `/api/journal/stats?${q}`),
        api<Any>(cfg, `/api/journal/trades?limit=500${days ? `&days=${days}` : ""}`),
        api<Any>(cfg, "/api/coach/summary"),
        api<Any>(cfg, "/api/coach/reviews"),
      ]);
      setStats(s);
      setTrades(t.trades);
      setCoach(c);
      setReviews(r.reviews);
    } catch (e) {
      setError(`Får ikke kontakt med backend: ${(e as Error).message}. Kjører den, og er tokenet lagret i innstillingene?`);
    }
  }, [cfg, days, direction, setup]);

  useEffect(() => void load(), [load]);

  const sync = async () => {
    if (!cfg) return;
    setBusy(true);
    try {
      await api(cfg, "/api/journal/sync", { method: "POST" });
      await api(cfg, "/api/coach/refresh", { method: "POST" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setups = Array.from(new Set(trades.map((t) => t.setup).filter(Boolean))) as string[];

  return (
    <div className="copilot-root mx-auto max-w-6xl space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold text-tv-text">Journal og coach</h1>
        <span className="text-xs text-tv-muted">XAUUSD · data fra MT5 (kun lesing)</span>
        <button onClick={sync} disabled={busy} className="ml-auto rounded bg-tv-blue px-3 py-1.5 text-xs text-white disabled:opacity-50">
          {busy ? "Oppdaterer …" : "Hent nye handler"}
        </button>
      </header>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={`rounded px-3 py-1.5 ${tab === k ? "bg-tv-hover text-tv-text" : "text-tv-muted hover:text-tv-text"}`}>
            {label}
          </button>
        ))}
        <span className="mx-2 h-4 w-px bg-tv-border" />
        <Select value={String(days ?? "")} onChange={(v) => setDays(v ? Number(v) : null)} options={[["7", "7 dager"], ["30", "30 dager"], ["90", "90 dager"], ["365", "1 år"], ["", "Alt"]]} />
        <Select value={direction} onChange={setDirection} options={[["", "Long og short"], ["long", "Bare long"], ["short", "Bare short"]]} />
        <Select value={setup} onChange={setSetup} options={[["", "Alle oppsett"], ...setups.map((s) => [s, s] as [string, string]), ["(uten tag)", "(uten tag)"]]} />
      </div>

      {error && <p className="rounded border border-tv-down/40 bg-tv-down/10 p-2 text-xs text-tv-down">{error}</p>}
      {!stats ? (
        <p className="text-xs text-tv-muted">Laster …</p>
      ) : tab === "oversikt" ? (
        <Overview stats={stats} />
      ) : tab === "analyse" ? (
        <Breakdown stats={stats} />
      ) : tab === "handler" ? (
        <Trades trades={trades} cfg={cfg!} onChanged={load} />
      ) : tab === "coach" ? (
        <Coach coach={coach} />
      ) : (
        <Reviews reviews={reviews} cfg={cfg!} onChanged={load} />
      )}
    </div>
  );
}

function Select({ value, onChange, options }: { value: string; onChange(v: string): void; options: [string, string][] }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="rounded border border-tv-border bg-tv-panel px-2 py-1 text-tv-text">
      {options.map(([v, l]) => (
        <option key={v + l} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}

function Tile({ label, value, sub, cls = "text-tv-text" }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="rounded border border-tv-border bg-tv-panel p-3">
      <div className="text-[10px] uppercase tracking-wider text-tv-muted">{label}</div>
      <div className={`tabular mt-1 text-xl font-semibold ${cls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[10px] text-tv-muted">{sub}</div>}
    </div>
  );
}

function Overview({ stats }: { stats: Any }) {
  if (stats.empty) return <p className="text-sm text-tv-muted">Ingen lukkede handler i valgt periode. Trykk «Hent nye handler» for å importere fra MT5.</p>;
  const s = stats.summary;
  const c = stats.costs;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Resultat" value={money(s.net)} cls={pnl(s.net)} sub={`${s.n} handler`} />
        <Tile label="Treffprosent" value={pct(s.winRate)} sub={`95 %: ${ci(s.winRateCi, pct)}`} />
        <Tile label="Profit factor" value={s.profitFactor == null ? "–" : no(s.profitFactor, 2)} />
        <Tile label="Forventning per handel" value={money(s.expectancy)} cls={pnl(s.expectancy)} sub={`95 %: ${ci(s.expectancyCi, money)}`} />
        <Tile label="Snitt gevinst / tap" value={`${money(s.avgWin)} / ${money(s.avgLoss)}`} />
        <Tile label="Snitt R" value={s.expectancyR == null ? "–" : `${no(s.expectancyR, 2)} R`} sub={s.expectancyRCi ? `95 %: ${ci(s.expectancyRCi, (v) => no(v, 2))}` : "krever SL ved inngang"} />
        <Tile label="Maks drawdown" value={money(-s.maxDrawdown)} cls="text-tv-down" />
        <Tile label="Lengste serier" value={`${s.streaks.maxWins} V / ${s.streaks.maxLosses} T`} sub={`nå: ${s.streaks.current > 0 ? `${s.streaks.current} gevinster` : s.streaks.current < 0 ? `${-s.streaks.current} tap` : "–"}`} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <LineChart title="Egenkapitalkurve (lukkede handler)" points={stats.equity.map((p: Any, i: number) => ({ x: i, y: p.equity, t: p.t }))} label={(p) => `Handel ${p.x + 1}\nSum: ${money(p.y)}`} />
        <LineChart title="Drawdown" color="#ef5350" fill points={stats.equity.map((p: Any, i: number) => ({ x: i, y: p.drawdown }))} label={(p) => `Handel ${p.x + 1}\nDrawdown: ${money(p.y)}`} />
        <BarChart title="Resultat per dag" bars={stats.daily.slice(-40).map((x: Any) => ({ key: x.day.slice(5), v: x.net }))} label={(b) => `${b.key}\n${money(b.v)}`} />
        <BarChart
          title={`Fordeling (${stats.distribution.unit === "R" ? "R per handel" : "resultat per handel"})`}
          bars={stats.distribution.bins.map((b: Any) => ({ key: no(b.from, stats.distribution.unit === "R" ? 1 : 0), v: b.count }))}
          label={(b) => `Fra ${b.key}: ${b.v} handler`}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Kommisjon" value={money(c.commission)} />
        <Tile label="Swap" value={money(c.swap)} />
        <Tile label="Gebyrer" value={money(c.fee)} />
        <Tile label="Spread (estimat)" value={c.spreadEstimate == null ? "–" : money(-c.spreadEstimate)} sub="fra spread ved inngang" />
      </div>
    </div>
  );
}

function GroupTable({ title, rows }: { title: string; rows: Any[] }) {
  return (
    <div className="rounded border border-tv-border bg-tv-panel p-3">
      <h3 className="mb-2 text-xs text-tv-muted">{title}</h3>
      <table className="tabular w-full text-xs">
        <thead className="text-tv-muted">
          <tr>
            <th className="text-left font-normal" />
            <th className="text-right font-normal">n</th>
            <th className="text-right font-normal">Treff</th>
            <th className="text-right font-normal">Snitt R</th>
            <th className="text-right font-normal">PF</th>
            <th className="text-right font-normal">Resultat</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.key)} className="border-t border-tv-border/50">
              <td className="py-1 text-tv-text">{String(r.key)}</td>
              <td className="text-right text-tv-muted">{r.n}</td>
              <td className="text-right">{pct(r.winRate)}</td>
              <td className="text-right">{r.avgR == null ? "–" : no(r.avgR, 2)}</td>
              <td className="text-right">{r.profitFactor == null ? "–" : no(r.profitFactor, 2)}</td>
              <td className={`text-right ${pnl(r.net)}`}>{money(r.net)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] text-tv-muted">Små grupper (n &lt; 20) sier lite – se Coach for statistisk testede mønstre.</p>
    </div>
  );
}

function Breakdown({ stats }: { stats: Any }) {
  if (stats.empty) return <p className="text-sm text-tv-muted">Ingen data.</p>;
  return (
    <div className="space-y-3">
      <BarChart title="Resultat per time (norsk tid, inngang)" bars={stats.byHour.map((g: Any) => ({ key: String(g.key).padStart(2, "0"), v: g.net }))} label={(b) => `Kl. ${b.key}\n${money(b.v)}`} />
      <div className="grid gap-3 md:grid-cols-2">
        <GroupTable title="Long mot short" rows={stats.byDirection} />
        <GroupTable title="Børsøkt" rows={stats.bySession} />
        <GroupTable title="Ukedag" rows={stats.byWeekday} />
        <GroupTable title="Oppsett (din tag)" rows={stats.bySetup} />
      </div>
    </div>
  );
}

function Trades({ trades, cfg, onChanged }: { trades: Any[]; cfg: BackendConfig; onChanged(): void }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!trades.length) return <p className="text-sm text-tv-muted">Ingen handler i perioden.</p>;
  return (
    <div className="overflow-x-auto rounded border border-tv-border bg-tv-panel">
      <table className="tabular w-full min-w-[720px] text-xs">
        <thead className="text-tv-muted">
          <tr className="text-left">
            {["Åpnet", "Retning", "Lot", "Inngang", "Utgang", "SL", "Resultat", "R", "Utgang via", "Økt", "Oppsett"].map((h) => (
              <th key={h} className="px-2 py-2 font-normal">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <Fragment key={t.position_id}>
              <tr onClick={() => setOpen(open === t.position_id ? null : t.position_id)} className="cursor-pointer border-t border-tv-border/60 hover:bg-tv-hover">
                <td className="px-2 py-1.5">{d(t.open_ms)}</td>
                <td className={t.direction === "long" ? "text-tv-up" : "text-tv-down"}>{t.direction}</td>
                <td>{t.volume}</td>
                <td>{no(t.entry_price, 2)}</td>
                <td>{t.exit_price == null ? "åpen" : no(t.exit_price, 2)}</td>
                <td>{t.sl ? no(t.sl, 2) : <span className="text-tv-down">ingen</span>}</td>
                <td className={pnl(t.net)}>{money(t.net)}</td>
                <td>{t.r_multiple == null ? "–" : no(t.r_multiple, 2)}</td>
                <td className="text-tv-muted">{{ tp: "TP", sl: "SL", manual: "manuelt", stopout: "stop out" }[t.exit_reason as string] ?? "–"}</td>
                <td className="text-tv-muted">{t.session}</td>
                <td>{t.setup || <span className="text-tv-muted">–</span>}</td>
              </tr>
              {open === t.position_id && (
                <tr className="bg-tv-bg">
                  <td colSpan={11} className="p-3">
                    <TradeDetail t={t} cfg={cfg} onChanged={onChanged} />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeDetail({ t, cfg, onChanged }: { t: Any; cfg: BackendConfig; onChanged(): void }) {
  const [note, setNote] = useState<string>(t.note ?? "");
  const [setupTag, setSetupTag] = useState<string>(t.setup ?? "");
  const [tags, setTags] = useState<string>((t.tags ?? []).join(", "));
  const [saved, setSaved] = useState(false);
  const save = async () => {
    await api(cfg, `/api/journal/trades/${t.position_id}`, {
      method: "PUT",
      body: JSON.stringify({ note, setup: setupTag, tags: tags.split(",").map((x) => x.trim()).filter(Boolean) }),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
    onChanged();
  };
  const upload = async (file: File) => {
    const dataUrl = await new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result));
      r.readAsDataURL(file);
    });
    await api(cfg, `/api/journal/trades/${t.position_id}/screenshot`, { method: "POST", body: JSON.stringify({ dataUrl }) });
    onChanged();
  };
  const ctx = t.context;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="space-y-2" onPaste={(e) => {
        const f = Array.from(e.clipboardData.files).find((x) => x.type.startsWith("image/"));
        if (f) void upload(f);
      }}>
        <label className="block text-[10px] uppercase tracking-wider text-tv-muted">Notat</label>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={4} className="w-full rounded border border-tv-border bg-tv-panel p-2 text-tv-text" placeholder="Hva så du? Fulgte du planen? (Lim inn skjermbilde med Ctrl+V)" />
        <div className="flex gap-2">
          <input value={setupTag} onChange={(e) => setSetupTag(e.target.value)} placeholder="Oppsett, f.eks. pullback" className="flex-1 rounded border border-tv-border bg-tv-panel px-2 py-1 text-tv-text" />
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Tagger, kommaseparert" className="flex-1 rounded border border-tv-border bg-tv-panel px-2 py-1 text-tv-text" />
        </div>
        <div className="flex items-center gap-2">
          <button onClick={save} className="rounded bg-tv-blue px-3 py-1 text-white">{saved ? "Lagret ✓" : "Lagre"}</button>
          <label className="cursor-pointer rounded border border-tv-border px-3 py-1 text-tv-text hover:bg-tv-hover">
            Legg til skjermbilde
            <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          {(t.screenshots ?? []).map((name: string) => (
            <Shot key={name} cfg={cfg} name={name} />
          ))}
        </div>
      </div>
      <div className="space-y-2 text-xs">
        {t.feedback && (
          <div>
            <p className="text-[10px] uppercase tracking-wider text-tv-muted">Coach-tilbakemelding</p>
            <p className="text-tv-text">{t.feedback.headline}</p>
            <ul>
              {t.feedback.points.map((p: Any) => (
                <li key={p.text} className={{ good: "text-tv-up", bad: "text-tv-down", warn: "text-tv-amber", neutral: "text-tv-muted" }[p.tone as string]}>· {p.text}</li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <p className="text-[10px] uppercase tracking-wider text-tv-muted">Markedet ved inngang (ingen fremtidsdata)</p>
          {ctx ? (
            <p className="text-tv-text">
              {Object.entries(ctx.tf ?? {}).map(([k, v]: [string, Any]) => `${k}: ${{ up: "opp", down: "ned", sideways: "sideveis" }[v.trend as string] ?? v.trend} (RSI ${v.rsi ?? "–"})`).join(" · ")}
              {ctx.with15m && ` · ${ctx.with15m === "with" ? "med" : ctx.with15m === "against" ? "mot" : "nøytral til"} 15m-trend`}
            </p>
          ) : (
            <p className="text-tv-muted">Ikke beregnet ennå.</p>
          )}
        </div>
        <p className="text-tv-muted">
          Brutto {money(t.gross)} · kommisjon {money(t.commission)} · swap {money(t.swap)} · risiko ved SL {money(t.risk_money)}
        </p>
      </div>
    </div>
  );
}

function Shot({ cfg, name }: { cfg: BackendConfig; name: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let u: string | null = null;
    void fetch(`${cfg.url}/api/journal/screenshots/${name}`, { headers: { Authorization: `Bearer ${cfg.token}` } })
      .then((r) => r.blob())
      .then((b) => {
        u = URL.createObjectURL(b);
        setUrl(u);
      });
    return () => {
      if (u) URL.revokeObjectURL(u);
    };
  }, [cfg, name]);
  return url ? (
    <a href={url} target="_blank" rel="noreferrer">
      <img src={url} alt="Skjermbilde" className="h-24 rounded border border-tv-border object-cover" />
    </a>
  ) : null;
}

function Coach({ coach }: { coach: Any }) {
  if (!coach) return <p className="text-xs text-tv-muted">Laster …</p>;
  const ai = coach.ai?.all;
  return (
    <div className="space-y-4 text-xs">
      <p className="text-tv-muted">
        Basert på {coach.trades} handler. Et mønster vises bare når begge grupper har minst {coach.minSample} handler og 95 %-intervallet for forskjellen ikke
        inneholder null. «Foreløpig» = under 50 handler i minste gruppe. Språkmodellen trenes ikke om; coachen lærer ved å lagre og analysere dataene dine.
      </p>
      <Section title="Statistisk underbygde mønstre">
        {coach.insights.length === 0 ? <Empty text="Ingen sikre mønstre ennå – fortsett å handle og registrere." /> : coach.insights.map((i: Any) => (
          <div key={i.id} className={`rounded border-l-2 bg-tv-panel p-2 ${i.kind === "strength" ? "border-tv-up" : i.kind === "weakness" ? "border-tv-down" : "border-tv-amber"}`}>
            <p className="text-tv-text">{i.title} <span className="text-tv-muted">· {i.strength}</span></p>
            <p className="text-tv-muted">{i.detail}</p>
          </div>
        ))}
      </Section>
      <Section title="Kunnskapsbase (husker over tid)">
        {coach.knowledge.length === 0 ? <Empty text="Tom." /> : (
          <table className="w-full">
            <tbody>
              {coach.knowledge.map((k: Any) => (
                <tr key={k.key} className="border-t border-tv-border/50">
                  <td className="py-1 text-tv-text">{k.title}</td>
                  <td className="text-tv-muted">{k.status === "active" ? "aktiv" : "ikke bekreftet på 30 dager"}</td>
                  <td className="text-right text-tv-muted">bekreftet {k.timesConfirmed}× · sist {d(k.lastConfirmed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
      <Section title="Kandidatregler – walk-forward-test (ut-av-utvalg)">
        <table className="tabular w-full">
          <tbody>
            {coach.candidates.map((c: Any) => (
              <tr key={c.id} className="border-t border-tv-border/50">
                <td className="py-1 text-tv-text">{c.title}</td>
                <td className={c.recommended ? "text-tv-up" : "text-tv-muted"}>{c.recommended ? "bestått" : c.reason}</td>
                <td className="text-right text-tv-muted">{c.oosGain == null ? "" : `${no(c.oosGain, 2)} (${ci(c.oosCi, (v) => no(v, 2))})`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-tv-muted">En regel anbefales bare hvis den forbedret resultatene i de fleste treningsperioder og forbedringen holdt på data den ikke ble valgt på.</p>
      </Section>
      <Section title="Har noe sluttet å virke?">
        {coach.drift.length === 0 ? <Empty text="For lite data til å vurdere ennå (trenger 40+ handler per gruppe)." /> : coach.drift.map((x: Any) => (
          <p key={x.group} className={x.status === "worse" ? "text-tv-down" : "text-tv-text"}>
            {x.group}: siste 20 snitt {no(x.recentMean, 2)} mot tidligere {no(x.beforeMean, 2)} · {x.status === "worse" ? "svakere" : x.status === "better" ? "bedre" : "stabilt"}
          </p>
        ))}
      </Section>
      <Section title="Hvor godt traff AI-forslagene?">
        {!ai || !ai.setups ? <Empty text="Ingen evaluerte AI-forslag ennå (de vurderes 30+ minutter etter at de ble gitt)." /> : (
          <>
            <p className="text-tv-text">
              {ai.setups} forslag · {ai.resolved} avgjort · treff (mål før invalidering) {pct(ai.hitRate)} ({ci(ai.hitRateCi, pct)}) · snitt {ai.meanR == null ? "–" : `${no(ai.meanR, 2)} R`} · {ai.notTriggered} ikke utløst
            </p>
            <p className="text-tv-muted">{coach.ai.note}</p>
          </>
        )}
      </Section>
      <Section title="Versjonshistorikk">
        <table className="w-full">
          <tbody>
            {coach.versions.map((v: Any) => (
              <tr key={v.component + v.version} className="border-t border-tv-border/50">
                <td className="py-1 text-tv-text">{{ ai_prompt: "AI-instruks", analysis_engine: "Analysemotor", risk_rules: "Risikoregler" }[v.component as string] ?? v.component}</td>
                <td className="text-tv-text">{v.version}</td>
                <td className="text-tv-muted">{d(v.firstSeen)} – {d(v.lastSeen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-tv-muted">Tilbake til en eldre AI-instruks: sett COPILOT_AI_PROMPT_VERSION i .env. Treffsikkerhet per versjon vises over når det finnes data.</p>
      </Section>
    </div>
  );
}

function Reviews({ reviews, cfg, onChanged }: { reviews: Any[]; cfg: BackendConfig; onChanged(): void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const make = async (period: "day" | "week") => {
    setBusy(period);
    try {
      await api(cfg, "/api/coach/reviews", { method: "POST", body: JSON.stringify({ period, useAi: true }) });
      onChanged();
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-3 text-xs">
      <div className="flex gap-2">
        <button onClick={() => make("day")} disabled={!!busy} className="rounded bg-tv-blue px-3 py-1.5 text-white disabled:opacity-50">{busy === "day" ? "Lager …" : "Lag dagsrapport nå"}</button>
        <button onClick={() => make("week")} disabled={!!busy} className="rounded border border-tv-border px-3 py-1.5 text-tv-text disabled:opacity-50">{busy === "week" ? "Lager …" : "Lag ukesrapport nå"}</button>
        <span className="self-center text-tv-muted">Lages også automatisk kl. 22:30 på handelsdager og lørdag for uka.</span>
      </div>
      {reviews.length === 0 ? <Empty text="Ingen rapporter ennå." /> : reviews.map((r) => (
        <article key={r.id} className="space-y-2 rounded border border-tv-border bg-tv-panel p-3">
          <h3 className="text-sm text-tv-text">{r.period === "day" ? "Dag" : "Uke"}: {r.label}</h3>
          {r.stats?.n ? (
            <p className="text-tv-muted">
              {r.stats.n} handler · resultat <span className={pnl(r.stats.net)}>{money(r.stats.net)}</span> · treff {pct(r.stats.winRate)} · snitt R {r.stats.avgR == null ? "–" : no(r.stats.avgR, 2)} ·
              SL brukt {r.adherence?.withSlPct ?? "–"} %
            </p>
          ) : <p className="text-tv-muted">Ingen handler i perioden.</p>}
          {r.narrative && (
            <div className="space-y-1">
              <p className="text-tv-text">{r.narrative.summary}</p>
              <p className="text-tv-up">Bra: {r.narrative.went_well.join(" · ")}</p>
              <p className="text-tv-amber">Forbedre: {r.narrative.improve.join(" · ")}</p>
              <p className="text-tv-text">Fokus neste gang: {r.narrative.focus_next}</p>
            </div>
          )}
          {r.narrativeError && <p className="text-tv-muted">AI-tekst ikke laget: {r.narrativeError}</p>}
          {r.suggestions?.length > 0 && (
            <ul className="list-disc pl-4 text-tv-text">
              {r.suggestions.map((s: string) => <li key={s}>{s}</li>)}
            </ul>
          )}
        </article>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h2 className="text-[11px] uppercase tracking-wider text-tv-muted">{title}</h2>
      {children}
    </section>
  );
}

const Empty = ({ text }: { text: string }) => <p className="text-tv-muted">{text}</p>;
