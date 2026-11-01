import { useRef } from "react";
import type { MarketState } from "../../shared/marketState";
import { TIMEFRAMES, type CandleMsg, type SymbolSpec } from "../../shared/protocol";
import { MiniChart } from "./MiniChart";

const fmt = (v: number | undefined, d: number) => (v == null ? "–" : v.toFixed(d));

export function MarketTab({ market }: { market: MarketState }) {
  const d = market.symbol?.digits ?? 2;
  const t = market.tick;
  const prevBid = useRef<number | null>(null);
  const dir = t && prevBid.current != null ? Math.sign(t.bid - prevBid.current) : 0;
  if (t) prevBid.current = t.bid;
  const priceCls = dir > 0 ? "text-tv-up" : dir < 0 ? "text-tv-down" : "text-tv-text";

  if (!t) {
    return <p className="text-xs text-tv-muted">Venter på markedsdata…</p>;
  }

  return (
    <div className="space-y-3">
      {market.status?.synthetic && (
        <div className="rounded border border-tv-amber/40 bg-tv-amber/10 px-2 py-1.5 text-[11px] text-tv-amber">
          Syntetiske demodata. Prisene er ikke ekte og skal ikke brukes til handel.
        </div>
      )}

      <section className="grid grid-cols-3 gap-2">
        <Stat label="Bid" value={fmt(t.bid, d)} cls={priceCls} />
        <Stat label="Ask" value={fmt(t.ask, d)} cls={priceCls} />
        <Stat label="Spread" value={fmt(t.spread, d)} sub={market.symbol ? `${Math.round(t.spread / market.symbol.point)} pts` : undefined} />
      </section>

      <section>
        <h3 className="mb-1 text-[11px] uppercase tracking-wider text-tv-muted">1m – siste 60 lys (bid)</h3>
        <MiniChart candles={market.candles["1m"].slice(-60)} digits={d} />
      </section>

      <section>
        <h3 className="mb-1 text-[11px] uppercase tracking-wider text-tv-muted">Tidsrammer</h3>
        <table className="tabular w-full text-xs">
          <thead className="text-tv-muted">
            <tr>
              <th className="text-left font-normal">TF</th>
              <th className="text-right font-normal">Åpning</th>
              <th className="text-right font-normal">Høy</th>
              <th className="text-right font-normal">Lav</th>
              <th className="text-right font-normal">Endring</th>
            </tr>
          </thead>
          <tbody>
            {TIMEFRAMES.map((tf) => (
              <TfRow key={tf} tf={tf} c={market.candles[tf].at(-1)} d={d} />
            ))}
          </tbody>
        </table>
      </section>

      {market.symbol && <ContractInfo spec={market.symbol} />}
    </div>
  );
}

function ContractInfo({ spec }: { spec: SymbolSpec }) {
  const oz = spec.contractSize;
  return (
    <section className="space-y-0.5 text-[11px] text-tv-muted">
      <h3 className="text-[11px] uppercase tracking-wider">Kontrakt {spec.brokerSymbol ? `(${spec.brokerSymbol})` : ""}</h3>
      <p>
        1,00 lot = <span className="text-tv-text">{oz} oz</span> · 0,10 lot = {+(oz * 0.1).toFixed(2)} oz · min {spec.volumeMin} lot, steg{" "}
        {spec.volumeStep}
      </p>
      <p>
        1 USD prisbevegelse ≈ <span className="text-tv-text">{(oz * 0.1).toFixed(0)} {spec.currencyProfit}</span> per 0,10 lot
        {spec.tickValue != null && spec.tickSize ? (
          <>
            {" "}· tick-verdi {spec.tickValue.toFixed(2)} {spec.currencyAccount ?? spec.currencyProfit} per {spec.tickSize} per lot
          </>
        ) : null}
      </p>
      {spec.source === "demo" && <p className="text-tv-amber">Demoverdier – start backend i MT5-modus for meglerens ekte spesifikasjon.</p>}
    </section>
  );
}

function Stat({ label, value, sub, cls = "text-tv-text" }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="rounded bg-tv-panel px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-tv-muted">{label}</div>
      <div className={`tabular font-mono text-sm ${cls}`}>{value}</div>
      {sub && <div className="text-[10px] text-tv-muted">{sub}</div>}
    </div>
  );
}

function TfRow({ tf, c, d }: { tf: string; c: CandleMsg | undefined; d: number }) {
  if (!c) {
    return (
      <tr>
        <td>{tf}</td>
        <td colSpan={4} className="text-right text-tv-muted">–</td>
      </tr>
    );
  }
  const ch = c.c - c.o;
  return (
    <tr>
      <td>{tf}</td>
      <td className="text-right">{c.o.toFixed(d)}</td>
      <td className="text-right">{c.h.toFixed(d)}</td>
      <td className="text-right">{c.l.toFixed(d)}</td>
      <td className={`text-right ${ch > 0 ? "text-tv-up" : ch < 0 ? "text-tv-down" : ""}`}>
        {ch > 0 ? "+" : ""}
        {ch.toFixed(d)}
      </td>
    </tr>
  );
}
