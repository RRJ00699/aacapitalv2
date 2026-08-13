"use client";
// app/dashboard/admin/OperationsOverview.tsx — the 8 AM answer, ZERO-WAKE.
//
// Web-plane rule (docs/runbooks/PROJECT_CONTROL.md): the deployed app must not become a
// recurring Neon wake source. This overview therefore consumes ONLY the
// KV-backed /api/ipo-command snapshot, fetched ONCE on mount plus a manual
// refresh — no interval polling, and NO Neon-backed admin routes
// (/api/admin/pipeline-steps and /api/admin/pipeline-failures are Neon-backed
// and are intentionally NOT called here; see lib/admin/no-neon-contract.test.ts).
//
// Live per-lane pipeline health needs a producer that publishes run health to
// KV (contract: pipeline-health:v1 — recorded in docs/runbooks/PROJECT_CONTROL.md, to be
// built by the next Codex producer task, NOT here). Until it exists, lane health
// renders as a configuration-required state. The pure lane classifier
// (lib/admin/lane-status.ts) is the ready consumer for that snapshot.
//
// Failure handling is centralised in lib/admin/ops-view.ts: a request failure or
// degraded/empty snapshot yields UNKNOWN, never a misleading "healthy 0/0".
import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { interpretCommand, type CommandFetch, type OpsView } from "@/lib/admin/ops-view";
import { LoadingState, FailedState, ConfigRequiredState, ScreenState } from "@/components/ui/states";

const COMMAND_URL = "/api/ipo-command"; // KV-backed snapshot (zero Neon wake)

async function loadCommand(): Promise<CommandFetch> {
  let res: Response;
  try {
    res = await fetch(COMMAND_URL, { cache: "no-store" });
  } catch {
    return { kind: "network-error" };
  }
  if (!res.ok) return { kind: "http-error", status: res.status };
  try {
    return { kind: "ok", json: await res.json() };
  } catch {
    return { kind: "malformed" };
  }
}

// An honest "we don't have this field yet" tile — the requested producer field
// is named so it can be cross-checked against docs/runbooks/PROJECT_CONTROL.md.
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
  const [view, setView] = useState<OpsView | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    setLoaded(false);
    const f = await loadCommand();
    setView(interpretCommand(f));
    setLoaded(true);
  }, []);

  // Fetch once on mount. Deliberately NO setInterval — the deployed app must not
  // poll on a timer. Refresh is manual.
  useEffect(() => { load(); }, [load]);

  return (
    <div style={{ marginBottom: 26 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <h2 style={{ fontSize: 15, fontWeight: 800, color: "var(--c-text)", margin: "0 0 10px", fontFamily: "var(--f-display)" }}>
          Pipeline operations
        </h2>
        <button type="button" onClick={load} style={{
          fontSize: 11, fontWeight: 700, color: "var(--c-text-sub)", background: "var(--c-surface)",
          border: "1px solid var(--c-border)", borderRadius: 999, padding: "5px 12px", cursor: "pointer",
        }}>Refresh</button>
      </div>

      {!loaded || !view ? (
        <LoadingState title="Loading operations snapshot…" source={COMMAND_URL} />
      ) : (
        <>
          {/* Snapshot health banner — never reports healthy on a failed request. */}
          {view.status === "unavailable" ? (
            <FailedState title="Operations snapshot unavailable" detail={view.note ?? undefined} onRetry={load} retryLabel="Refresh" />
          ) : view.status === "degraded" ? (
            <ScreenState kind="stale" title="Snapshot degraded — counts shown as UNKNOWN"
              detail={view.note ?? "The published snapshot is a degraded fallback."} source={COMMAND_URL} onRetry={load} retryLabel="Refresh" />
          ) : view.status === "empty" ? (
            <ScreenState kind="pending" title="Snapshot has no IPO cards"
              detail="Structurally valid but empty — counts are UNKNOWN rather than zero." source={COMMAND_URL} />
          ) : (
            <ScreenState kind="pending" title="Snapshot loaded"
              detail="Active-IPO and completeness figures below are from the published KV snapshot." source={COMMAND_URL} />
          )}

          {/* At-a-glance counts — UNKNOWN (not 0) whenever the snapshot can't be trusted. */}
          <div className="aac-tiles" style={{ marginTop: 12 }}>
            <div style={tile}>
              <div style={tileLabel}>Active IPOs</div>
              <div style={{ ...tileVal, color: view.activeCount == null ? "var(--c-warning)" : "var(--c-text)" }}>
                {view.activeCount == null ? "UNKNOWN" : view.activeCount}
              </div>
            </div>
            <div style={tile}>
              <div style={tileLabel}>Research complete</div>
              <div style={{ ...tileVal, color: "var(--c-positive)" }}>{view.completeness ? view.completeness.complete : "—"}</div>
            </div>
            <div style={tile}>
              <div style={tileLabel}>Research partial</div>
              <div style={{ ...tileVal, color: "var(--c-warning)" }}>{view.completeness ? view.completeness.partial : "—"}</div>
            </div>
            <div style={tile}>
              <div style={tileLabel}>Research pending</div>
              <div style={{ ...tileVal, color: "var(--c-text)" }}>{view.completeness ? view.completeness.pending : "—"}</div>
            </div>
          </div>
          {view.completeness == null && (
            <div style={{ fontSize: 11, color: "var(--c-text-meta)", marginTop: 6 }}>
              Completeness totals are UNKNOWN while the snapshot is degraded, empty, or unavailable — not shown as zero.
            </div>
          )}
        </>
      )}

      {/* Per-lane pipeline health — needs a KV producer that this web page can
          read without waking Neon. Until that contract ships, this is an honest
          configuration-required state, not a fabricated board. */}
      <div style={{ marginTop: 14 }}>
        <ConfigRequiredState
          title="Per-lane pipeline health — awaiting KV producer"
          detail={
            <>
              Live lane status (first failing lane + traceback) requires the pipeline to publish run
              health to KV so the web app can read it without a Neon query. The classifier is ready
              (lib/admin/lane-status.ts); the producer is a separate Codex task. Use the job runner
              below to trigger runs meanwhile.
            </>
          }
          source="pipeline-health:v1 (KV) — not yet published"
        />
      </div>

      {/* Honest unavailable fields — each names the exact producer field wanted.
          Logged in docs/runbooks/PROJECT_CONTROL.md → payload_fields_unavailable. */}
      <div style={{ marginTop: 14 }}>
        <div style={{ ...tileLabel, marginBottom: 6 }}>Requested, not yet in any KV payload</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
          <Unavailable label="Last run + per-lane status" field="pipeline-health:v1 (KV): steps[]{step,ok,ran_at}, expected[]" />
          <Unavailable label="Per-lane duration" field="pipeline-health:v1: steps[].duration_ms" />
          <Unavailable label="Failed-step traceback" field="pipeline-health:v1: failures[].stderr_tail" />
          <Unavailable label="Owner-action queue" field="admin.owner_action_queue[]" />
          <Unavailable label="Config-required lanes" field="pipeline-health:v1: steps[].config_required" />
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
