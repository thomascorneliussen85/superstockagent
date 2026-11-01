import { useEffect, useReducer, useState } from "react";
import { emptyMarketState, reduceMarket, type MarketState } from "../shared/marketState";
import type { ConnState } from "../shared/protocol";
import type { PanelEvent, PanelTransport } from "../shared/transport";

interface PanelData {
  conn: ConnState;
  connDetail?: string;
  market: MarketState;
}

function reducer(s: PanelData, ev: PanelEvent): PanelData {
  switch (ev.kind) {
    case "snapshot":
      return { conn: ev.conn, connDetail: ev.detail, market: ev.market };
    case "conn":
      return { ...s, conn: ev.conn, connDetail: ev.detail };
    case "msg":
      return { ...s, market: reduceMarket(s.market, ev.msg, Date.now()) };
    default:
      return s;
  }
}

export function usePanelData(transport: PanelTransport, onToggle: () => void): PanelData {
  const [state, dispatch] = useReducer(reducer, { conn: "idle", market: emptyMarketState() });
  useEffect(
    () =>
      transport.subscribe((ev) => {
        if (ev.kind === "toggle") onToggle();
        else dispatch(ev);
      }),
    [transport, onToggle],
  );
  return state;
}

/** Re-renders periodically so ages ("0.4 s siden") stay current. */
export function useNow(intervalMs = 500): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
