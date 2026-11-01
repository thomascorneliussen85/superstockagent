// Small SVG charts in the TradingView palette. One y-axis per chart; hover
// layer (crosshair + tooltip) on every chart; text in text colours only.
import { useMemo, useRef, useState, type ReactNode } from "react";

const C = { grid: "#2a2e39", axis: "#787b86", up: "#26a69a", down: "#ef5350", line: "#2962ff", text: "#d1d4dc" };

function niceTicks(min: number, max: number, n = 4): number[] {
  if (min === max) return [min];
  const span = max - min;
  const step = 10 ** Math.floor(Math.log10(span / n));
  const err = (span / n) / step;
  const s = step * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1);
  const out = [];
  for (let v = Math.ceil(min / s) * s; v <= max + 1e-9; v += s) out.push(+v.toFixed(10));
  return out;
}

const fmt = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1).replace(".", ",")}k` : v.toFixed(Math.abs(v) < 10 ? 2 : 0).replace(".", ","));

interface Frame {
  width?: number;
  height?: number;
  title: string;
  empty?: boolean;
  children: (dims: { w: number; h: number; pad: { l: number; r: number; t: number; b: number } }) => ReactNode;
}

function Frame({ height = 180, title, empty, children }: Frame) {
  const w = 600;
  const pad = { l: 44, r: 10, t: 8, b: 20 };
  return (
    <figure className="rounded border border-tv-border bg-tv-panel p-3">
      <figcaption className="mb-1 text-xs text-tv-muted">{title}</figcaption>
      {empty ? (
        <p className="py-8 text-center text-xs text-tv-muted">Ingen data ennå</p>
      ) : (
        <div className="relative">{children({ w, h: height, pad })}</div>
      )}
    </figure>
  );
}

export function LineChart({
  title, points, label, color = C.line, fill = false, height,
}: { title: string; points: { x: number; y: number }[]; label: (p: { x: number; y: number }) => string; color?: string; fill?: boolean; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const ys = points.map((p) => p.y);
  const lo = Math.min(0, ...ys);
  const hi = Math.max(0, ...ys);
  return (
    <Frame title={title} empty={points.length === 0} height={height}>
      {({ w, h, pad }) => {
        const x = (i: number) => pad.l + (i / Math.max(1, points.length - 1)) * (w - pad.l - pad.r);
        const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
        const d = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.y)}`).join(" ");
        const onMove = (e: React.PointerEvent) => {
          const r = ref.current!.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * w;
          const i = Math.round(((px - pad.l) / (w - pad.l - pad.r)) * (points.length - 1));
          setHover(Math.max(0, Math.min(points.length - 1, i)));
        };
        return (
          <>
            <svg ref={ref} viewBox={`0 0 ${w} ${h}`} className="w-full" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
              {niceTicks(lo, hi).map((t) => (
                <g key={t}>
                  <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={C.grid} strokeWidth={t === 0 ? 1.5 : 1} />
                  <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill={C.axis}>{fmt(t)}</text>
                </g>
              ))}
              {fill && <path d={`${d} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill={color} opacity={0.15} />}
              <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
              {hover != null && (
                <>
                  <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={h - pad.b} stroke={C.axis} strokeDasharray="3 3" />
                  <circle cx={x(hover)} cy={y(points[hover].y)} r={4} fill={color} stroke="#1e222d" strokeWidth={2} />
                </>
              )}
            </svg>
            {hover != null && <Tip leftPct={(x(hover) / w) * 100}>{label(points[hover])}</Tip>}
          </>
        );
      }}
    </Frame>
  );
}

export function BarChart({
  title, bars, label, height,
}: { title: string; bars: { key: string; v: number }[]; label: (b: { key: string; v: number }) => string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const lo = Math.min(0, ...bars.map((b) => b.v));
  const hi = Math.max(0, ...bars.map((b) => b.v));
  return (
    <Frame title={title} empty={bars.length === 0} height={height}>
      {({ w, h, pad }) => {
        const bw = (w - pad.l - pad.r) / Math.max(1, bars.length);
        const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
        const showLabels = bars.length <= 24;
        return (
          <>
            <svg viewBox={`0 0 ${w} ${h}`} className="w-full" onPointerLeave={() => setHover(null)}>
              {niceTicks(lo, hi).map((t) => (
                <g key={t}>
                  <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={C.grid} strokeWidth={t === 0 ? 1.5 : 1} />
                  <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill={C.axis}>{fmt(t)}</text>
                </g>
              ))}
              {bars.map((b, i) => {
                const x0 = pad.l + i * bw + 1;
                const top = Math.min(y(b.v), y(0));
                const hh = Math.max(1, Math.abs(y(b.v) - y(0)));
                return (
                  <g key={b.key} onPointerEnter={() => setHover(i)}>
                    <rect x={pad.l + i * bw} y={pad.t} width={bw} height={h - pad.t - pad.b} fill="transparent" />
                    <rect x={x0} y={top} width={Math.max(1, bw - 2)} height={hh} rx={Math.min(4, bw / 4)}
                      fill={b.v >= 0 ? C.up : C.down} opacity={hover == null || hover === i ? 1 : 0.55} />
                    {showLabels && (
                      <text x={x0 + bw / 2 - 1} y={h - 6} textAnchor="middle" fontSize={9} fill={C.axis}>{b.key}</text>
                    )}
                  </g>
                );
              })}
            </svg>
            {hover != null && <Tip leftPct={((pad.l + (hover + 0.5) * bw) / w) * 100}>{label(bars[hover])}</Tip>}
          </>
        );
      }}
    </Frame>
  );
}

function Tip({ leftPct, children }: { leftPct: number; children: ReactNode }) {
  return (
    <div
      className="pointer-events-none absolute top-1 z-10 whitespace-pre rounded border border-tv-border bg-tv-bg px-2 py-1 text-[11px] text-tv-text shadow"
      style={{ left: `${Math.min(80, Math.max(2, leftPct))}%` }}
    >
      {children}
    </div>
  );
}

export function useSorted<T>(rows: T[], key: (r: T) => number) {
  return useMemo(() => [...rows].sort((a, b) => key(b) - key(a)), [rows, key]);
}
