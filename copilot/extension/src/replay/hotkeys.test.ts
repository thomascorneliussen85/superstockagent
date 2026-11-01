import { describe, expect, it } from "vitest";
import { actionFor, comboOf, DEFAULT_HOTKEYS, nextSpeed, orderRisk } from "./hotkeys";

const ev = (key: string, mods: Partial<{ shiftKey: boolean; ctrlKey: boolean; altKey: boolean; metaKey: boolean }> = {}) => ({
  key, shiftKey: false, ctrlKey: false, altKey: false, metaKey: false, ...mods,
});

describe("hotkeys", () => {
  it("normalises combos", () => {
    expect(comboOf(ev("b"))).toBe("B");
    expect(comboOf(ev(" "))).toBe("Space");
    expect(comboOf(ev("ArrowRight", { shiftKey: true }))).toBe("Shift+ArrowRight");
    expect(comboOf(ev("+", { shiftKey: true }))).toBe("+");
    expect(actionFor("B", DEFAULT_HOTKEYS)).toBe("buy");
    expect(actionFor("Q", DEFAULT_HOTKEYS)).toBeNull();
  });
  it("steps speeds", () => {
    expect(nextSpeed(1, 1)).toBe(2);
    expect(nextSpeed(60, 1)).toBe(60);
    expect(nextSpeed(5, -1)).toBe(2);
  });
  it("computes order risk in money, never assuming lots = ounces", () => {
    const r = orderRisk(0.1, 100, 2, 4, 7);
    expect(r.oz).toBe(10);
    expect(r.risk).toBeCloseTo(20.7);
    expect(r.reward).toBeCloseTo(39.3);
    expect(orderRisk(10, 100, 2, 4, 7).risk).toBeCloseTo(2070);
  });
});
