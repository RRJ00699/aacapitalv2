import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest } from "next/server";
import { POST } from "../app/api/admin/snapshots/route";
import { GET as indexGET } from "../app/api/ipo/index/route";
import { __setTestKVForIntegration } from "./kv-cache";

class MemoryKV {
  values = new Map<string, string>();
  async get(k: string) { return this.values.get(k) ?? null; }
  async put(k: string, v: string) { this.values.set(k, v); }
}

test("builder payload -> publish endpoint -> KV -> user route -> x-cache HIT", async () => {
  const kv = new MemoryKV();
  __setTestKVForIntegration(kv);
  const oldKey = process.env.SNAPSHOT_PUBLISH_KEY;
  process.env.SNAPSHOT_PUBLISH_KEY = "test-key";
  try {
    const builderPayload = { rows: [{ company_name: "Route IPO", sym: "ROUTE", listing_date: "2026-08-04" }], generated_at: "2026-08-04T00:00:00Z" };
    const req = new NextRequest("https://aacapital.test/api/admin/snapshots", {
      method: "POST",
      headers: { "content-type": "application/json", "x-aac-key": "test-key" },
      body: JSON.stringify({ snapshots: [{ name: "ipo:index:v3", payload: builderPayload }] }),
    });
    const published = await POST(req);
    assert.equal(published.status, 200);
    assert.equal((await published.json()).ok, true);
    assert.ok(await kv.get("snapshot:ipo:index:v3:active"));

    const routeResponse = await indexGET();
    assert.equal(routeResponse.headers.get("x-cache"), "HIT");
    assert.deepEqual(await routeResponse.json(), builderPayload);
  } finally {
    if (oldKey === undefined) delete process.env.SNAPSHOT_PUBLISH_KEY;
    else process.env.SNAPSHOT_PUBLISH_KEY = oldKey;
    __setTestKVForIntegration(undefined);
  }
});
test("test KV mutator rejects production mutation", () => {
  const oldEnv = process.env.NODE_ENV;
  (process.env as Record<string, string | undefined>).NODE_ENV = "production";
  try {
    assert.throws(() => __setTestKVForIntegration(null), /disabled in production/);
  } finally {
    if (oldEnv === undefined) delete (process.env as Record<string, string | undefined>).NODE_ENV;
    else (process.env as Record<string, string | undefined>).NODE_ENV = oldEnv;
  }
});

test("UAT production server reads deterministic versioned snapshots without a Cloudflare binding", async () => {
  const oldFixture = process.env.UAT_SNAPSHOT_JSON;
  process.env.UAT_SNAPSHOT_JSON = `${process.cwd()}/uat/fixtures/snapshots.json`;
  __setTestKVForIntegration(undefined);
  try {
    const response = await indexGET();
    assert.equal(response.headers.get("x-cache"), "HIT");
    assert.equal((await response.json()).rows[0].sym, "UATGOOD");
  } finally {
    if (oldFixture === undefined) delete process.env.UAT_SNAPSHOT_JSON;
    else process.env.UAT_SNAPSHOT_JSON = oldFixture;
    __setTestKVForIntegration(undefined);
  }
});
