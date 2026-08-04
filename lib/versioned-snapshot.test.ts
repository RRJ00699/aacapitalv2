import assert from "node:assert/strict";
import test from "node:test";
import { publishVersionedSnapshot, readVersionedSnapshot } from "./versioned-snapshot";

class MemoryKV {
  values = new Map<string, string>();
  async get(k: string) { return this.values.get(k) ?? null; }
  async put(k: string, v: string) { this.values.set(k, v); }
}

const contracts = {
  "ipo-command:v6": { cards: [], filtered: [], filtered_count: 0, live: [], levels: [], blocks: [], post: [], brlm: [], dl: [], track: [] },
  "ipo:index:v3": { rows: [{ company_name: "Example", sym: "EXAMPLE", listing_date: "2026-08-04" }], generated_at: "2026-08-04T00:00:00Z" },
  "journey:candles:v2": { rows: { EXAMPLE: [{ date: "2026-08-04", open: 100, high: 110, low: 99, close: 108, volume: 1 }] }, generated_at: "2026-08-04T00:00:00Z" },
  "ipo-live-preopen:v2": { ok: true, window: "listing_date = IST-today", book_live: false, count: 1, listings: [{ sym: "EXAMPLE", verdict: "WATCH" }], fetchedAt: "2026-08-04T00:00:00Z" },
};

for (const [name, payload] of Object.entries(contracts)) test(`${name}: pipeline publish -> consumer HIT preserves UI contract`, async () => {
  const kv = new MemoryKV(); await publishVersionedSnapshot(kv, name, payload, "v1");
  const hit = await readVersionedSnapshot(kv, name);
  assert.equal(hit?.source, "active"); assert.deepEqual(JSON.parse(hit!.payload), payload);
});

test("active corruption rolls back to previous pointer", async () => {
  const kv = new MemoryKV();
  await publishVersionedSnapshot(kv, "ipo:index:v3", { rows: [{ sym: "OLD" }] }, "v1");
  await publishVersionedSnapshot(kv, "ipo:index:v3", { rows: [{ sym: "NEW" }] }, "v2");
  kv.values.set("snapshot:ipo:index:v3:data:v2", "{corrupt");
  const hit = await readVersionedSnapshot(kv, "ipo:index:v3");
  assert.equal(hit?.source, "previous"); assert.equal(JSON.parse(hit!.payload).rows[0].sym, "OLD");
});
