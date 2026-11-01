import type { MarketState } from "../../shared/marketState";
import type { AccountView, PositionView, RiskAlert } from "../../shared/protocol";
import { no } from "../describe";

const money = (v: number | null | undefined, cur?: string) => (v == null ? "–" : `${no(v, 2)}${cur ? ` ${cur}` : ""}`);
const pnlCls = (v: number) => (v > 0 ? "text-tv-up" : v < 0 ? "text-tv-down" : "text-tv-text");

export function PositionsTab({ market }: { market: MarketState }) {
  const v = market.account;
  if (!v) return <p className="text-xs text-tv-muted">Venter på kontodata …</p>;
  if (!v.available) return <p className="text-xs text-tv-muted">{v.reason}</p>;
  const cur = v.account?.currency ?? "";

  return (
    <div className="space-y-3 text-xs">
      <Alerts alerts={v.alerts ?? []} />
      <AccountSummary v={v} cur={cur} />
      <section className="space-y-2">
        <h3 className="text-[10px] uppercase tracking-wider text-tv-muted">
          Åpne posisjoner ({v.positions?.length ?? 0}){v.pendingOrders ? ` · ${v.pendingOrders} ventende ordre` : ""}
        </h3>
        {v.positions && v.positions.length > 0 ? (
          v.positions.map((p) => <Position key={p.ticket} p={p} cur={cur} />)
        ) : (
          <p className="text-tv-muted">Ingen åpne posisjoner.</p>
        )}
      </section>
      <p className="text-[10px] text-tv-muted">
        Kun lesing: panelet viser og varsler, men endrer eller lukker aldri noe i MT5. Grenser settes i backend/.env
        (COPILOT_RISK_MAX_PER_TRADE_PCT={v.rules?.maxPerTradePct}, COPILOT_RISK_DAILY_LOSS_LIMIT_PCT=
        {v.rules?.dailyLossLimitPct}).
      </p>
    </div>
  );
}

function Alerts({ alerts }: { alerts: RiskAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <ul className="space-y-1">
      {alerts.map((a) => (
        <li
          key={a.key}
          className={`rounded border px-2 py-1 text-[11px] ${
            a.level === "critical"
              ? "border-tv-down/50 bg-tv-down/15 text-tv-down"
              : "border-tv-amber/40 bg-tv-amber/10 text-tv-amber"
          }`}
        >
          {a.level === "critical" ? "⛔ " : "⚠ "}
          {a.text}
        </li>
      ))}
    </ul>
  );
}

function AccountSummary({ v, cur }: { v: AccountView; cur: string }) {
  const a = v.account!;
  const d = v.day!;
  const used = Math.min(100, d.usedPct ?? 0);
  return (
    <section className="space-y-2 rounded border border-tv-border bg-tv-panel p-2">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Saldo" value={money(a.balance)} />
        <Stat label="Egenkapital" value={money(a.equity)} />
        <Stat label="Flytende" value={money(a.profit)} cls={pnlCls(a.profit)} />
      </div>
      <div>
        <div className="mb-0.5 flex justify-between text-[10px] text-tv-muted">
          <span>
            I dag: <span className={pnlCls(d.result)}>{money(d.result, cur)}</span> ({d.closedTrades} lukket)
          </span>
          <span>
            Tapsgrense {no(d.limitPct, 1)} % = {money(d.limitMoney, cur)}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded bg-tv-bg">
          <div className={`h-full ${used >= 80 ? "bg-tv-down" : used >= 50 ? "bg-tv-amber" : "bg-tv-blue"}`} style={{ width: `${used}%` }} />
        </div>
        <p className="mt-0.5 text-[10px] text-tv-muted">
          Åpen risiko til stop-loss: {d.anyWithoutSl ? "ubegrenset (posisjon uten SL)" : money(d.openRisk, cur)} · Margin{" "}
          {a.marginLevel ? `${no(a.marginLevel, 0)} %` : "–"} · {a.tradeMode === "live" ? "LIVE" : "DEMO"}
        </p>
      </div>
    </section>
  );
}

function Position({ p, cur }: { p: PositionView; cur: string }) {
  const long = p.type === "buy";
  const d = p.digits;
  const pnl = p.profit + p.swap;
  const progress = p.slProgress == null ? null : Math.round(p.slProgress * 100);
  return (
    <div className={`rounded border p-2 ${long ? "border-tv-up/30" : "border-tv-down/30"}`}>
      <div className="mb-1 flex items-center gap-2">
        <b className={long ? "text-tv-up" : "text-tv-down"}>{long ? "LONG" : "SHORT"}</b>
        <span className="text-tv-text">{p.symbol}</span>
        <span className="text-tv-muted" title="MT5-volum i lot, og antall unser etter meglerens kontraktstørrelse">
          {p.volume} lot = {no(p.oz, p.oz % 1 ? 2 : 0)} oz
        </span>
        <span className={`tabular ml-auto font-semibold ${pnlCls(pnl)}`}>{money(pnl, cur)}</span>
      </div>
      <Row k="Inngang → nå" v={`${no(p.priceOpen, d)} → ${no(p.priceCurrent, d)}`} />
      <Row k="Stop-loss" v={p.sl > 0 ? `${no(p.sl, d)}  (${no(p.distToSl, d)} unna${p.distToSlAtr != null ? `, ${no(p.distToSlAtr, 1)} ATR` : ""})` : "INGEN"} warn={p.sl <= 0} />
      <Row k="Take-profit" v={p.tp > 0 ? `${no(p.tp, d)}  (${no(p.distToTp, d)} unna)` : "–"} />
      <Row
        k="Risiko ved SL"
        v={
          p.riskMoney != null
            ? `${money(p.riskMoney, cur)} · ${no(p.riskPct, 2)} % av saldo`
            : p.lockedMoney != null
              ? `ingen – ${money(p.lockedMoney, cur)} låst gevinst`
              : "–"
        }
      />
      {p.rMultiple != null && <Row k="Nå i R" v={`${p.rMultiple > 0 ? "+" : ""}${no(p.rMultiple, 2)} R`} />}
      {progress != null && (
        <div className="mt-1" title="Hvor mye av avstanden mellom inngang og stop-loss som gjenstår">
          <div className="h-1 overflow-hidden rounded bg-tv-bg">
            <div className={`h-full ${progress <= 25 ? "bg-tv-down" : "bg-tv-up"}`} style={{ width: `${progress}%` }} />
          </div>
          <p className="text-[10px] text-tv-muted">{progress} % av avstanden til stop-loss gjenstår</p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, cls = "text-tv-text" }: { label: string; value: string; cls?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-tv-muted">{label}</div>
      <div className={`tabular font-mono text-[13px] ${cls}`}>{value}</div>
    </div>
  );
}

function Row({ k, v, warn }: { k: string; v: string; warn?: boolean }) {
  return (
    <div className="tabular flex justify-between gap-2">
      <span className="text-tv-muted">{k}</span>
      <span className={warn ? "font-semibold text-tv-down" : "text-tv-text"}>{v}</span>
    </div>
  );
}
