// workers/ingest/src/index.ts — the ingest Worker for the 5-table D1 schema.
// Public app never binds this. Only pipeline/cron.py (Stage D) calls it.

import { VALIDATORS, PK_COLUMNS, ALLOWED_MODES, type IngestMode } from "./schemas";
import { resolveIpoIdentity, IdentityConflictError } from "./identity";
import { coalesceEmptyPatch, upsertRow, appendRow, type D1, type RowChange } from "./db";
import { factStatements } from "./source-facts";

export interface Env {
  DB_CORE: D1;
  INGEST_KEY: string;
  NTFY_TOPIC?: string;
  MAX_ROWS_PER_REQUEST?: string;
  AAC_ENV?: string;
}

function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers || {}) },
  });
}

async function alertNtfy(topic: string | undefined, title: string, msg: string) {
  if (!topic) return;
  try {
    await fetch(`https://ntfy.sh/${topic}`, {
      method: "POST",
      headers: { Title: title, Priority: "high" },
      body: msg,
    });
  } catch { /* never fail ingest on ntfy hiccup */ }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      const meta = await env.DB_CORE.prepare(
        "SELECT count(*) AS n, max(applied_at) AS latest FROM d1_migrations",
      ).first<{ n: number; latest: string }>();
      return json({
        ok: true,
        service: "aacapital-ingest",
        env: env.AAC_ENV ?? "unknown",
        schema_target: "d1-5table",
        migrations_applied: meta?.n ?? 0,
        latest_migration_at: meta?.latest ?? null,
      });
    }

    if (request.method !== "POST") return json({ error: "method_not_allowed" }, { status: 405 });
    if (!url.pathname.startsWith("/ingest/")) return json({ error: "not_found" }, { status: 404 });

    // Constant-time auth check.
    const provided = request.headers.get("x-aac-ingest-key") ?? "";
    if (!env.INGEST_KEY || provided.length !== env.INGEST_KEY.length) {
      return json({ error: "unauthorized" }, { status: 401 });
    }
    let mismatch = 0;
    for (let i = 0; i < provided.length; i++) mismatch |= provided.charCodeAt(i) ^ env.INGEST_KEY.charCodeAt(i);
    if (mismatch !== 0) return json({ error: "unauthorized" }, { status: 401 });

    const table = url.pathname.slice("/ingest/".length);
    const validator = VALIDATORS[table];
    const pkCols = PK_COLUMNS[table];
    const allowed = ALLOWED_MODES[table];
    if (!validator || !pkCols || !allowed) return json({ error: "unknown_table", table }, { status: 400 });

    let body: any;
    try { body = await request.json(); } catch { return json({ error: "invalid_json" }, { status: 400 }); }

    const mode: IngestMode = body?.mode;
    const source = String(body?.source ?? "").trim();
    const pipelineVersion = body?.pipeline_version == null ? null : String(body.pipeline_version).trim();
    const observedAt = String(body?.observed_at ?? new Date().toISOString().replace(/\.\d{3}Z$/, "Z")).trim();
    const rows: any[] = Array.isArray(body?.rows) ? body.rows : [];
    const maxRows = Number(env.MAX_ROWS_PER_REQUEST ?? "5000");

    if (!allowed.includes(mode)) return json({ error: "mode_not_allowed_for_table", table, mode, allowed }, { status: 400 });
    if (!source) return json({ error: "source_required" }, { status: 400 });
    if (rows.length === 0) return json({ error: "no_rows" }, { status: 400 });
    if (rows.length > maxRows) return json({ error: "too_many_rows", limit: maxRows, got: rows.length }, { status: 413 });

    const errors: any[] = [];
    const statements: D1PreparedStatement[] = [];
    let inserted = 0, updated = 0, unchanged = 0, factsAppended = 0;

    for (let i = 0; i < rows.length; i++) {
      const raw = rows[i];
      const validated = validator(raw, i, errors);
      if (!validated) continue;

      let ipoId: number;
      try {
        const resolution = await resolveIpoIdentity(
          env.DB_CORE,
          validated.identity ?? { name_display: String(raw.name_display ?? raw.company_name) },
        );
        ipoId = resolution.ipo_id;
        if (resolution.created) inserted++;
      } catch (e) {
        if (e instanceof IdentityConflictError) {
          errors.push({ row_index: i, message: e.message });
          continue;
        }
        throw e;
      }

      // `ipo` table has NO per-row payload beyond identity itself; nothing else to write.
      if (table === "ipo") continue;

      const rowWithId: Record<string, unknown> = { ...validated.row, ipo_id: ipoId };
      let changes: RowChange[] = [];

      if (mode === "coalesce_empty") {
        const pk: Record<string, string | number> = {};
        for (const k of pkCols) pk[k] = rowWithId[k] as string | number;
        const patch: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(rowWithId)) if (!pkCols.includes(k)) patch[k] = v;
        const res = await coalesceEmptyPatch(env.DB_CORE, table, pk, patch);
        changes = res.changes;
        statements.push(...res.statements);
        if (res.statements.length === 0) unchanged++;
        else updated++;
      } else if (mode === "append") {
        // For AUTOINCREMENT PK tables the composite PK is not present in the row;
        // fall back to plain INSERT.
        if (pkCols.length === 1 && pkCols[0] === "id") {
          const cols = Object.keys(rowWithId).filter((k) => k !== "id");
          statements.push(
            env.DB_CORE
              .prepare(`INSERT INTO ${table} (${cols.join(", ")}) VALUES (${cols.map(() => "?").join(", ")})`)
              .bind(...cols.map((c) => rowWithId[c])),
          );
          changes = cols.map((c) => ({
            field: `${table}.${c}`,
            prev: null,
            next: rowWithId[c] === null || rowWithId[c] === undefined ? null : String(rowWithId[c]),
          }));
        } else {
          const res = appendRow(env.DB_CORE, table, pkCols, rowWithId);
          changes = res.changes;
          statements.push(...res.statements);
        }
        updated++;
      } else {
        // upsert
        if (pkCols.length === 1 && pkCols[0] === "id") {
          const cols = Object.keys(rowWithId).filter((k) => k !== "id");
          statements.push(
            env.DB_CORE
              .prepare(`INSERT INTO ${table} (${cols.join(", ")}) VALUES (${cols.map(() => "?").join(", ")})`)
              .bind(...cols.map((c) => rowWithId[c])),
          );
          changes = cols.map((c) => ({
            field: `${table}.${c}`,
            prev: null,
            next: rowWithId[c] === null || rowWithId[c] === undefined ? null : String(rowWithId[c]),
          }));
        } else {
          const res = upsertRow(env.DB_CORE, table, pkCols, rowWithId);
          changes = res.changes;
          statements.push(...res.statements);
        }
        updated++;
      }

      const fs = await factStatements(
        env.DB_CORE,
        {
          ipo_id: ipoId,
          source,
          document_sha: raw.document_sha ?? raw.doc_id ?? null,
          confidence: raw.confidence ?? null,
          pipeline_version: pipelineVersion,
          fetched_at: observedAt,
        },
        changes,
      );
      statements.push(...fs);
      factsAppended += fs.length;
    }

    if (statements.length === 0) {
      return json({ ok: errors.length === 0, inserted, updated, unchanged, facts_appended: factsAppended, errors });
    }

    try {
      await env.DB_CORE.batch(statements);
    } catch (e: any) {
      await alertNtfy(env.NTFY_TOPIC, "AACapital ingest FAILED", `table=${table} err=${e?.message}`);
      return json({ error: "d1_batch_failed", message: String(e?.message ?? e) }, { status: 500 });
    }

    return json({ ok: errors.length === 0, inserted, updated, unchanged, facts_appended: factsAppended, errors });
  },
} satisfies ExportedHandler<Env>;
