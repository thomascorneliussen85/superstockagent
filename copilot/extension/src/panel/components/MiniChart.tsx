import type { CandleMsg } from "../../shared/protocol";

/** Lightweight SVG candlestick strip. Not a trading chart - TradingView remains the main chart. */
export function MiniChart({ candles, digits }: { candles: CandleMsg[]; digits: number }) {
  const W = 300;
  const H = 90;
  if (candles.length === 0) return <div className="h-[90px] rounded bg-tv-panel" />;
  const hi = Math.max(...candles.map((c) => c.h));
  const lo = Math.min(...candles.map((c) => c.l));
  const range = hi - lo || 1;
  const y = (p: number) => 4 + ((hi - p) / range) * (H - 8);
  const step = W / Math.max(candles.length, 30);
  const bw = Math.max(1, step * 0.6);
  const last = candles[candles.length - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-[90px] w-full rounded bg-tv-panel">
      {candles.map((c, i) => {
        const x = i * step + step / 2;
        const up = c.c >= c.o;
        const color = up ? "#26a69a" : "#ef5350";
        const top = y(Math.max(c.o, c.c));
        const bh = Math.max(1, Math.abs(y(c.o) - y(c.c)));
        return (
          <g key={c.t}>
            <line x1={x} x2={x} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <rect x={x - bw / 2} y={top} width={bw} height={bh} fill={color} />
          </g>
        );
      })}
      <line x1={0} x2={W} y1={y(last.c)} y2={y(last.c)} stroke="#2962ff" strokeDasharray="3 3" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      <title>{`H ${hi.toFixed(digits)} / L ${lo.toFixed(digits)}`}</title>
    </svg>
  );
}
