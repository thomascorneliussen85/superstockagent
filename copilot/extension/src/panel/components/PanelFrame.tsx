import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { clampGeom, defaultGeom, isValidGeom, moveBy, resizeBy, type PanelGeom } from "../../shared/geometry";
import type { MarketState } from "../../shared/marketState";
import type { ConnState } from "../../shared/protocol";
import { KEYS, type KVStore } from "../../shared/storage";
import { ModeBadge } from "./ModeBadge";

interface Props {
  store: KVStore;
  data: { conn: ConnState; market: MarketState };
  onClose(): void;
  onOpenOptions(): void;
  children: ReactNode;
}

const vp = () => ({ vw: window.innerWidth, vh: window.innerHeight });

export function PanelFrame({ store, data, onClose, onOpenOptions, children }: Props) {
  const [geom, setGeom] = useState<PanelGeom>(() => defaultGeom(window.innerWidth, window.innerHeight));
  const drag = useRef<{ mode: "move" | "resize"; x: number; y: number } | null>(null);
  const geomRef = useRef(geom);
  geomRef.current = geom;

  useEffect(() => {
    void store.get<PanelGeom>(KEYS.geom).then((g) => {
      if (isValidGeom(g)) setGeom(clampGeom(g, window.innerWidth, window.innerHeight));
    });
    const onResize = () => setGeom((g) => clampGeom(g, window.innerWidth, window.innerHeight));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [store]);

  const persist = (g: PanelGeom) => void store.set(KEYS.geom, g);

  const start = (mode: "move" | "resize") => (e: PointerEvent<HTMLElement>) => {
    if (e.button !== 0) return;
    if (mode === "move" && (e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { mode, x: e.clientX, y: e.clientY };
  };
  const onMove = (e: PointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    d.x = e.clientX;
    d.y = e.clientY;
    const { vw, vh } = vp();
    setGeom((g) => (d.mode === "move" ? moveBy(g, dx, dy, vw, vh) : resizeBy(g, dx, dy, vw, vh)));
  };
  const end = (e: PointerEvent<HTMLElement>) => {
    if (!drag.current) return;
    drag.current = null;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    persist(geomRef.current);
  };
  const toggleCollapsed = () => {
    const g = { ...geom, collapsed: !geom.collapsed };
    setGeom(g);
    persist(g);
  };

  const connColor =
    data.conn === "connected"
      ? data.market.status?.state === "live"
        ? "bg-tv-up"
        : "bg-tv-amber"
      : data.conn === "connecting" || data.conn === "authenticating"
        ? "bg-tv-amber animate-pulse"
        : "bg-tv-down";

  return (
    <div
      role="dialog"
      aria-label="AI Trading Copilot"
      // Keep keyboard/wheel input inside the panel from triggering TradingView shortcuts or chart zoom.
      onKeyDown={(e) => e.stopPropagation()}
      onKeyUp={(e) => e.stopPropagation()}
      onWheel={(e) => e.stopPropagation()}
      className="fixed flex flex-col overflow-hidden rounded-md border border-tv-border bg-tv-bg/95 shadow-2xl backdrop-blur"
      style={{ left: geom.x, top: geom.y, width: geom.w, height: geom.collapsed ? undefined : geom.h }}
    >
      <header
        onPointerDown={start("move")}
        onPointerMove={onMove}
        onPointerUp={end}
        onPointerCancel={end}
        onDoubleClick={toggleCollapsed}
        className="flex h-9 shrink-0 cursor-move select-none items-center gap-2 border-b border-tv-border bg-tv-panel px-2"
      >
        <span className={`h-2 w-2 rounded-full ${connColor}`} title={`Tilkobling: ${data.conn}`} />
        <span className="text-xs font-semibold tracking-wide text-tv-text">AI Copilot</span>
        <span className="text-xs text-tv-muted">{data.market.hello?.symbol ?? "XAUUSD"}</span>
        <ModeBadge market={data.market} />
        <div className="ml-auto flex items-center gap-0.5">
          <IconButton label="Innstillinger" onClick={onOpenOptions}>⚙</IconButton>
          <IconButton label={geom.collapsed ? "Utvid" : "Minimer"} onClick={toggleCollapsed}>
            {geom.collapsed ? "▾" : "▴"}
          </IconButton>
          <IconButton label="Skjul (Alt+Shift+A)" onClick={onClose}>✕</IconButton>
        </div>
      </header>
      {!geom.collapsed && (
        <>
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
          <div
            onPointerDown={start("resize")}
            onPointerMove={onMove}
            onPointerUp={end}
            onPointerCancel={end}
            title="Endre størrelse"
            className="absolute bottom-0 right-0 h-3.5 w-3.5 cursor-nwse-resize"
            style={{ background: "linear-gradient(135deg, transparent 50%, #434651 50%)" }}
          />
        </>
      )}
    </div>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick(): void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className="flex h-6 w-6 items-center justify-center rounded text-xs text-tv-muted hover:bg-tv-hover hover:text-tv-text"
    >
      {children}
    </button>
  );
}
