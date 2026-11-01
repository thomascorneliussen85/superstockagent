import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketState } from "../shared/marketState";
import type { KVStore } from "../shared/storage";
import { KEYS } from "../shared/storage";
import type { PanelTransport } from "../shared/transport";
import { PanelFrame } from "./components/PanelFrame";
import { AnalysisTab } from "./components/AnalysisTab";
import { MarketTab } from "./components/MarketTab";
import { CoachTab } from "./components/CoachTab";
import { PositionsTab } from "./components/PositionsTab";
import { SignalsTab } from "./components/SignalsTab";
import { StatusBar } from "./components/StatusBar";
import { usePanelData } from "./usePanel";
import { AlertGate, alertsBetween, DEFAULT_VOICE, speak, type VoiceSettings } from "./voice";

export type TabId = "market" | "analysis" | "signals" | "positions" | "coach";

const TABS: { id: TabId; label: string }[] = [
  { id: "market", label: "Marked" },
  { id: "analysis", label: "Analyse" },
  { id: "signals", label: "AI" },
  { id: "positions", label: "Posisjoner" },
  { id: "coach", label: "Coach" },
];

interface Props {
  transport: PanelTransport;
  store: KVStore;
}

export function App({ transport, store }: Props) {
  const [visible, setVisible] = useState(true);
  const [tab, setTab] = useState<TabId>("market");

  useEffect(() => {
    void store.get<boolean>(KEYS.visible).then((v) => v === false && setVisible(false));
    void store.get<TabId>(KEYS.tab).then((t) => t && TABS.some((x) => x.id === t) && setTab(t));
  }, [store]);

  const toggle = useCallback(() => {
    setVisible((v) => {
      void store.set(KEYS.visible, !v);
      return !v;
    });
  }, [store]);

  const data = usePanelData(transport, toggle);
  const [voice, setVoice] = useState<VoiceSettings>(DEFAULT_VOICE);
  useEffect(() => {
    void store.get<VoiceSettings>(KEYS.voice).then((v) => v && setVoice({ ...DEFAULT_VOICE, ...v, types: { ...DEFAULT_VOICE.types, ...v.types } }));
  }, [store]);
  const updateVoice = (v: VoiceSettings) => {
    setVoice(v);
    void store.set(KEYS.voice, v);
  };
  useVoiceAlerts(data.market, voice);
  const selectTab = (t: TabId) => {
    setTab(t);
    void store.set(KEYS.tab, t);
  };

  if (!visible) {
    return (
      <div className="copilot-root">
        <button
          onClick={toggle}
          title="Vis AI Trading Copilot (Alt+Shift+A)"
          className="fixed bottom-16 right-4 rounded-full border border-tv-border bg-tv-panel px-3 py-1.5 text-xs font-semibold text-tv-amber shadow-lg hover:bg-tv-hover"
        >
          AI
        </button>
      </div>
    );
  }

  return (
    <div className="copilot-root">
      <PanelFrame store={store} data={data} onClose={toggle} onOpenOptions={transport.openOptions}>
        <nav className="flex shrink-0 border-b border-tv-border px-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => selectTab(t.id)}
              className={`px-2.5 py-2 text-xs transition-colors ${
                tab === t.id ? "border-b-2 border-tv-blue text-tv-text" : "text-tv-muted hover:text-tv-text"
              }`}
            >
              {t.label}
              {t.id === "positions" && (data.market.account?.alerts?.length ?? 0) > 0 && (
                <span
                  className={`ml-1 inline-block h-1.5 w-1.5 rounded-full align-middle ${
                    data.market.account?.alerts?.some((a) => a.level === "critical") ? "bg-tv-down" : "bg-tv-amber"
                  }`}
                />
              )}
            </button>
          ))}
        </nav>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {tab === "market" ? (
            <MarketTab market={data.market} />
          ) : tab === "analysis" ? (
            <AnalysisTab market={data.market} onOpenChart={() => transport.openPage("chart")} />
          ) : tab === "signals" ? (
            <SignalsTab
              market={data.market}
              connected={data.conn === "connected"}
              onAsk={() => transport.send({ type: "ai_request" })}
              voice={voice}
              onVoice={updateVoice}
            />
          ) : tab === "positions" ? (
            <PositionsTab market={data.market} />
          ) : (
            <CoachTab market={data.market} onOpen={(p) => transport.openPage(p)} />
          )}
        </div>
        <StatusBar data={data} />
      </PanelFrame>
    </div>
  );
}

/** Speaks new alerts (only in the visible tab, so several TradingView tabs never talk at once). */
function useVoiceAlerts(market: MarketState, voice: VoiceSettings) {
  const prev = useRef<MarketState | null>(null);
  const gate = useRef(new AlertGate());
  useEffect(() => {
    const before = prev.current;
    prev.current = market;
    if (!voice.enabled || document.visibilityState !== "visible") return;
    for (const a of alertsBetween(before, market)) {
      if (gate.current.allow(a, Date.now(), voice)) speak(a.text, voice.volume);
    }
  }, [market, voice]);
}
