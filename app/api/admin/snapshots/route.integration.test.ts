import assert from "node:assert/strict";
import { execFile, spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const root = resolve(import.meta.dirname, "../../../..");

async function availablePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") return reject(new Error("could not allocate test port"));
      server.close((error) => error ? reject(error) : resolvePort(address.port));
    });
  });
}

async function waitForWorker(origin: string, worker: ChildProcess, logs: () => string): Promise<void> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (worker.exitCode !== null) throw new Error(`local Worker exited before readiness\n${logs()}`);
    try {
      const response = await fetch(`${origin}/api/admin/snapshots`);
      if (response.status === 401) return;
    } catch { /* Worker is still starting. */ }
    await new Promise(resolveWait => setTimeout(resolveWait, 250));
  }
  throw new Error(`local Worker did not become ready\n${logs()}`);
}

test("fixture builder publishes versioned snapshots through the real local Worker and KV", { timeout: 120_000 }, async () => {
  assert.ok(existsSync(join(root, ".open-next/worker.js")), "run the OpenNext build before this integration test");

  const persistPath = await mkdtemp(join(tmpdir(), "snapshot-publication-kv-"));
  const port = await availablePort();
  const origin = `http://127.0.0.1:${port}`;
  const publishKey = "local-integration-publish-key";
  let workerOutput = "";
  const worker = spawn(
    process.execPath,
    [join(root, "node_modules/wrangler/bin/wrangler.js"), "dev", "--local", "--port", String(port), "--persist-to", persistPath,
      "--var", `SNAPSHOT_PUBLISH_KEY:${publishKey}`, "--log-level", "error"],
    { cwd: root, detached: process.platform !== "win32", env: { ...process.env, DATABASE_URL: "", NEON_DATABASE_URL: "" }, stdio: ["ignore", "pipe", "pipe"] },
  );
  worker.stdout?.on("data", chunk => { workerOutput += String(chunk); });
  worker.stderr?.on("data", chunk => { workerOutput += String(chunk); });

  try {
    await waitForWorker(origin, worker, () => workerOutput);
    const { stdout, stderr } = await execFileAsync(
      process.execPath,
      ["--import", "tsx", "pipeline/build/build_snapshots.ts", "--limit=1", "--concurrency=1"],
      {
        cwd: root,
        env: {
          ...process.env,
          DATABASE_URL: "",
          NEON_DATABASE_URL: "",
          SNAPSHOT_TEST_FIXTURE: "1",
          SNAPSHOT_PUBLISH_URL: origin,
          SNAPSHOT_PUBLISH_KEY: publishKey,
        },
      },
    );
    assert.equal(stderr, "");
    assert.match(stdout, /"snapshot_fixture_sql_verified":true/);

    const successes = stdout.trim().split("\n").map(line => {
      try { return JSON.parse(line) as Record<string, unknown>; } catch { return {}; }
    }).filter(value => value.ok === true);
    assert.ok(successes.length, `builder did not print the publication success response:\n${stdout}`);
    const published = Object.assign({}, ...successes.map(success => success.published as Record<string,string>));
    assert.ok(published["ipo-command:v6"]);
    assert.ok(published["ipo-details:isin:INE000000001:v1"]);

    const detailsResponse = await fetch(`${origin}/api/ipo/details/INE000000001`);
    assert.equal(detailsResponse.status, 200, "Details consumer must read the builder-published local KV snapshot");
    assert.equal(detailsResponse.headers.get("x-cache"), "HIT");
    const detailsPayload = await detailsResponse.json() as { schema_version?: string; verified_evidence?: unknown[] };
    assert.equal(detailsPayload.schema_version, "ipo-details-v1");
    assert.equal(detailsPayload.verified_evidence?.length, 1);

    const readKV = async (key: string) => (await execFileAsync(
      process.platform === "win32" ? "npx.cmd" : "npx",
      ["wrangler", "kv", "key", "get", key, "--binding", "CACHE", "--local", "--persist-to", persistPath, "--text"],
      { cwd: root },
    )).stdout.trim();

    const activeVersion = await readKV("snapshot:ipo-command:v6:active");
    assert.equal(activeVersion, published["ipo-command:v6"], "active pointer must contain the returned version");
    const immutablePayload = await readKV(`snapshot:ipo-command:v6:data:${activeVersion}`);
    const parsedPayload = JSON.parse(immutablePayload) as { cards?: unknown[] };
    assert.ok(Array.isArray(parsedPayload.cards), "immutable KV value must be the actual builder snapshot");

    console.log(JSON.stringify({
      snapshot_fixture_sql_verified: true,
      http_post_status: 200,
      worker: ".open-next/worker.js",
      kv_immutable_key_verified: true,
      kv_active_pointer_verified: true,
      published_snapshots: Object.keys(published).length,
    }));
  } finally {
    if (worker.pid && process.platform !== "win32") process.kill(-worker.pid, "SIGTERM");
    else worker.kill("SIGTERM");
    await new Promise<void>(resolveExit => {
      if (worker.exitCode !== null) return resolveExit();
      worker.once("exit", () => resolveExit());
      setTimeout(() => {
        if (worker.pid && process.platform !== "win32") {
          try { process.kill(-worker.pid, "SIGKILL"); } catch { /* Process group already stopped. */ }
        } else worker.kill("SIGKILL");
        resolveExit();
      }, 5_000).unref();
    });
    await rm(persistPath, { recursive: true, force: true });
  }
});
