import type { TabId } from "../App";

const PLANNED: Record<Exclude<TabId, "market">, { phase: string; title: string; items: string[] }> = {
  analysis: {
    phase: "Fase 2–3",
    title: "Markedsanalyse",
    items: [
      "Deterministiske indikatorer: RSI, Supertrend, EMA 9/20/50/200, ATR",
      "Markedsstruktur, støtte/motstand, likviditetssoner",
      "Multi-tidsramme (1m, 5m, 15m, 1h)",
      "AI-forklaring på norsk – kun ved relevante endringer",
    ],
  },
  signals: {
    phase: "Fase 3",
    title: "Mulige oppsett",
    items: [
      "Retning, inngangssone, invalidering, mål og R/R",
      "Støttende og motstridende bevis",
      "Datafriskhet – konfidens vises kun når den er kalibrert historisk",
    ],
  },
  positions: {
    phase: "Fase 4",
    title: "Posisjoner og risiko (kun lesing)",
    items: [
      "Åpne MT5-posisjoner med SL/TP og urealisert P/L",
      "Risiko i % av konto, basert på faktisk kontraktsspesifikasjon",
      "Varsler: spread, invalidering nær, daglig risikogrense",
    ],
  },
  coach: {
    phase: "Fase 5–6",
    title: "Personlig coach",
    items: [
      "Journal importert fra MT5-historikk",
      "Statistisk underbygde mønstre med minimum utvalgsstørrelse",
      "Daglige og ukentlige gjennomganger",
    ],
  },
};

export function PlannedTab({ tab }: { tab: Exclude<TabId, "market"> }) {
  const p = PLANNED[tab];
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-tv-text">{p.title}</h2>
        <span className="rounded bg-tv-panel px-1.5 py-px text-[10px] text-tv-muted">{p.phase}</span>
      </div>
      <p className="text-xs text-tv-muted">Ikke implementert ennå. Planlagt innhold:</p>
      <ul className="list-disc space-y-1 pl-4 text-xs text-tv-text">
        {p.items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}
