// lib/admin/lane-status.ts — pure lane classification for pipeline step data.
// Presentation logic only: no DB access, no fetch, no new fields. It consumes
// the same shape the existing step board uses (step, ok, error, ran_at) plus the
// shared EXPECTED_LEAN_STEPS contract, and reuses the existing run-in-progress
// rule (app/dashboard/settings StepBoard): while a run is still active, lanes
// that have not been reached yet are PENDING — never "missing", and never a
// prompt to re-run schema sync. Only a completed/stale run may call an absent
// daily lane missing. Unit-tested by lib/admin/lane-status.test.ts.
//
// NOTE: this module is NOT wired to any Neon-backed web route (that would make
// the web plane a recurring DB wake source — see docs/runbooks/PROJECT_CONTROL.md
// zero-wake rule). It is the ready consumer for a future KV-published
// pipeline-health snapshot; until that producer contract exists, the Admin
// overview renders a configuration-required state instead of calling it.

export type StepRow = { step: string; ok: boolean; error?: string | null; ran_at?: string | null };
export type ExpectedStep = { step: string; weekly?: boolean };
export type FailureRow = { step: string; script?: string | null; stderr_tail?: string | null; failed_at?: string | null };

// A lane's health for the latest run:
//   ok      — ran and succeeded
//   failed  — ran and reported an error
//   missing — a completed/stale run finished without this expected daily lane
//   pending — not reached yet (run in progress), no run data, unknown completion,
//             or a weekly-only step on a non-purge day
export type LaneStatus = "ok" | "failed" | "missing" | "pending";

export type Lane = {
  step: string;
  weekly: boolean;
  status: LaneStatus;
  error: string | null;
  ranAt: string | null;
};

// Same threshold the existing StepBoard uses: if the newest step row is within
// 15 minutes, the run is still in progress and absent lanes are suppressed.
export const IN_PROGRESS_MS = 15 * 60 * 1000;

function normalizeStep(s: string): string {
  return s.trim().toLowerCase();
}

// Run completion state, derived the same way as the StepBoard:
//   true  — newest row is older than the in-progress window (run settled/stale)
//   false — newest row is fresh (run still in progress)
//   null  — cannot be determined (no parseable ran_at) → treat as unknown
export function runComplete(steps: StepRow[], now: number): boolean | null {
  let newest: number | null = null;
  for (const s of steps) {
    if (!s.ran_at) continue;
    const t = Date.parse(s.ran_at);
    if (Number.isNaN(t)) continue;
    if (newest == null || t > newest) newest = t;
  }
  if (newest == null) return null;
  return now - newest >= IN_PROGRESS_MS;
}

// Map the latest run's step rows onto the expected lane list, preserving the
// expected order (so "first failing lane" is meaningful for a tired operator).
// `opts.now` defaults to a caller-supplied clock; `opts.complete` overrides the
// derived completion state when a producer supplies an authoritative signal.
export function deriveLanes(
  expected: ExpectedStep[],
  steps: StepRow[],
  opts: { now: number; complete?: boolean | null } = { now: 0 },
): Lane[] {
  const byStep = new Map<string, StepRow>();
  for (const s of steps) byStep.set(normalizeStep(s.step), s);
  const hasRunData = steps.length > 0;
  const weeklyRan = expected.some((e) => e.weekly && byStep.has(normalizeStep(e.step)));
  const complete = opts.complete !== undefined ? opts.complete : runComplete(steps, opts.now);

  return expected.map((e) => {
    const weekly = e.weekly === true;
    const row = byStep.get(normalizeStep(e.step));
    let status: LaneStatus;
    if (row) {
      status = row.ok ? "ok" : "failed";
    } else if (!hasRunData) {
      status = "pending"; // nothing has run — not a failure
    } else if (weekly && !weeklyRan) {
      status = "pending"; // weekly step simply didn't run today
    } else if (complete === true) {
      status = "missing"; // a settled run finished without this daily lane
    } else {
      status = "pending"; // run in progress (false) or unknown completion (null)
    }
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

// Attach the richer stderr traceback tail (from a failures feed) to a lane by
// step name, so a failed lane can surface the real traceback, not a truncated
// step error.
export function tracebackForLane(lane: Lane, failures: FailureRow[]): string | null {
  const match = failures.find((f) => normalizeStep(f.step) === normalizeStep(lane.step));
  return match?.stderr_tail ?? lane.error ?? null;
}
