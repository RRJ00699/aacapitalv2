// workers/ingest/src/source-facts.ts — append-only provenance ledger.
// Idempotency: UNIQUE (ipo_id, field, observation_hash), where
//   observation_hash = sha256(field | value | source | document_sha | pipeline_version)
// This is stable across retries with the same values, unlike a
// timestamp-based PK.

import type { D1, RowChange } from "./db";

export interface FactContext {
  ipo_id: number;
  source: string;                 // 'nse' | 'sebi' | 'sbi' | 'kite' | 'ipomatrix' | 'derived' | 'manual'
  document_sha?: string | null;   // documents.sha256 when supported by upstream doc
  confidence?: string | null;     // decimal string 0..1
  pipeline_version?: string | null;
  fetched_at: string;             // UTC ISO-8601 (same instant across a batch)
}

async function sha256Hex(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest("SHA-256", bytes);
  const arr = new Uint8Array(buf);
  let hex = "";
  for (let i = 0; i < arr.length; i++) hex += arr[i].toString(16).padStart(2, "0");
  return hex;
}

export async function observationHash(
  field: string,
  value: string | null,
  source: string,
  document_sha: string | null | undefined,
  pipeline_version: string | null | undefined,
): Promise<string> {
  return sha256Hex([field, value ?? "", source, document_sha ?? "", pipeline_version ?? ""].join("|"));
}

export async function factStatements(
  db: D1,
  ctx: FactContext,
  changes: RowChange[],
): Promise<D1PreparedStatement[]> {
  if (!changes || changes.length === 0) return [];
  const stmts: D1PreparedStatement[] = [];
  for (const c of changes) {
    const hash = await observationHash(c.field, c.next, ctx.source, ctx.document_sha, ctx.pipeline_version);
    stmts.push(
      db
        .prepare(
          `INSERT INTO source_facts
             (ipo_id, field, value, source, document_sha, confidence,
              pipeline_version, observation_hash, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (ipo_id, field, observation_hash) DO NOTHING`,
        )
        .bind(
          ctx.ipo_id,
          c.field,
          c.next,
          ctx.source,
          ctx.document_sha ?? null,
          ctx.confidence ?? null,
          ctx.pipeline_version ?? null,
          hash,
          ctx.fetched_at,
        ),
    );
  }
  return stmts;
}
