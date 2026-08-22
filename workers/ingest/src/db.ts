// workers/ingest/src/db.ts — thin D1 helpers.

export type D1 = D1Database;

export interface RowChange {
  field: string;
  prev: string | null;
  next: string | null;
}

export function nullify<T>(v: T | null | undefined): T | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  return v;
}

/**
 * Fill-empty-only writer. Only NULL cells are set from the patch. Returns
 * the changes for provenance and the exact D1 statements to run in a batch.
 */
export async function coalesceEmptyPatch(
  db: D1,
  table: string,
  pk: Record<string, string | number>,
  patch: Record<string, unknown>,
): Promise<{ changes: RowChange[]; statements: D1PreparedStatement[] }> {
  const pkKeys = Object.keys(pk);
  const pkWhere = pkKeys.map((k) => `${k} = ?`).join(" AND ");
  const pkValues = pkKeys.map((k) => pk[k]);
  const patchKeys = Object.keys(patch).filter((k) => patch[k] !== undefined);
  if (patchKeys.length === 0) return { changes: [], statements: [] };

  const existing = await db
    .prepare(`SELECT ${patchKeys.join(", ")} FROM ${table} WHERE ${pkWhere}`)
    .bind(...pkValues)
    .first<Record<string, unknown>>();

  const statements: D1PreparedStatement[] = [];
  const changes: RowChange[] = [];

  if (!existing) {
    // INSERT full patch (nulls allowed) plus PK.
    const cols = [...pkKeys, ...patchKeys];
    const vals: unknown[] = [...pkValues, ...patchKeys.map((k) => nullify(patch[k]))];
    statements.push(
      db.prepare(`INSERT INTO ${table} (${cols.join(", ")}) VALUES (${cols.map(() => "?").join(", ")})`).bind(...vals),
    );
    for (const k of patchKeys) {
      const v = nullify(patch[k]);
      if (v !== null && v !== undefined) {
        changes.push({ field: `${table}.${k}`, prev: null, next: String(v) });
      }
    }
    return { changes, statements };
  }

  const applied: Record<string, unknown> = {};
  for (const k of patchKeys) {
    const cur = existing[k] ?? null;
    const nxt = nullify(patch[k]);
    if (cur === null && nxt !== null && nxt !== undefined) {
      applied[k] = nxt;
      changes.push({ field: `${table}.${k}`, prev: null, next: String(nxt) });
    }
  }
  if (Object.keys(applied).length > 0) {
    const sets = Object.keys(applied).map((k) => `${k} = ?`).join(", ");
    statements.push(
      db.prepare(`UPDATE ${table} SET ${sets} WHERE ${pkWhere}`).bind(...Object.values(applied), ...pkValues),
    );
  }
  return { changes, statements };
}

/**
 * UPSERT writer (engine outputs). Overwrites every non-PK column in `row`.
 * Every non-null field is reported as a change for source_facts.
 */
export function upsertRow(
  db: D1,
  table: string,
  pkColumns: string[],
  row: Record<string, unknown>,
): { changes: RowChange[]; statements: D1PreparedStatement[] } {
  const cols = Object.keys(row);
  const vals = cols.map((c) => nullify(row[c]));
  const nonPk = cols.filter((c) => !pkColumns.includes(c));
  const excluded = nonPk.map((c) => `${c} = excluded.${c}`).join(", ");
  const sql =
    `INSERT INTO ${table} (${cols.join(", ")}) VALUES (${cols.map(() => "?").join(", ")}) ` +
    `ON CONFLICT (${pkColumns.join(", ")}) DO UPDATE SET ${excluded}`;
  const changes: RowChange[] = cols.map((c) => ({
    field: `${table}.${c}`,
    prev: null,
    next: row[c] === null || row[c] === undefined ? null : String(row[c]),
  }));
  return { changes, statements: [db.prepare(sql).bind(...vals)] };
}
