"use client";
// app/dashboard/admin/OperationsOverview.tsx — the 8 AM answer.
// Surfaces the latest pipeline run health from EXISTING authenticated APIs only
// (/api/admin/pipeline-steps, /api/admin/pipeline-failures, /api/ipo-command).
// The whole point: a tired owner identifies the first failing lane and the
// required action in under five minutes. Fields the current payloads don't
// carry are shown as an honest "Not available from current payload" — never a
// fabricated number — and the exact producer request is logged in
// docs/PROJECT_CONTROL.md.
import { useCallback, useEffect, useState, type CSSProperties } from "react";
import {
  deriveLanes,
  firstActionableLane,
  laneSummary,
  lastRunAt,
  tracebackForLane,
  type ExpectedStep,
  type StepRow,
  type FailureRow,
  type Lane,
} from "@/lib/admin/lane-status";
import { LoadingState, FailedState, PendingState, ScreenState } from "@/components/ui/states";

type StepsPayload = { ok: boolean; steps?: StepRow[]; expected?: ExpectedStep[]; error?: string };
type FailuresPayload = { ok: boolean; failures?: FailureRow[]; error?: string };
type CommandPayload = { cards?: Record<string, unknown>[]; filtered_count?: number; degraded?: string };

const LANE_TOKEN: Record<Lane["status"], { fg: string; bg: string; bd: string; label: string }> = {
  ok: { fg: "var(--c-positive)", bg: "var(--c-positive-bg)", bd: "var(--c-positive-bd)", label: "OK" },
  failed: { fg: "var(--c-negative)", bg: "var(--c-negative-bg)", bd: "var(--c-negative-bd)", label: "FAILED" },
  missing: { fg: "var(--c-warning)", bg: "var(--c-warning-bg)", bd: "var(--c-warning-bd)", label: "MISSING" },
  pending: { fg: "var(--c-text-meta)", bg: "var(--c-surface-2)", bd: "var(--c-border)", label: "PENDING" },
};

function fmt(iso: string | null): string {
  if (!iso) return "unknown";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return String(iso);
  return new Date(t).toLocaleString();
}

// An honest "we don't have this field yet" tile — the requested producer field
// is named so it can be cross-checked against PROJECT_CONTROL.
function Unavailable({ label, field }: { label: string; field: string }) {
  return (
    <div style={{ border: "1px dashed var(--c-border)", borderRadius: 10, padding: "9px 11px", background: "var(--c-surface)" }}>
      <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.4, textTransform: "uppercase", color: "var(--c-text-meta)" }}>{label}</div>
      <div style={{ fontSize: 11.5, color: "var(--c-text-sub)", marginTop: 3 }}>Not available from current payload</div>
      <div style={{ fontSize: 9.5, color: "var(--c-text-meta)", marginTop: 3, fontFamily: "var(--f-mono)" }}>needs: {field}</div>
    </div>
  );
}

export default function OperationsOverview() {
  const [steps, setSteps] = useState<StepsPayload | null>(null);
  const [failures, setFailures] = useState<FailuresPayload | null>(null);
  const [command, setCommand] = useState<CommandPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, f, c] = await Promise.all([
        fetch("/api/admin/pipeline-steps", { cache: "no-store" }).then((r) => r.json()).catch(() => null),
        fetch("/api/admin/pipeline-failures", { cache: "no-store" }).then((r) => r.json()).catch(() => null),
        fetch("/api/ipo-command", { cache: "no-store" }).then((r) => r.json()).catch(() => null),
      ]);
      setSteps(s);
      setFailures(f);
      setCommand(c);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "network error");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  if (!loaded) {
    return <LoadingState title="Loading pipeline operations…" />;
  }
  if (err) {
    return <FailedState title="Could not load operations" detail={err} onRetry={load} />;
  }

  const expected = steps?.expected ?? [];
  const stepRows = steps?.steps ?? [];
  const failureRows = failures?.failures ?? [];
  const lanes = deriveLanes(expected, stepRows);
  const summary = laneSummary(lanes);
  const runAt = lastRunAt(stepRows);
  const firstBad = firstActionableLane(lanes);

  const noRunData = stepRows.length === 0 && expected.length > 0;
  const cards = command?.cards ?? [];
  // Active IPO count — derived from card.state; UNKNOWN when the snapshot is
  // absent (never rendered as 0, which would read as "nothing live").
  const activeStates = new Set(["OPEN", "LISTING", "UPCOMING", "INWINDOW"]);
  const activeCount = command == null
    ? null
    : cards.filter((c) => activeStates.has(String((c as { state?: unknown }).state ?? "").toUpperCase())).length;
  // Completeness — counts from the research block already in the payload.
  const completeness = { complete: 0, partial: 0, pending: 0 };
  for (const c of cards) {
    const status = String(((c as { research?: { pipeline_status?: unknown } }).research?.pipeline_status) ?? "");
    if (status === "RESEARCH_COMPLETE") completeness.complete += 1;
    else if (status === "RESEARCH_PARTIAL") completeness.partial += 1;
    else completeness.pending += 1;
  }

  const overallFg = summary.failed > 0 ? "var(--c-negative)" : summary.missing > 0 ? "var(--c-warning)" : "var(--c-positive)";

  return (
    <div style={{ marginBottom: 26 }}>
      <h2 style={{ fontSize: 15, fontWeight: 800, color: "var(--c-text)", margin: "0 0 10px", fontFamily: "var(--f-display)" }}>
        Pipeline operations · last run
      </h2>

      {/* THE 8 AM ANSWER — first failing lane + required action, or all-clear. */}
      {noRunData ? (
        <PendingState
          title="No pipeline run recorded yet"
          detail="No step rows for a recent run. Run the pipeline job below; this panel fills in once steps report."
          source="pipeline_step_runs"
        />
      ) : firstBad ? (
        <ScreenState
          kind={firstBad.status === "failed" ? "error" : "pending"}
          title={`First lane needing action: ${firstBad.step}`}
          detail={
            <>
              {firstBad.status === "failed"
                ? "This lane ran and reported an error. Read the traceback, fix the cause, then re-run the pipeline job."
                : "This lane was expected in the latest run but did not report. Re-run schema sync, then the pipeline job."}
              {(() => {
                const tb = tracebackForLane(firstBad, failureRows);
                return tb ? (
                  <pre style={{
                    margin: "8px 0 0", fontSize: 11, lineHeight: 1.5, fontFamily: "var(--f-mono)",
                    color: "#C7D2FE", background: "#0B1020", borderRadius: 8, padding: "10px 12px",
                    overflowX: "auto", maxHeight: 220, whiteSpace: "pre-wrap",
                  }}>{tb.slice(-2000)}</pre>
                ) : null;
              })()}
            </>
          }
          source="pipeline_step_runs + pipeline_failures"
          asOf={fmt(runAt)}
          onRetry={load}
          retryLabel="Refresh"
        />
      ) : (
        <div role="status" style={{
          background: "var(--c-positive-bg)", border: "1px solid var(--c-positive-bd)",
          borderRadius: "var(--radius-3)", padding: "14px 16px",
        }}>
          <div style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
            <span aria-hidden style={{ color: "var(--c-positive)", fontWeight: 800, fontSize: 14 }}>✓</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--c-positive)" }}>All lanes healthy</div>
              <div style={{ fontSize: 11.5, color: "var(--c-text-sub)", marginTop: 3 }}>
                {summary.ok} of {summary.total} lanes ok · {summary.pending} pending (weekly/awaiting).
              </div>
              <div style={{ fontSize: 10.5, color: "var(--c-text-meta)", marginTop: 6, fontFamily: "var(--f-mono)" }}>
                source: pipeline_step_runs · as of {fmt(runAt)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* At-a-glance counts */}
      <div className="aac-tiles" style={{ marginTop: 12 }}>
        <div style={{ ...tile, borderColor: "var(--c-border)" }}>
          <div style={tileLabel}>Overall</div>
          <div style={{ ...tileVal, color: overallFg }}>{summary.failed > 0 ? "FAILING" : summary.missing > 0 ? "PARTIAL" : "HEALTHY"}</div>
        </div>
        <div style={tile}><div style={tileLabel}>Lanes ok</div><div style={{ ...tileVal, color: "var(--c-positive)" }}>{summary.ok}/{summary.total}</div></div>
        <div style={tile}><div style={tileLabel}>Failed</div><div style={{ ...tileVal, color: summary.failed ? "var(--c-negative)" : "var(--c-text)" }}>{summary.failed}</div></div>
        <div style={tile}><div style={tileLabel}>Missing</div><div style={{ ...tileVal, color: summary.missing ? "var(--c-warning)" : "var(--c-text)" }}>{summary.missing}</div></div>
        <div style={tile}>
          <div style={tileLabel}>Active IPOs</div>
          <div style={{ ...tileVal, color: "var(--c-text)" }}>{activeCount == null ? "UNKNOWN" : activeCount}</div>
        </div>
        <div style={tile}>
          <div style={tileLabel}>Last run</div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--c-text-sub)", marginTop: 3 }}>{fmt(runAt)}</div>
        </div>
      </div>

      {/* Completeness summary from the command payload's research block */}
      <div style={{ marginTop: 12, border: "1px solid var(--c-border)", borderRadius: 10, padding: "10px 12px", background: "var(--c-surface)" }}>
        <div style={tileLabel}>Research completeness (published snapshot)</div>
        {command?.degraded ? (
          <div style={{ fontSize: 11.5, color: "var(--c-warning)", marginTop: 4 }}>Snapshot degraded — {String(command.degraded)}</div>
        ) : cards.length === 0 ? (
          <div style={{ fontSize: 11.5, color: "var(--c-text-sub)", marginTop: 4 }}>No cards in the current snapshot.</div>
        ) : (
          <div style={{ fontSize: 12.5, color: "var(--c-text-sub)", marginTop: 4 }}>
            {completeness.complete} complete · {completeness.partial} partial · {completeness.pending} pending
            {typeof command?.filtered_count === "number" && command.filtered_count > 0
              ? ` · ${command.filtered_count} filtered out (junk floor)` : ""}
          </div>
        )}
      </div>

      {/* Per-lane grid — expected order, first failure obvious at a glance */}
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 6 }}>
        {lanes.map((l) => {
          const t = LANE_TOKEN[l.status];
          return (
            <div key={l.step} title={l.error ?? undefined} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
              border: `1px solid ${t.bd}`, background: t.bg, borderRadius: 8, padding: "6px 9px",
            }}>
              <span style={{ fontSize: 11, color: "var(--c-text-sub)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {l.step}{l.weekly ? " ·wk" : ""}
              </span>
              <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: 0.4, color: t.fg, flexShrink: 0 }}>{t.label}</span>
            </div>
          );
        })}
      </div>

      {/* Honest unavailable fields — each names the exact producer field wanted.
          These are logged in docs/PROJECT_CONTROL.md → payload_fields_unavailable. */}
      <div style={{ marginTop: 14 }}>
        <div style={{ ...tileLabel, marginBottom: 6 }}>Requested, not yet in any payload</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
          <Unavailable label="Per-lane duration" field="pipeline_step_runs.duration_ms" />
          <Unavailable label="Owner-action queue" field="admin.owner_action_queue[]" />
          <Unavailable label="Config-required lanes" field="pipeline_step_runs.config_required" />
          <Unavailable label="Retry / pending docs" field="rhp.retry_pending_count" />
          <Unavailable label="Paid-call status / cap" field="admin.paid_call_status{used,cap}" />
        </div>
      </div>
    </div>
  );
}

const tile: CSSProperties = {
  background: "var(--c-surface)", border: "1px solid var(--c-border)", borderRadius: 10, padding: "9px 11px", minWidth: 0,
};
const tileLabel: CSSProperties = {
  fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, textTransform: "uppercase", color: "var(--c-text-meta)",
};
const tileVal: CSSProperties = {
  fontSize: 16, fontWeight: 800, fontFamily: "var(--f-mono)", marginTop: 2,
};
