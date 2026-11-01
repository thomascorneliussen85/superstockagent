// Candlestick chart (Lightweight Charts) with analysis overlays:
// support/resistance, trendlines, a tick-volume profile and the AI setup.
import {
  createChart,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { AiComment, Analysis, CandleMsg, Timeframe } from "../shared/protocol";
import { no } from "../panel/describe";

export interface Overlays {
  levels: boolean;
  volume: boolean;
  trendlines: boolean;
  ai: boolean;
}
export const DEFAULT_OVERLAYS: Overlays = { levels: true, volume: true, trendlines: true, ai: true };

export const TF_MS: Record<Timeframe, number> = { "1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000 };

/** Lightweight Charts plots UTC; shift by the local offset so the axis shows Norwegian time. */
export const localSec = (ms: number) => (Math.floor(ms / 1000) - new Date(ms).getTimezoneOffset() * 60) as UTCTimestamp;

const COL = { up: "#26a69a", down: "#ef5350", blue: "#2962ff", amber: "#f7a600", muted: "#787b86" };

interface SimPos { id: number; side: "buy" | "sell"; entry: number; sl: number | null; tp: number | null }
interface SimTrade { side: "buy" | "sell"; open_ms: number; close_ms: number; net: number }

interface Props {
  candles: CandleMsg[];
  tf: Timeframe;
  analysis: Analysis | null;
  ai: AiComment | null;
  overlays: Overlays;
  nowMs?: number; // replay clock; live uses Date.now()
  positions?: SimPos[];
  trades?: SimTrade[];
}

export function ChartView({ candles, tf, analysis, ai, overlays, nowMs, positions = [], trades = [] }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lines = useRef<IPriceLine[]>([]);
  const trendSeries = useRef<ISeriesApi<"Line">[]>([]);
  const lastKey = useRef("");
  const vpRef = useRef<Analysis["volumeProfile"] | null>(null);
  const showVp = useRef(overlays.volume);

  // ---- chart lifecycle -------------------------------------------------------------
  useEffect(() => {
    if (!box.current) return;
    const c = createChart(box.current, {
      autoSize: true,
      layout: { background: { color: "#131722" }, textColor: "#d1d4dc" },
      grid: { vertLines: { color: "#1e222d" }, horzLines: { color: "#1e222d" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#2a2e39", rightOffset: 8 },
      rightPriceScale: { borderColor: "#2a2e39" },
      crosshair: { mode: 0 },
    });
    series.current = c.addCandlestickSeries({
      upColor: COL.up, downColor: COL.down, borderVisible: false, wickUpColor: COL.up, wickDownColor: COL.down,
    });
    chart.current = c;
    // Volume profile is drawn on a canvas over the chart and redrawn regularly.
    let raf = 0;
    let last = 0;
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      if (t - last < 200) return;
      last = t;
      drawProfile();
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      c.remove();
    };
  }, []);

  function drawProfile() {
    const cv = canvas.current;
    const s = series.current;
    const host = box.current;
    if (!cv || !s || !host) return;
    const w = host.clientWidth;
    const h = host.clientHeight;
    if (cv.width !== w || cv.height !== h) {
      cv.width = w;
      cv.height = h;
    }
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    const vp = vpRef.current;
    if (!showVp.current || !vp) return;
    const priceScaleW = chart.current?.priceScale("right").width() ?? 60;
    const right = w - priceScaleW - 4;
    const maxW = Math.min(140, w * 0.18);
    for (const b of vp.bins) {
      const y1 = s.priceToCoordinate(b.p + vp.binSize / 2);
      const y2 = s.priceToCoordinate(b.p - vp.binSize / 2);
      if (y1 == null || y2 == null) continue;
      const inVa = b.p >= vp.val && b.p <= vp.vah;
      ctx.fillStyle = b.p === vp.poc ? "rgba(247,166,0,0.55)" : inVa ? "rgba(41,98,255,0.30)" : "rgba(120,123,134,0.22)";
      const bw = Math.max(1, b.v * maxW);
      ctx.fillRect(right - bw, Math.min(y1, y2) + 1, bw, Math.max(1, Math.abs(y2 - y1) - 2));
    }
  }

  // ---- candles ----------------------------------------------------------------------
  useEffect(() => {
    const s = series.current;
    if (!s) return;
    if (candles.length === 0) {
      s.setData([]);
      lastKey.current = "";
      return;
    }
    const bar = (c: CandleMsg) => ({ time: localSec(c.t) as Time, open: c.o, high: c.h, low: c.l, close: c.c });
    const key = `${tf}:${candles.length}:${candles[0].t}`;
    if (key === lastKey.current) s.update(bar(candles[candles.length - 1]));
    else {
      s.setData(candles.map(bar));
      lastKey.current = key;
    }
  }, [candles, tf]);

  // ---- overlays -----------------------------------------------------------------------
  useEffect(() => {
    vpRef.current = analysis?.volumeProfile ?? null;
    showVp.current = overlays.volume;
  }, [analysis, overlays.volume]);

  useEffect(() => {
    const s = series.current;
    const c = chart.current;
    if (!s || !c) return;
    lines.current.forEach((l) => s.removePriceLine(l));
    lines.current = [];
    trendSeries.current.forEach((x) => c.removeSeries(x));
    trendSeries.current = [];
    const add = (price: number, color: string, title: string, style: LineStyle = LineStyle.Dashed, width: 1 | 2 = 1) =>
      lines.current.push(s.createPriceLine({ price, color, lineWidth: width, lineStyle: style, title, axisLabelVisible: true }));

    const a = analysis?.timeframes?.[tf];
    if (overlays.levels && a && !a.insufficient) {
      a.levels?.support.forEach((l) => add(l.price, COL.up, `S ${l.touches}×`));
      a.levels?.resistance.forEach((l) => add(l.price, COL.down, `R ${l.touches}×`));
      // Strongest levels from the next higher timeframe, drawn thicker.
      const higher = { "1m": "15m", "5m": "1h", "15m": "1h", "1h": null }[tf] as Timeframe | null;
      const h = higher ? analysis?.timeframes?.[higher] : null;
      if (h && !h.insufficient) {
        h.levels?.support.slice(0, 1).forEach((l) => add(l.price, COL.up, `S ${higher}`, LineStyle.Solid, 2));
        h.levels?.resistance.slice(0, 1).forEach((l) => add(l.price, COL.down, `R ${higher}`, LineStyle.Solid, 2));
      }
    }
    if (overlays.volume && analysis?.volumeProfile) add(analysis.volumeProfile.poc, COL.amber, "POC", LineStyle.Dotted);

    if (overlays.trendlines && a?.trendlines) {
      for (const t of a.trendlines) {
        const ls = c.addLineSeries({
          color: t.kind === "support" ? COL.up : COL.down,
          lineWidth: 2,
          lineStyle: t.broken ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const pts = [
          { time: localSec(t.t1) as Time, value: t.p1 },
          { time: localSec(t.tNow) as Time, value: t.valueNow },
        ].sort((x, y) => (x.time as number) - (y.time as number));
        if ((pts[0].time as number) < (pts[1].time as number)) ls.setData(pts);
        trendSeries.current.push(ls);
      }
    }

    const now = nowMs ?? Date.now();
    const fresh = ai && now - ai.createdAt < 30 * 60_000 && now >= ai.createdAt;
    if (overlays.ai && fresh && ai?.setup) {
      const st = ai.setup;
      const long = st.direction === "long";
      add(st.entryHigh, COL.blue, long ? "Mulig kjøp (AI)" : "Inngang", LineStyle.Dotted);
      add(st.entryLow, COL.blue, long ? "Inngang" : "Mulig salg (AI)", LineStyle.Dotted);
      add(st.invalidation, COL.down, "Invalidering", LineStyle.Solid);
      add(st.target, COL.up, `Mål · R/R ${no(st.rr, 1)}`, LineStyle.Solid);
    }

    // Markers: AI setup time + simulated trades
    const markers: SeriesMarker<Time>[] = [];
    const tfMs = TF_MS[tf];
    if (overlays.ai && fresh && ai?.setup) {
      markers.push({
        time: localSec(ai.createdAt - (ai.createdAt % tfMs)) as Time,
        position: ai.setup.direction === "long" ? "belowBar" : "aboveBar",
        color: COL.blue,
        shape: ai.setup.direction === "long" ? "arrowUp" : "arrowDown",
        text: ai.setup.direction === "long" ? "Mulig LONG" : "Mulig SHORT",
      });
    }
    for (const t of trades.slice(-40)) {
      markers.push({ time: localSec(t.open_ms - (t.open_ms % tfMs)) as Time, position: t.side === "buy" ? "belowBar" : "aboveBar", color: t.side === "buy" ? COL.up : COL.down, shape: t.side === "buy" ? "arrowUp" : "arrowDown", text: "" });
      markers.push({ time: localSec(t.close_ms - (t.close_ms % tfMs)) as Time, position: "inBar", color: t.net >= 0 ? COL.up : COL.down, shape: "circle", text: no(t.net, 0) });
    }
    for (const p of positions) {
      const col = p.side === "buy" ? COL.up : COL.down;
      add(p.entry, col, p.side === "buy" ? "LONG" : "SHORT", LineStyle.Solid);
      if (p.sl) add(p.sl, COL.down, "SL", LineStyle.Dashed);
      if (p.tp) add(p.tp, COL.up, "TP", LineStyle.Dashed);
    }
    markers.sort((x, y) => (x.time as number) - (y.time as number));
    s.setMarkers(markers);
  }, [analysis, ai, tf, overlays, nowMs, positions, trades]);

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={box} className="absolute inset-0" />
      <canvas ref={canvas} className="pointer-events-none absolute inset-0 z-10" />
    </div>
  );
}

export function OverlayToggles({ value, onChange }: { value: Overlays; onChange(v: Overlays): void }) {
  const items: [keyof Overlays, string, string][] = [
    ["levels", "Støtte/motstand", "Grønne/røde stiplede linjer (tykk = høyere tidsramme)"],
    ["trendlines", "Trendlinjer", "Gjennom de to siste svingpunktene; stiplet = brutt"],
    ["volume", "Volumprofil", "Tick-volum per prisnivå siste døgn; gul = POC, blå = verdiområdet (70 %)"],
    ["ai", "AI-oppsett", "Inngangssone, invalidering og mål fra siste AI-vurdering (vises i 30 min)"],
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-tv-muted">
      {items.map(([k, label, help]) => (
        <label key={k} className="flex cursor-pointer items-center gap-1" title={help}>
          <input type="checkbox" checked={value[k]} onChange={(e) => onChange({ ...value, [k]: e.target.checked })} />
          {label}
        </label>
      ))}
    </div>
  );
}
