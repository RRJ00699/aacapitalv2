import { test } from "node:test";
import assert from "node:assert/strict";
import {
  deriveLanes,
  firstActionableLane,
  laneSummary,
  lastRunAt,
  runComplete,
  tracebackForLane,
  IN_PROGRESS_MS,
  type ExpectedStep,
  type StepRow,
} from "./lane-status";

const EXPECTED: ExpectedStep[] = [
  { step: "schema sync (single owner of DDL)" },
  { step: "NSE discovery (new IPOs)" },
  { step: "refresh GMP" },
  { step: "purge post-lock candles", weekly: true },
  { step: "health-check (gate)" },
];

// A fixed clock (Date.now is unavailable in some sandboxes; always pass `now`).
const T0 = Date.parse("2026-08-13T02:00:00Z");
const settled = { now: T0 + IN_PROGRESS_MS + 60_000 }; // run finished > 15m ago
const active = { now: T0 + 60_000 }; // newest row 1m old → run in progress

test("all ok when every expected step ran and succeeded (settled run)", () => {
  const steps: StepRow[] = EXPECTED.map((e, i) => ({
    step: e.step, ok: true, ran_at: new Date(T0 + i * 1000).toISOString(),
  }));
  const lanes = deriveLanes(EXPECTED, steps, settled);
  assert.equal(laneSummary(lanes).ok, 5);
  assert.equal(firstActionableLane(lanes), null);
});

test("a failed step is the first actionable lane, in expected order", () => {
  const steps: StepRow[] = [
    { step: "schema sync (single owner of DDL)", ok: true, ran_at: new Date(T0).toISOString() },
    { step: "NSE discovery (new IPOs)", ok: false, error: "NSE 503", ran_at: new Date(T0 + 1000).toISOString() },
    { step: "refresh GMP", ok: false, error: "gmp timeout", ran_at: new Date(T0 + 2000).toISOString() },
  ];
  const lanes = deriveLanes(EXPECTED, steps, settled);
  const first = firstActionableLane(lanes);
  assert.equal(first?.step, "NSE discovery (new IPOs)");
  assert.equal(first?.status, "failed");
});

// 334-3: run-in-progress must NOT be classified as missing.
test("first step emitted during an ACTIVE run → later lanes pending, nothing actionable", () => {
  const steps: StepRow[] = [
    // Newest row is fresh → run in progress; the rest simply haven't been reached.
    { step: "schema sync (single owner of DDL)", ok: true, ran_at: new Date(active.now - 30_000).toISOString() },
  ];
  const lanes = deriveLanes(EXPECTED, steps, active);
  const byStep = Object.fromEntries(lanes.map((l) => [l.step, l.status]));
  assert.equal(byStep["NSE discovery (new IPOs)"], "pending");
  assert.equal(byStep["health-check (gate)"], "pending");
  assert.equal(laneSummary(lanes).missing, 0);
  assert.equal(firstActionableLane(lanes), null); // never tells the owner to run schema mid-run
});

test("COMPLETED run missing a required daily lane → missing", () => {
  const steps: StepRow[] = [
    { step: "schema sync (single owner of DDL)", ok: true, ran_at: new Date(T0).toISOString() },
    // NSE discovery, refresh GMP, health-check absent; run settled > 15m ago.
  ];
  const lanes = deriveLanes(EXPECTED, steps, settled);
  const byStep = Object.fromEntries(lanes.map((l) => [l.step, l.status]));
  assert.equal(byStep["NSE discovery (new IPOs)"], "missing");
  assert.equal(byStep["health-check (gate)"], "missing");
  const first = firstActionableLane(lanes);
  assert.equal(first?.status, "missing");
  assert.equal(first?.step, "NSE discovery (new IPOs)");
});

test("weekly lane absent on a normal (settled) day → pending, not missing", () => {
  const steps: StepRow[] = EXPECTED
    .filter((e) => !e.weekly)
    .map((e, i) => ({ step: e.step, ok: true, ran_at: new Date(T0 + i * 1000).toISOString() }));
  const lanes = deriveLanes(EXPECTED, steps, settled);
  const purge = lanes.find((l) => l.step === "purge post-lock candles")!;
  assert.equal(purge.status, "pending");
  assert.equal(firstActionableLane(lanes), null);
});

test("no run data at all → every lane pending, nothing actionable", () => {
  const lanes = deriveLanes(EXPECTED, [], settled);
  assert.equal(laneSummary(lanes).pending, 5);
  assert.equal(firstActionableLane(lanes), null);
  assert.equal(lastRunAt([]), null);
});

test("unknown completion (no parseable ran_at) never yields 'missing'", () => {
  const steps: StepRow[] = [{ step: "schema sync (single owner of DDL)", ok: true, ran_at: null }];
  assert.equal(runComplete(steps, T0), null);
  const lanes = deriveLanes(EXPECTED, steps, { now: T0 });
  assert.equal(laneSummary(lanes).missing, 0);
});

test("runComplete: fresh row = in progress (false); stale row = complete (true)", () => {
  const fresh: StepRow[] = [{ step: "a", ok: true, ran_at: new Date(active.now - 60_000).toISOString() }];
  const stale: StepRow[] = [{ step: "a", ok: true, ran_at: new Date(T0).toISOString() }];
  assert.equal(runComplete(fresh, active.now), false);
  assert.equal(runComplete(stale, settled.now), true);
});

test("lastRunAt returns the newest ran_at", () => {
  const steps: StepRow[] = [
    { step: "a", ok: true, ran_at: "2026-08-13T02:00:00Z" },
    { step: "b", ok: true, ran_at: "2026-08-13T02:05:00Z" },
    { step: "c", ok: true, ran_at: null },
  ];
  assert.equal(lastRunAt(steps), "2026-08-13T02:05:00Z");
});

test("tracebackForLane prefers the full stderr tail over the truncated step error", () => {
  const steps: StepRow[] = [{ step: "refresh GMP", ok: false, error: "short err", ran_at: new Date(T0).toISOString() }];
  const lanes = deriveLanes(EXPECTED, steps, settled);
  const gmp = lanes.find((l) => l.step === "refresh GMP")!;
  const tb = tracebackForLane(gmp, [
    { step: "refresh GMP", stderr_tail: "Traceback (most recent call last): ... long tail", failed_at: null },
  ]);
  assert.match(tb ?? "", /Traceback/);
});
