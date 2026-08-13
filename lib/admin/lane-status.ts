// lib/admin/lane-status.ts — pure derivation for the Admin Operations overview.
// Consumes ONLY fields that already exist in the /api/admin/pipeline-steps and
// /api/admin/pipeline-failures payloads (step, ok, error, ran_at, stderr_tail)
// plus the shared EXPECTED_LEAN_STEPS contract. No DB access, no new fields —
// this is presentation logic, unit-tested by lib/admin/lane-status.test.ts.

export type StepRow = { step: string; ok: boolean; error?: string | null; ran_at?: string | null };
export type ExpectedStep = { step: string; weekly?: boolean };
export type FailureRow = { step: string; script?: string | null; stderr_tail?: string | null; failed_at?: string | null };

// A lane's health for the latest run:
//   ok      — ran and succeeded
//   failed  — ran and reported an error
//   missing — expected in a daily run but absent from the latest run's steps
//   pending — no run data yet, or a weekly-only step on a non-purge day
export type LaneStatus = "ok" | "failed" | "missing" | "pending";

export type Lane = {
  step: string;
  weekly: boolean;
  status: LaneStatus;
  error: string | null;
  ranAt: string | null;
};

function normalizeStep(s: string): string {
  return s.trim().toLowerCase();
}

// Map the latest run's step rows onto the expected lane list, preserving the
// expected order (so "first failing lane" is meaningful for a tired operator).
export function deriveLanes(expected: ExpectedStep[], steps: StepRow[]): Lane[] {
  const byStep = new Map<string, StepRow>();
  for (const s of steps) byStep.set(normalizeStep(s.step), s);
  const hasRunData = steps.length > 0;

  return expected.map((e) => {
    const weekly = e.weekly === true;
    const row = byStep.get(normalizeStep(e.step));
    let status: LaneStatus;
    if (row) status = row.ok ? "ok" : "failed";
    else if (!hasRunData) status = "pending"; // nothing has run — not a failure
    else if (weekly) status = "pending"; // weekly step simply didn't run today
    else status = "missing";
    return {
      step: e.step,
      weekly,
      status,
      error: row?.error ?? null,
      ranAt: row?.ran_at ?? null,
    };
  });
}

// The first lane an operator must act on: a hard failure wins over a missing
// lane; both preserve expected order. Returns null when everything is ok/pending.
export function firstActionableLane(lanes: Lane[]): Lane | null {
  return (
    lanes.find((l) => l.status === "failed") ??
    lanes.find((l) => l.status === "missing") ??
    null
  );
}

export function laneSummary(lanes: Lane[]): {
  ok: number; failed: number; missing: number; pending: number; total: number;
} {
  const s = { ok: 0, failed: 0, missing: 0, pending: 0, total: lanes.length };
  for (const l of lanes) s[l.status] += 1;
  return s;
}

// Latest ran_at across all step rows (the "last pipeline run" timestamp).
export function lastRunAt(steps: StepRow[]): string | null {
  let best: number | null = null;
  let bestRaw: string | null = null;
  for (const s of steps) {
    if (!s.ran_at) continue;
    const t = Date.parse(s.ran_at);
    if (Number.isNaN(t)) continue;
    if (best == null || t > best) { best = t; bestRaw = s.ran_at; }
  }
  return bestRaw;
}

// Attach the richer stderr traceback tail (from pipeline-failures) to a lane by
// step name, so a failed lane can surface the real traceback, not the truncated
// 200-char step error.
export function tracebackForLane(lane: Lane, failures: FailureRow[]): string | null {
  const match = failures.find((f) => normalizeStep(f.step) === normalizeStep(lane.step));
  return match?.stderr_tail ?? lane.error ?? null;
}
