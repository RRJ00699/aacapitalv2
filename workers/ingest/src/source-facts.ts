// workers/ingest/src/source-facts.ts — append-only provenance ledger.
// Idempotent: PK (ipo_id, field, source, fetched_at) prevents retry dupes.

import type { D1, RowChange } from "./db";

export interface FactContext {
  ipo_id: number;
  source: string;               // 'nse' | 'sebi' | 'sbi' | 'kite' | 'ipomatrix' | 'derived' | 'manual'
  doc_id?: string | null;       // documents.sha256 when supported by upstream doc
  confidence?: string | null;   // decimal string 0..1
  fetched_at: string;           // UTC ISO-8601 (SAME instant across a batch)
}

export function factStatements(
  db: D1,
  ctx: FactContext,
  changes: RowChange[],
): D1PreparedStatement[] {
  if (!changes || changes.length === 0) return [];
  const stmts: D1PreparedStatement[] = [];
  for (const c of changes) {
    stmts.push(
      db
        .prepare(
          `INSERT INTO source_facts (ipo_id, field, value, source, doc_id, confidence, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (ipo_id, field, source, fetched_at) DO NOTHING`,
        )
        .bind(ctx.ipo_id, c.field, c.next, ctx.source, ctx.doc_id ?? null, ctx.confidence ?? null, ctx.fetched_at),
    );
  }
  return stmts;
}
