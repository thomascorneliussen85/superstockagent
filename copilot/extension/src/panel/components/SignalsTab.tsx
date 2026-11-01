import type { MarketState } from "../../shared/marketState";
import type { AiComment, Bias } from "../../shared/protocol";
import { no } from "../describe";
import { useNow } from "../usePanel";
import { hasNorwegianVoice, speak, type AlertType, type VoiceSettings } from "../voice";

const BIAS: Record<Bias, { text: string; cls: string }> = {
  long: { text: "Heller mot long", cls: "border-tv-up/50 bg-tv-up/15 text-tv-up" },
  short: { text: "Heller mot short", cls: "border-tv-down/50 bg-tv-down/15 text-tv-down" },
  neutral: { text: "Nøytral", cls: "border-tv-border bg-tv-panel text-tv-muted" },
  avoid: { text: "Avvent", cls: "border-tv-amber/50 bg-tv-amber/15 text-tv-amber" },
};
const KIND: Record<string, string> = {
  pullback: "pullback",
  breakout: "breakout",
  reversal: "reversering",
  range: "range",
  none: "",
};

interface Props {
  market: MarketState;
  connected: boolean;
  onAsk(): void;
  voice: VoiceSettings;
  onVoice(v: VoiceSettings): void;
}

export function SignalsTab({ market, connected, onAsk, voice, onVoice }: Props) {
  const now = useNow(1000);
  const st = market.aiStatus;
  const ai = market.ai;
  const d = market.symbol?.digits ?? 2;
  const thinking = st?.state === "thinking";
  const canAsk = connected && st?.state === "ready";

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-tv-muted">
          AI: {st ? (st.state === "disabled" ? "av" : thinking ? "tenker …" : "klar") : "–"}
          {st?.model ? ` · ${st.model}` : ""}
        </span>
        <button
          onClick={onAsk}
          disabled={!canAsk}
          className="ml-auto rounded bg-tv-blue px-2 py-1 text-[11px] text-white disabled:cursor-not-allowed disabled:opacity-40"
          title="Ber om en ny vurdering nå (teller mot budsjettet)"
        >
          {thinking ? "Tenker …" : "Spør AI nå"}
        </button>
      </div>

      {st?.reason && <Note tone="red">{st.reason}</Note>}
      {st?.note && <Note tone="amber">{st.note}</Note>}

      {ai ? <Comment ai={ai} market={market} now={now} d={d} /> : <p className="text-tv-muted">Ingen AI-kommentar ennå. Den kommer automatisk når noe viktig skjer i markedet.</p>}

      {st && st.state !== "disabled" && <Budget st={st} />}

      <VoicePanel voice={voice} onVoice={onVoice} />
    </div>
  );
}

function Comment({ ai, market, now, d }: { ai: AiComment; market: MarketState; now: number; d: number }) {
  const ageS = Math.max(0, (now - ai.createdAt) / 1000);
  const bid = market.tick?.bid;
  const moved = ai.price && bid != null && ai.atr1m ? Math.abs(bid - ai.price.bid) / ai.atr1m : 0;
  const outdated = ageS > 300 || moved > 1.5;
  const b = BIAS[ai.bias] ?? BIAS.neutral;
  const lotOz = (market.symbol?.contractSize ?? 100) * 0.1;

  return (
    <section className={`space-y-2 rounded border border-tv-border bg-tv-panel p-2 ${outdated ? "opacity-60" : ""}`}>
      <div className="flex items-center gap-2">
        <span className={`rounded border px-1.5 py-px text-[11px] font-semibold ${b.cls}`}>{b.text}</span>
        <span className="text-[10px] text-tv-muted">
          {new Date(ai.createdAt).toLocaleTimeString("nb-NO")} · {ageS < 60 ? `${ageS.toFixed(0)} s` : `${Math.floor(ageS / 60)} min`} siden
        </span>
      </div>
      {outdated && <p className="text-[11px] text-tv-amber">Utdatert – markedet har beveget seg siden denne vurderingen.</p>}
      <p className="text-[13px] leading-snug text-tv-text">{ai.summary}</p>

      {ai.setup && (
        <div className={`rounded border p-2 ${ai.setup.direction === "long" ? "border-tv-up/40" : "border-tv-down/40"}`}>
          <div className="mb-1 flex items-center gap-2">
            <b className={ai.setup.direction === "long" ? "text-tv-up" : "text-tv-down"}>
              Mulig {ai.setup.direction.toUpperCase()} {KIND[ai.setup.kind] ?? ""}
            </b>
            <span className={`ml-auto ${ai.setup.rr >= 1.5 ? "text-tv-text" : "text-tv-amber"}`} title="Beregnet av systemet, inkludert spread">
              R/R {no(ai.setup.rr, 1)}
            </span>
          </div>
          <Row k="Inngangssone" v={`${no(ai.setup.entryLow, d)} – ${no(ai.setup.entryHigh, d)}`} />
          <Row k="Invalidering" v={no(ai.setup.invalidation, d)} />
          <Row k="Mulig mål" v={no(ai.setup.target, d)} />
          <Row k="Risiko per 0,10 lot" v={`≈ ${no(ai.setup.riskPerOz * lotOz, 0)} USD`} />
          {ai.setup.supporting.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {ai.setup.supporting.map((s) => (
                <li key={s} className="text-tv-up">+ <span className="text-tv-text">{s}</span></li>
              ))}
            </ul>
          )}
          {ai.setup.conflicting.length > 0 && (
            <ul className="mt-0.5 space-y-0.5">
              {ai.setup.conflicting.map((s) => (
                <li key={s} className="text-tv-down">− <span className="text-tv-text">{s}</span></li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-[10px] text-tv-muted">Konfidens vises ikke: den er ikke kalibrert mot historiske resultater ennå.</p>
        </div>
      )}
      {ai.setupRejected && <p className="text-[11px] text-tv-muted">AI-ens oppsett ble forkastet av systemet: {ai.setupRejected}.</p>}

      {ai.warnings.length > 0 && (
        <ul className="space-y-0.5">
          {ai.warnings.map((w) => (
            <li key={w} className="text-tv-amber">⚠ {w}</li>
          ))}
        </ul>
      )}
      <p className="text-[10px] text-tv-muted">
        Utløst av: {ai.reasons.join("; ") || "–"} · {ai.model} · {no(ai.costNok, 2)} kr
      </p>
      <p className="text-[10px] text-tv-muted">AI-tolkning av fakta – ingen garanti, ikke finansiell rådgivning.</p>
    </section>
  );
}

function Budget({ st }: { st: NonNullable<MarketState["aiStatus"]> }) {
  const b = st.budget;
  const pct = b.monthCapNok > 0 ? Math.min(100, (b.monthSpentNok / b.monthCapNok) * 100) : 100;
  return (
    <section>
      <div className="mb-0.5 flex justify-between text-[10px] text-tv-muted">
        <span>AI-budsjett denne måneden</span>
        <span>
          {no(b.monthSpentNok, 2)} av {no(b.monthCapNok, 0)} kr
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-tv-panel">
        <div className={`h-full ${pct > 85 ? "bg-tv-down" : "bg-tv-blue"}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-0.5 text-[10px] text-tv-muted">
        I dag: {no(b.daySpentNok, 2)} av {no(b.dayAllowanceNok, 2)} kr · {b.callsToday} kall
        {st.cooldownS > 0 ? ` · neste automatiske om ${st.cooldownS} s` : ""}
      </p>
    </section>
  );
}

const TYPE_LABEL: Record<AlertType, string> = { setup: "Mulige oppsett", structure: "Brudd (5m/15m)", spread: "Høy spread" };

function VoicePanel({ voice, onVoice }: { voice: VoiceSettings; onVoice(v: VoiceSettings): void }) {
  return (
    <section className="space-y-1 border-t border-tv-border pt-2">
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={voice.enabled} onChange={(e) => onVoice({ ...voice, enabled: e.target.checked })} />
        <span className="text-tv-text">Talevarsler på norsk</span>
        <button
          className="ml-auto rounded border border-tv-border px-1.5 py-px text-[11px] text-tv-muted hover:bg-tv-hover"
          onClick={() => speak("Talevarsler er på.", voice.volume)}
        >
          Test
        </button>
      </label>
      {voice.enabled && (
        <>
          <div className="flex items-center gap-2 text-tv-muted">
            Volum
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={voice.volume}
              onChange={(e) => onVoice({ ...voice, volume: Number(e.target.value) })}
              className="flex-1"
            />
          </div>
          <div className="flex flex-wrap gap-x-3">
            {(Object.keys(TYPE_LABEL) as AlertType[]).map((t) => (
              <label key={t} className="flex items-center gap-1 text-tv-muted">
                <input
                  type="checkbox"
                  checked={voice.types[t]}
                  onChange={(e) => onVoice({ ...voice, types: { ...voice.types, [t]: e.target.checked } })}
                />
                {TYPE_LABEL[t]}
              </label>
            ))}
          </div>
          {!hasNorwegianVoice() && (
            <p className="text-[10px] text-tv-amber">Fant ingen norsk stemme i Windows – bruker standardstemmen. Installer «Norsk bokmål» under Windows-innstillinger → Tid og språk → Tale.</p>
          )}
        </>
      )}
    </section>
  );
}

function Note({ tone, children }: { tone: "red" | "amber"; children: React.ReactNode }) {
  const cls = tone === "red" ? "border-tv-down/40 bg-tv-down/10 text-tv-down" : "border-tv-amber/40 bg-tv-amber/10 text-tv-amber";
  return <div className={`rounded border px-2 py-1 text-[11px] ${cls}`}>{children}</div>;
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="tabular flex justify-between">
      <span className="text-tv-muted">{k}</span>
      <span className="text-tv-text">{v}</span>
    </div>
  );
}
