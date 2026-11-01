import { describe, expect, it } from "vitest";
import { clampGeom, defaultGeom, isValidGeom, MIN_H, MIN_W, moveBy, resizeBy } from "./geometry";

describe("geometry", () => {
  const g = defaultGeom(1920, 1080);
  it("default fits viewport", () => {
    expect(g.x + g.w).toBeLessThanOrEqual(1920);
    expect(g.y + g.h).toBeLessThanOrEqual(1080);
  });
  it("cannot be dragged fully off-screen", () => {
    const far = moveBy(g, 99999, 99999, 1920, 1080);
    expect(far.x).toBeLessThan(1920);
    expect(far.y).toBeLessThan(1080);
    const neg = moveBy(g, -99999, -99999, 1920, 1080);
    expect(neg.x + neg.w).toBeGreaterThan(0);
    expect(neg.y).toBe(0);
  });
  it("respects minimum size", () => {
    const small = resizeBy(g, -9999, -9999, 1920, 1080);
    expect(small.w).toBe(MIN_W);
    expect(small.h).toBe(MIN_H);
  });
  it("re-clamps when window shrinks", () => {
    const c = clampGeom({ ...g, x: 1800 }, 800, 600);
    expect(c.x).toBeLessThan(800);
  });
  it("validates persisted values", () => {
    expect(isValidGeom(g)).toBe(true);
    expect(isValidGeom({ x: 1, y: 2, w: NaN, h: 3, collapsed: false })).toBe(false);
    expect(isValidGeom(null)).toBe(false);
  });
});
