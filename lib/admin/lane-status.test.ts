import { test } from "node:test";
import assert from "node:assert/strict";
import {
  deriveLanes,
  firstActionableLane,
  laneSummary,
  lastRunAt,
  tracebackForLane,
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

test("all ok when every expected step ran and succeeded", () => {
  const steps: StepRow[] = [
    { step: "schema sync (single owner of DDL)", ok: true, ran_at: "2026-08-13T02:00:00Z" },
    { step: "NSE discovery (new IPOs)", ok: true, ran_at: "2026-08-13T02:01:00Z" },
    { step: "refresh GMP", ok: true, ran_at: "2026-08-13T02:02:00Z" },
    { step: "purge post-lock candles", ok: true, ran_at: "2026-08-13T02:03:00Z" },
    { step: "health-check (gate)", ok: true, ran_at: "2026-08-13T02:04:00Z" },
  ];
  const lanes = deriveLanes(EXPECTED, steps);
  assert.equal(laneSummary(lanes).ok, 5);
  assert.equal(firstActionableLane(lanes), null);
});

test("a failed step is the first actionable lane, in expected order", () => {
  const steps: StepRow[] = [
    { step: "schema sync (single owner of DDL)", ok: true, ran_at: "2026-08-13T02:00:00Z" },
    { step: "NSE discovery (new IPOs)", ok: false, error: "NSE 503", ran_at: "2026-08-13T02:01:00Z" },
    { step: "refresh GMP", ok: false, error: "gmp timeout", ran_at: "2026-08-13T02:02:00Z" },
  ];
  const lanes = deriveLanes(EXPECTED, steps);
  const first = firstActionableLane(lanes);
  assert.equal(first?.step, "NSE discovery (new IPOs)");
  assert.equal(first?.status, "failed");
});

test("missing non-weekly step is 'missing'; missing weekly step is 'pending'", () => {
  const steps: StepRow[] = [
    { step: "schema sync (single owner of DDL)", ok: true, ran_at: "2026-08-13T02:00:00Z" },
    // NSE discovery, refresh GMP, purge, health-check all absent
  ];
  const lanes = deriveLanes(EXPECTED, steps);
  const byStep = Object.fromEntries(lanes.map((l) => [l.step, l.status]));
  assert.equal(byStep["NSE discovery (new IPOs)"], "missing");
  assert.equal(byStep["purge post-lock candles"], "pending"); // weekly — not run daily
  const first = firstActionableLane(lanes);
  assert.equal(first?.status, "missing");
  assert.equal(first?.step, "NSE discovery (new IPOs)");
});

test("no run data at all → every lane pending, nothing actionable", () => {
  const lanes = deriveLanes(EXPECTED, []);
  assert.equal(laneSummary(lanes).pending, 5);
  assert.equal(firstActionableLane(lanes), null);
  assert.equal(lastRunAt([]), null);
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
  const steps: StepRow[] = [{ step: "refresh GMP", ok: false, error: "short err", ran_at: null }];
  const lanes = deriveLanes(EXPECTED, steps);
  const gmp = lanes.find((l) => l.step === "refresh GMP")!;
  const tb = tracebackForLane(gmp, [
    { step: "refresh GMP", stderr_tail: "Traceback (most recent call last): ... long tail", failed_at: null },
  ]);
  assert.match(tb ?? "", /Traceback/);
});
