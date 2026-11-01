import type { MarketState } from "../../shared/marketState";
import type { Insight, SimilarResult } from "../../shared/protocol";
import { no } from "../describe";

const TONE: Record<string, string> = { good: "text-tv-up", bad: "text-tv-down", warn: "text-tv-amber", neutral: "text-tv-muted" };
const ICON: Record<string, string> = { good: "✓", bad: "✕", warn: "!", neutral: "·" };

export function CoachTab({ market, onOpen }: { market: MarketState; onOpen(page: "journal" | "replay" | "chart"): void }) {
  const c = market.coach;
  const fb = market.feedback ?? c?.lastFeedback ?? null;
  return (
    <div className="space-y-3 text-xs">
      <div className="flex gap-2">
        <button onClick={() => onOpen("journal")} className="flex-1 rounded bg-tv-blue px-2 py-1 text-white hover:opacity-90">
          Journal og coach
        </button>
        <button onClick={() => onOpen("replay")} className="flex-1 rounded border border-tv-border px-2 py-1 text-tv-text hover:bg-tv-hover">
          Replay-trening
        </button>
      </div>

      <section>
        <H>Siste handel</H>
        {fb ? (
          <div className="rounded border border-tv-border bg-tv-panel p-2">
            <p className={`font-semibold ${fb.net > 0 ? "text-tv-up" : fb.net < 0 ? "text-tv-down" : "text-tv-text"}`}>
              {fb.direction === "long" ? "Long" : "Short"} · {fb.headline}
            </p>
            <ul className="mt-1 space-y-0.5">
              {fb.points.map((p) => (
                <li key={p.text} className="flex gap-1.5">
                  <span className={`w-3 shrink-0 text-center ${TONE[p.tone]}`}>{ICON[p.tone]}</span>
                  <span className="text-tv-text">{p.text}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-tv-muted">Ingen lukket handel registrert ennå. Tilbakemelding kommer automatisk når du lukker en handel.</p>
        )}
      </section>

      <section>
        <H>Lignende situasjoner i din historikk</H>
        {c?.similar?.long || c?.similar?.short ? (
          <div className="grid grid-cols-2 gap-2">
            <Similar label="Long nå" s={c.similar.long} />
            <Similar label="Short nå" s={c.similar.short} />
          </div>
        ) : (
          <p className="text-tv-muted">Trenger flere handler med registrert markedskontekst.</p>
        )}
      </section>

      <section>
        <H>Dine mønstre</H>
        {!c ? (
          <p className="text-tv-muted">Laster …</p>
        ) : c.insights.length === 0 ? (
          <p className="text-tv-muted">
            Ingen statistisk sikre mønstre ennå ({c.trades} handler). Påstander vises først når hver gruppe har minst {c.minSample} handler og
            forskjellen holder i et 95 %-konfidensintervall.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {c.insights.map((i) => (
              <InsightRow key={i.id} i={i} />
            ))}
          </ul>
        )}
      </section>

      {c && c.drift.length > 0 && (
        <section>
          <H>Varsel om endring</H>
          {c.drift.map((d) => (
            <p key={d.group} className="text-tv-amber">
              «{d.group}» har gått svakere de siste handlene ({no(d.recentMean, 2)} mot {no(d.beforeMean, 2)} tidligere).
            </p>
          ))}
        </section>
      )}
      {c && c.recommended.length > 0 && (
        <section>
          <H>Regler som har bestått walk-forward-test</H>
          {c.recommended.map((r) => (
            <p key={r.id} className="text-tv-text">
              {r.title} – forbedring utenfor utvalget {no(r.oosGain, 2)} ({r.oosCi ? `${no(r.oosCi[0], 2)}–${no(r.oosCi[1], 2)}` : "–"}). Du bestemmer selv.
            </p>
          ))}
        </section>
      )}
      <p className="text-[10px] text-tv-muted">
        Coachen lærer ved å lagre og analysere dine handler – språkmodellen trenes ikke om. Den endrer aldri risikogrenser eller handler.
      </p>
    </div>
  );
}

function InsightRow({ i }: { i: Insight }) {
  const cls = i.kind === "strength" ? "border-tv-up/40" : i.kind === "weakness" ? "border-tv-down/40" : "border-tv-amber/40";
  return (
    <li className={`rounded border-l-2 bg-tv-panel px-2 py-1 ${cls}`}>
      <p className="text-tv-text">{i.title}</p>
      <p className="text-[10px] text-tv-muted">
        {i.detail} · {i.strength}
      </p>
    </li>
  );
}

function Similar({ label, s }: { label: string; s?: SimilarResult }) {
  if (!s || !s.n) return <div className="rounded bg-tv-panel p-2 text-tv-muted">{label}: {s?.reason ?? "–"}</div>;
  const unit = s.unit === "R" ? " R" : "";
  return (
    <div className="rounded bg-tv-panel p-2">
      <p className="text-[10px] uppercase tracking-wider text-tv-muted">{label}</p>
      <p className="text-tv-text">
        Treff {Math.round((s.winRate ?? 0) * 100)} %{" "}
        <span className="text-tv-muted">
          ({s.winRateCi ? `${Math.round(s.winRateCi[0] * 100)}–${Math.round(s.winRateCi[1] * 100)} %` : "–"})
        </span>
      </p>
      <p className="text-tv-text">
        Snitt {no(s.meanOutcome, 2)}
        {unit}
      </p>
      <p className="text-[10px] text-tv-muted">n = {s.n}{s.enough ? "" : " – lite utvalg"}</p>
    </div>
  );
}

const H = ({ children }: { children: React.ReactNode }) => (
  <h3 className="mb-1 text-[10px] uppercase tracking-wider text-tv-muted">{children}</h3>
);
