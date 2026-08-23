// workers/ingest/src/identity.ts
// Locked identity rules (product contract §6):
//   1. ISIN exact match — always wins.
//   2. name_norm exact match — fallback.
//   3. symbol / nse_symbol / bse_code MUST NOT be used for identity.
// Returns the INTEGER surrogate `ipo.id`.
//
// `normaliseName` is a character-for-character port of the canonical Python
// normaliser in `pipeline/fill_ipo.py:_norm`:
//   1. lowercase the input
//   2. replace every char that is not [a-z0-9 ] with a space
//   3. collapse runs of whitespace to a single space and strip
// This must stay in lockstep with the Python implementation. Keep the tests
// in `workers/ingest/tests/identity.spec.ts` (added under Stage-B testing PR)
// pinned to identical fixtures.

import type { D1 } from "./db";

export function normaliseName(raw: string): string {
  if (raw == null) return "";
  const lower = String(raw).toLowerCase();
  const alnum = lower.replace(/[^a-z0-9 ]+/g, " ");
  return alnum.replace(/\s+/g, " ").trim();
}

export interface IpoIdentityInput {
  isin?: string | null;
  name_display: string;
  symbol?: string | null;
  sector?: string | null;
  industry?: string | null;
  is_mainboard?: boolean | 0 | 1 | null;
  status?: string | null;
  listing_date?: string | null;
  kite_token?: number | null;
  ipomatrix_id?: string | null;
  bse_code?: string | null;
}

export interface Resolution {
  ipo_id: number;
  created: boolean;
  matched_by: "isin" | "name_norm" | "created";
}

export class IdentityConflictError extends Error {
  constructor(msg: string) {
    super(msg);
    this.name = "IdentityConflictError";
  }
}

/**
 * Resolve or create an ipo row and return its INTEGER id. Never uses
 * symbol. Never merges rows. If ISIN and name_norm point to different rows,
 * the caller sees a conflict via UNIQUE index and returns HTTP 409.
 */
export async function resolveIpoIdentity(db: D1, input: IpoIdentityInput): Promise<Resolution> {
  const isin = (input.isin ?? "").trim() || null;
  const name_norm = normaliseName(input.name_display);
  if (!name_norm) throw new IdentityConflictError("name_display normalised to empty");

  if (isin) {
    const byIsin = await db.prepare("SELECT id FROM ipo WHERE isin = ?").bind(isin).first<{ id: number }>();
    if (byIsin) return { ipo_id: byIsin.id, created: false, matched_by: "isin" };
  }

  const byName = await db
    .prepare("SELECT id, isin FROM ipo WHERE name_norm = ?")
    .bind(name_norm)
    .first<{ id: number; isin: string | null }>();

  if (byName) {
    if (isin && byName.isin && byName.isin !== isin) {
      throw new IdentityConflictError(
        `name_norm '${name_norm}' already bound to ISIN ${byName.isin}, incoming ${isin}`,
      );
    }
    if (isin && !byName.isin) {
      await db
        .prepare("UPDATE ipo SET isin = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?")
        .bind(isin, byName.id)
        .run();
    }
    return { ipo_id: byName.id, created: false, matched_by: "name_norm" };
  }

  const res = await db
    .prepare(
      `INSERT INTO ipo
         (isin, symbol, name_norm, name_display, sector, industry, is_mainboard,
          status, listing_date, kite_token, ipomatrix_id, bse_code)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      isin,
      input.symbol ?? null,
      name_norm,
      input.name_display,
      input.sector ?? null,
      input.industry ?? null,
      input.is_mainboard === undefined || input.is_mainboard === null
        ? null
        : input.is_mainboard
          ? 1
          : 0,
      input.status ?? null,
      input.listing_date ?? null,
      input.kite_token ?? null,
      input.ipomatrix_id ?? null,
      input.bse_code ?? null,
    )
    .run();
  const newId = res.meta?.last_row_id;
  if (typeof newId !== "number") throw new Error("ipo insert did not return last_row_id");
  return { ipo_id: newId, created: true, matched_by: "created" };
}
