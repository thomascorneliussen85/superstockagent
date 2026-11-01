import { useState } from "react";
import type { MarketState } from "../../shared/marketState";
import { TIMEFRAMES, type LevelInfo, type TfAnalysis, type Timeframe } from "../../shared/protocol";
import { eventText, no, PATTERN_TEXT, STRUCTURE_TEXT, summarize, TREND_TEXT } from "../describe";
import { useNow } from "../usePanel";

const trendCls = (l?: string) => (l === "up" ? "text-tv-up" : l === "down" ? "text-tv-down" : "text-tv-muted");
const arrow = (l?: string) => (l === "up" ? "▲" : l === "down" ? "▼" : "◆");

export function AnalysisTab({ market }: { market: MarketState }) {
  const [tf, setTf] = useState<Timeframe>("1m");
  const now = useNow(1000);
  const a = market.analysis;
  const d = market.symbol?.digits ?? 2;
  if (!a) return <p className="text-xs text-tv-muted">Venter på første analyse…</p>;
  const sel = a.timeframes[tf];
  const price = market.tick?.bid ?? a.price?.bid ?? null;
  const age = market.analysisAt ? Math.max(0, (now - market.analysisAt) / 1000) : null;

  return (
    <div className="space-y-3">
      {/* Multi-timeframe overview */}
      <table className="tabular w-full text-xs">
        <thead className="text-tv-muted">
          <tr>
            <th className="text-left font-normal">TF</th>
            <th className="text-left font-normal">Trend</th>
            <th className="text-right font-normal">RSI</th>
            <th className="text-right font-normal">EMA</th>
            <th className="text-right font-normal">ST</th>
            <th className="text-right font-normal">Vol.</th>
          </tr>
        </thead>
        <tbody>
          {TIMEFRAMES.map((k) => (
            <OverviewRow key={k} a={a.timeframes[k]} selected={k === tf} onSelect={() => setTf(k)} />
          ))}
        </tbody>
      </table>

      {/* Rule-based Norwegian summary */}
      <section className="rounded border border-tv-border bg-tv-panel p-2">
        <div className="mb-1 flex items-center gap-1">
          {TIMEFRAMES.map((k) => (
            <button
              key={k}
              onClick={() => setTf(k)}
              className={`rounded px-1.5 py-px text-[11px] ${k === tf ? "bg-tv-blue text-white" : "text-tv-muted hover:bg-tv-hover"}`}
            >
              {k}
            </button>
          ))}
          <span className="ml-auto text-[10px] text-tv-muted">{age == null ? "" : `oppdatert ${age.toFixed(0)} s siden`}</span>
        </div>
        <ul className="space-y-0.5 text-xs leading-snug text-tv-text">
          {summarize(a, tf, d).map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
        <p className="mt-1.5 text-[10px] text-tv-muted">Regelbasert oppsummering av fakta – ikke en prognose eller handelsanbefaling.</p>
      </section>

      {sel && !sel.insufficient && <Details a={sel} d={d} price={price} />}

      {/* Spread */}
      {a.spread && (
        <section className="text-xs">
          <H>Spread og kostnad</H>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5">
            <span>
              Nå <b className={spreadCls(a.spread.state)}>{no(a.spread.current, d)}</b> ({a.spread.points} pts)
            </span>
            {a.spread.median != null && <span className="text-tv-muted">median {no(a.spread.median, d)}</span>}
            <span className="text-tv-muted">
              ≈ {no(a.spread.costPerLot, 0)} {a.spread.currency} per 1,00 lot per handel
            </span>
          </div>
        </section>
      )}

      {/* Event log */}
      <section className="text-xs">
        <H>Hendelser (lukkede lys)</H>
        {a.recentEvents.length === 0 ? (
          <p className="text-tv-muted">Ingen brudd registrert siden oppstart.</p>
        ) : (
          <ul className="space-y-0.5">
            {a.recentEvents.slice(0, 8).map((e, i) => (
              <li key={`${e.tf}-${e.t}-${e.type}-${i}`} className="flex gap-2">
                <span className="tabular w-10 shrink-0 text-tv-muted">{e.t ? hhmm(e.t) : ""}</span>
                <span className="w-7 shrink-0 text-tv-muted">{e.tf}</span>
                <span className={e.type.endsWith("up") ? "text-tv-up" : "text-tv-down"}>{eventText(e, d)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function OverviewRow({ a, selected, onSelect }: { a: TfAnalysis; selected: boolean; onSelect(): void }) {
  if (!a || a.insufficient) {
    return (
      <tr className="cursor-pointer" onClick={onSelect}>
        <td>{a?.tf}</td>
        <td colSpan={5} className="text-tv-muted">for lite data</td>
      </tr>
    );
  }
  const stack = a.emaStack === "bull" ? "▲" : a.emaStack === "bear" ? "▼" : "◆";
  const stackCls = a.emaStack === "bull" ? "text-tv-up" : a.emaStack === "bear" ? "text-tv-down" : "text-tv-muted";
  const st = a.supertrend?.dir;
  return (
    <tr onClick={onSelect} className={`cursor-pointer ${selected ? "bg-tv-hover" : "hover:bg-tv-panel"}`}>
      <td className="py-0.5 pl-1">{a.tf}</td>
      <td className={trendCls(a.trend?.label)}>
        {arrow(a.trend?.label)} {a.trend ? TREND_TEXT[a.trend.label].split(" ")[0] : "–"}
      </td>
      <td className={`text-right ${rsiCls(a.rsi)}`}>{no(a.rsi, 0)}</td>
      <td className={`text-right ${stackCls}`} title="EMA 9/20/50-rekkefølge">{stack}</td>
      <td className={`text-right ${st === 1 ? "text-tv-up" : st === -1 ? "text-tv-down" : ""}`}>
        {st === 1 ? "▲" : st === -1 ? "▼" : "–"}
      </td>
      <td className="pr-1 text-right text-tv-muted">{a.volatility === "high" ? "høy" : a.volatility === "low" ? "lav" : "norm"}</td>
    </tr>
  );
}

function Details({ a, d, price }: { a: TfAnalysis; d: number; price: number | null }) {
  const dist = (lv: LevelInfo) => (price == null ? "" : ` (${no(lv.price - price, d)})`);
  return (
    <section className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
      <div>
        <H>Indikatorer {a.tf}</H>
        <Row k="EMA 9" v={no(a.ema?.["9"], d)} />
        <Row k="EMA 20" v={no(a.ema?.["20"], d)} />
        <Row k="EMA 50" v={no(a.ema?.["50"], d)} />
        <Row k="EMA 200" v={a.ema?.["200"] == null ? "for lite data" : no(a.ema["200"], d)} />
        <Row k="RSI 14" v={no(a.rsi, 1)} />
        <Row k="ATR 14" v={`${no(a.atr, d)}${a.atrPercentile != null ? ` · p${a.atrPercentile}` : ""}`} />
        <Row k="Supertrend" v={`${a.supertrend?.dir === 1 ? "opp" : a.supertrend?.dir === -1 ? "ned" : "–"} ${no(a.supertrend?.value, d)}`} />
        <Row k="Tick-volum" v={a.tickVolumeRatio == null ? "–" : `${no(a.tickVolumeRatio, 1)}× snitt`} />
      </div>
      <div>
        <H>Struktur</H>
        <p className="mb-1 text-tv-text">
          {a.structure ? STRUCTURE_TEXT[a.structure.label] : "–"}
          {a.structure?.highs && ` (${a.structure.highs}/${a.structure.lows ?? "–"})`}
        </p>
        <H>Motstand</H>
        {a.levels?.resistance.length ? (
          a.levels.resistance.map((lv) => <Row key={lv.price} k={no(lv.price, d)} v={`${lv.touches}×${dist(lv)}`} cls="text-tv-down" />)
        ) : (
          <p className="text-tv-muted">–</p>
        )}
        <H>Støtte</H>
        {a.levels?.support.length ? (
          a.levels.support.map((lv) => <Row key={lv.price} k={no(lv.price, d)} v={`${lv.touches}×${dist(lv)}`} cls="text-tv-up" />)
        ) : (
          <p className="text-tv-muted">–</p>
        )}
      </div>
      <div className="col-span-2">
        <H>Likviditet (like topper/bunner)</H>
        <p className="text-tv-text">
          Over: {a.liquidity?.above.map((l) => no(l.price, d)).join(", ") || "–"} · Under:{" "}
          {a.liquidity?.below.map((l) => no(l.price, d)).join(", ") || "–"}
        </p>
        {a.patterns && a.patterns.length > 0 && (
          <p className="mt-1 text-tv-text">Mønster: {a.patterns.map((p) => PATTERN_TEXT[p] ?? p).join(", ")}</p>
        )}
      </div>
    </section>
  );
}

const H = ({ children }: { children: React.ReactNode }) => (
  <h3 className="mb-0.5 mt-1 text-[10px] uppercase tracking-wider text-tv-muted">{children}</h3>
);

function Row({ k, v, cls = "text-tv-text" }: { k: string; v: string; cls?: string }) {
  return (
    <div className="tabular flex justify-between gap-2">
      <span className={cls === "text-tv-text" ? "text-tv-muted" : cls}>{k}</span>
      <span className="text-right text-tv-text">{v}</span>
    </div>
  );
}

const rsiCls = (v?: number | null) => (v == null ? "" : v >= 70 ? "text-tv-down" : v <= 30 ? "text-tv-up" : "");
const spreadCls = (s: string | null) => (s === "high" ? "text-tv-down" : s === "elevated" ? "text-tv-amber" : "text-tv-text");
const hhmm = (t: number) => new Date(t).toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
