import test from "node:test";
import assert from "node:assert/strict";
import { runDiagnostic, CHECKS } from "./diagnostics";
import type { SqlClient } from "./sql";

const mock = (rows: Record<string, unknown>[]): SqlClient =>
  ((_s: TemplateStringsArray, ..._v: unknown[]) => Promise.resolve(rows)) as SqlClient;

test("sbi_notes check is removed (returns null)", async () => {
  assert.equal(await runDiagnostic(mock([]), "sbi_notes"), null);
});

test("unknown check returns null", async () => {
  assert.equal(await runDiagnostic(mock([]), "definitely_not_a_check"), null);
});

test("known checks are routed and return rows", async () => {
  for (const c of CHECKS) {
    const rows = await runDiagnostic(mock([{ ok: 1 }]), c);
    assert.ok(Array.isArray(rows), `${c} should return rows`);
  }
});

test("sbi_notes is not in the CHECKS whitelist", () => {
  assert.equal((CHECKS as readonly string[]).includes("sbi_notes"), false);
});
