// Panel position/size maths (pure, unit tested).

export interface PanelGeom {
  x: number;
  y: number;
  w: number;
  h: number;
  collapsed: boolean;
}

export const MIN_W = 280;
export const MIN_H = 220;
export const HEADER_H = 36;
/** Pixels of the header that must remain on screen so the panel can always be grabbed. */
const GRAB_MARGIN = 60;

export function defaultGeom(vw: number, vh: number): PanelGeom {
  const w = 340;
  const h = Math.min(560, Math.max(MIN_H, vh - 140));
  return { x: Math.max(0, vw - w - 70), y: 90, w, h, collapsed: false };
}

export function clampGeom(g: PanelGeom, vw: number, vh: number): PanelGeom {
  const w = Math.max(MIN_W, Math.min(g.w, Math.max(MIN_W, vw)));
  const h = Math.max(MIN_H, Math.min(g.h, Math.max(MIN_H, vh)));
  const x = Math.min(Math.max(g.x, GRAB_MARGIN - w), Math.max(0, vw - GRAB_MARGIN));
  const y = Math.min(Math.max(g.y, 0), Math.max(0, vh - HEADER_H));
  return { ...g, x, y, w, h };
}

export function moveBy(g: PanelGeom, dx: number, dy: number, vw: number, vh: number): PanelGeom {
  return clampGeom({ ...g, x: g.x + dx, y: g.y + dy }, vw, vh);
}

export function resizeBy(g: PanelGeom, dw: number, dh: number, vw: number, vh: number): PanelGeom {
  return clampGeom({ ...g, w: g.w + dw, h: g.h + dh }, vw, vh);
}

export function isValidGeom(v: unknown): v is PanelGeom {
  if (!v || typeof v !== "object") return false;
  const g = v as Record<string, unknown>;
  return ["x", "y", "w", "h"].every((k) => typeof g[k] === "number" && Number.isFinite(g[k])) &&
    typeof g.collapsed === "boolean";
}
