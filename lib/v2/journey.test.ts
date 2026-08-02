import test from "node:test";
import assert from "node:assert/strict";
import { computeJourney } from "./journey";

const c = (open: number, high: number, low: number, close: number) => ({ date: "2026-07-01", open, high, low, close, volume: 1000 });

test("no candles -> hasData false", () => {
  const out = computeJourney([], "FOO") as Record<string, unknown>;
  assert.equal(out.hasData, false);
});

test("armed then floor broken -> EXIT", () => {
  // entry 100, peak hits +10% (arms), live forced to 101 (<= +3% floor of 103)
  const rows = [c(100, 100, 100, 100), c(105, 110, 104, 108)];
  const out = computeJourney(rows, "FOO", { price: 101, source: "live" }) as Record<string, unknown>;
  assert.equal(out.armed, true);
  assert.equal(out.decision, "EXIT");
});

test("armed and holding above floor -> HOLD", () => {
  const rows = [c(100, 100, 100, 100), c(108, 112, 107, 111)];
  const out = computeJourney(rows, "FOO", { price: 111, source: "live" }) as Record<string, unknown>;
  assert.equal(out.armed, true);
  assert.equal(out.decision, "HOLD");
});

test("not yet armed -> HOLD with trailing-stop protection", () => {
  const rows = [c(100, 100, 100, 100), c(101, 103, 100, 102)];
  const out = computeJourney(rows, "FOO", { price: 102, source: "live" }) as Record<string, unknown>;
  assert.equal(out.armed, false);
  assert.equal(out.decision, "HOLD");
});
