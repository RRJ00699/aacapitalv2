import test from "node:test";
import assert from "node:assert/strict";
import { buildIpoIndex } from "./ipo-index";
import type { SqlClient } from "./sql";

const mock = (rows: Record<string, unknown>[]): SqlClient =>
  ((_s: TemplateStringsArray, ..._v: unknown[]) => Promise.resolve(rows)) as SqlClient;

test("ipo-index returns rows + generated_at envelope", async () => {
  const out = await buildIpoIndex(mock([{ company_name: "Foo Ltd", sym: "FOO", listing_date: "2026-07-01" }]));
  assert.equal(out.rows.length, 1);
  assert.equal((out.rows[0] as Record<string, unknown>).sym, "FOO");
  assert.ok(typeof out.generated_at === "string" && out.generated_at.length > 0);
});

test("ipo-index tolerates an empty universe", async () => {
  const out = await buildIpoIndex(mock([]));
  assert.deepEqual(out.rows, []);
});
