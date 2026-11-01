import { useCallback, useEffect, useState } from "react";
import type { KVStore } from "../shared/storage";
import { KEYS } from "../shared/storage";
import type { PanelTransport } from "../shared/transport";
import { PanelFrame } from "./components/PanelFrame";
import { AnalysisTab } from "./components/AnalysisTab";
import { MarketTab } from "./components/MarketTab";
import { PlannedTab } from "./components/PlannedTab";
import { StatusBar } from "./components/StatusBar";
import { usePanelData } from "./usePanel";

export type TabId = "market" | "analysis" | "signals" | "positions" | "coach";

const TABS: { id: TabId; label: string }[] = [
  { id: "market", label: "Marked" },
  { id: "analysis", label: "Analyse" },
  { id: "signals", label: "Signaler" },
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
            </button>
          ))}
        </nav>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {tab === "market" ? (
            <MarketTab market={data.market} />
          ) : tab === "analysis" ? (
            <AnalysisTab market={data.market} />
          ) : (
            <PlannedTab tab={tab} />
          )}
        </div>
        <StatusBar data={data} />
      </PanelFrame>
    </div>
  );
}
