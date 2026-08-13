import { test } from "node:test";
import assert from "node:assert/strict";
import { interpretCommand, type CommandFetch } from "./ops-view";

test("HTTP 500 → UNAVAILABLE, never 0 or []", () => {
  const v = interpretCommand({ kind: "http-error", status: 500 });
  assert.equal(v.status, "unavailable");
  assert.equal(v.activeCount, null); // UNKNOWN, not 0
  assert.equal(v.completeness, null);
});

test("rejected fetch (network error) → UNAVAILABLE", () => {
  const v = interpretCommand({ kind: "network-error" });
  assert.equal(v.status, "unavailable");
  assert.equal(v.activeCount, null);
});

test("malformed JSON → UNAVAILABLE, never healthy", () => {
  const v = interpretCommand({ kind: "malformed" });
  assert.equal(v.status, "unavailable");
  assert.equal(v.activeCount, null);
});

// 334-4: degraded fallback with empty cards must be UNKNOWN, not 0.
test("degraded snapshot with cards:[] → degraded + UNKNOWN counts", () => {
  const v = interpretCommand({ kind: "ok", json: { degraded: "snapshot unavailable", cards: [] } });
  assert.equal(v.status, "degraded");
  assert.equal(v.activeCount, null);
  assert.equal(v.completeness, null);
});

test("empty but valid snapshot (cards:[], no degraded) → UNKNOWN, never healthy 0", () => {
  const v = interpretCommand({ kind: "ok", json: { cards: [] } });
  assert.equal(v.status, "empty");
  assert.equal(v.activeCount, null);
  assert.equal(v.completeness, null);
});

test("payload missing cards array → UNAVAILABLE", () => {
  const v = interpretCommand({ kind: "ok", json: { foo: "bar" } });
  assert.equal(v.status, "unavailable");
  assert.equal(v.activeCount, null);
});

test("non-object JSON → UNAVAILABLE", () => {
  const v = interpretCommand({ kind: "ok", json: [1, 2, 3] });
  assert.equal(v.status, "unavailable");
});

test("healthy snapshot with real cards → active count + completeness tally", () => {
  const v = interpretCommand({
    kind: "ok",
    json: {
      cards: [
        { state: "OPEN", research: { pipeline_status: "RESEARCH_COMPLETE" } },
        { state: "UPCOMING", research: { pipeline_status: "RESEARCH_PARTIAL" } },
        { state: "LISTING", research: { pipeline_status: "ENRICHED" } },
        { state: "CLOSED", research: { pipeline_status: "RESEARCH_COMPLETE" } }, // not active
      ],
    },
  });
  assert.equal(v.status, "healthy");
  assert.equal(v.activeCount, 3); // OPEN + UPCOMING + LISTING
  assert.deepEqual(v.completeness, { complete: 2, partial: 1, pending: 1 });
});
