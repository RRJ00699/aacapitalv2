// lib/admin/ops-view.ts — pure interpreter for the KV-backed /api/ipo-command
// payload, used by the Admin Operations overview. It exists so failure handling
// is unit-testable (lib/admin/ops-view.test.ts) and consistent:
//   • a request failure (HTTP error, rejected fetch, malformed JSON) is NEVER
//     turned into [] — it becomes UNAVAILABLE;
//   • a degraded snapshot, or an empty/absent cards array, yields UNKNOWN counts
//     rather than a misleading 0/0 "healthy";
//   • only a valid snapshot with real cards produces numbers.
// This module does no I/O — the caller performs the fetch and hands the result
// in as a discriminated `CommandFetch`.

// The result of attempting to load /api/ipo-command, classified by the caller.
export type CommandFetch =
  | { kind: "ok"; json: unknown }        // response.ok AND JSON parsed
  | { kind: "http-error"; status: number } // response returned but not ok
  | { kind: "malformed" }                 // response ok but JSON.parse failed
  | { kind: "network-error" };            // fetch itself rejected

export type OpsStatus = "healthy" | "degraded" | "empty" | "unavailable";

export type OpsView = {
  status: OpsStatus;
  // null means UNKNOWN — the UI must render "UNKNOWN", never 0.
  activeCount: number | null;
  completeness: { complete: number; partial: number; pending: number } | null;
  note: string | null;
};

const ACTIVE_STATES = new Set(["OPEN", "LISTING", "UPCOMING", "INWINDOW"]);

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function interpretCommand(f: CommandFetch): OpsView {
  // Any transport/parse failure → UNAVAILABLE. Never a zero, never an empty list.
  if (f.kind === "network-error") return unavailable("request failed (network)");
  if (f.kind === "malformed") return unavailable("malformed response (not JSON)");
  if (f.kind === "http-error") return unavailable(`request failed (HTTP ${f.status})`);

  const json = f.json;
  if (!isObject(json)) return unavailable("unexpected payload shape");

  // A degraded fallback snapshot cannot be trusted for counts → UNKNOWN.
  if (json.degraded) {
    return { status: "degraded", activeCount: null, completeness: null, note: String(json.degraded) };
  }

  // Contract check: cards must be an array. Anything else is unavailable, not 0.
  const cards = json.cards;
  if (!Array.isArray(cards)) return unavailable("payload missing a cards array");

  // An empty (but structurally valid) snapshot is ambiguous — "no IPOs" vs "not
  // populated". Report UNKNOWN rather than a confident 0.
  if (cards.length === 0) {
    return { status: "empty", activeCount: null, completeness: null, note: "snapshot has no cards" };
  }

  let active = 0;
  const completeness = { complete: 0, partial: 0, pending: 0 };
  for (const c of cards) {
    const card = isObject(c) ? c : {};
    const state = String(card.state ?? "").toUpperCase();
    if (ACTIVE_STATES.has(state)) active += 1;
    const research = isObject(card.research) ? card.research : {};
    const pipelineStatus = String(research.pipeline_status ?? "");
    if (pipelineStatus === "RESEARCH_COMPLETE") completeness.complete += 1;
    else if (pipelineStatus === "RESEARCH_PARTIAL") completeness.partial += 1;
    else completeness.pending += 1;
  }
  return { status: "healthy", activeCount: active, completeness, note: null };
}

function unavailable(note: string): OpsView {
  return { status: "unavailable", activeCount: null, completeness: null, note };
}
