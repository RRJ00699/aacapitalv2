import assert from "node:assert/strict";
import test from "node:test";
import { publishVersionedSnapshot, readStrict, readVersionedSnapshot, setKvStoreForTests, type KV } from "./kv-cache";

function memory(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  let puts = 0;
  const kv: KV = { get: async key => data.get(key) ?? null, put: async (key, value) => { puts++; data.set(key, value); } };
  return { kv, data, get puts() { return puts; } };
}

test("strict primary, stale, and total miss perform reads only", async () => {
  const primary = memory({ feed: '{"ok":1}' }); setKvStoreForTests(primary.kv);
  assert.deepEqual(await readStrict("feed"), { payload: '{"ok":1}', source: "primary" });
  const stale = memory({ "feed:stale": '{"ok":2}' }); setKvStoreForTests(stale.kv);
  assert.deepEqual(await readStrict("feed"), { payload: '{"ok":2}', source: "stale" });
  const miss = memory(); setKvStoreForTests(miss.kv);
  assert.equal(await readStrict("feed"), null);
  assert.equal(primary.puts + stale.puts + miss.puts, 0);
  setKvStoreForTests(undefined);
});

test("publication retains previous and readers roll back to it", async () => {
  const mem = memory(); setKvStoreForTests(mem.kv);
  const meta = { generated_at: "2026-08-04T00:00:00Z", schema_version: "1", source_freshness: { ipo: "2026-08-04" }, engine_versions: { identity: "v3" } };
  const first = await publishVersionedSnapshot("ipo:index:v3", { rows: [{ isin: "INE000A01001" }] }, meta);
  await publishVersionedSnapshot("ipo:index:v3", { rows: [{ isin: "INE000A01002" }] }, { ...meta, generated_at: "2026-08-04T01:00:00Z" });
  mem.data.delete(JSON.parse(mem.data.get("ipo:index:v3:active")!).version_key);
  assert.deepEqual(await readVersionedSnapshot("ipo:index:v3"), { payload: '{"rows":[{"isin":"INE000A01001"}]}', source: "stale" });
  assert.ok(mem.data.has(first.version_key));
  setKvStoreForTests(undefined);
});
