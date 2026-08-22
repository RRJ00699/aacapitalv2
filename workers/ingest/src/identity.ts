// workers/ingest/src/identity.ts
// Locked identity rules (product contract §6):
//   1. ISIN exact match — always wins.
//   2. name_norm exact match — fallback.
//   3. symbol / nse_symbol / bse_code MUST NOT be used for identity.
// Returns the INTEGER surrogate `ipo.id` (matches Neon BIGINT domain).

import type { D1 } from "./db";

const LEGAL_SUFFIXES = [
  "LIMITED", "LTD", "LTD.", "PRIVATE", "PVT", "PVT.",
  "INDIA", "INDIA LTD", "INDIA LIMITED", "CORPORATION", "CORP",
  "INCORPORATED", "INC", "COMPANY", "CO", "CO.", "HOLDINGS",
  "INTERNATIONAL", "INTL", "INDUSTRIES", "ENTERPRISES", "GROUP",
];

export function normaliseName(raw: string): string {
  const upper = raw.toUpperCase().normalize("NFKD");
  const noPunct = upper.replace(/[^\p{L}\p{N}\s]/gu, " ");
  const tokens = noPunct.split(/\s+/).filter(Boolean);
  while (tokens.length > 1 && LEGAL_SUFFIXES.includes(tokens[tokens.length - 1])) {
    tokens.pop();
  }
  return tokens.join(" ");
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
  bse_code?: string | null;
}

export interface Resolution {
  ipo_id: number;                       // INTEGER surrogate (Neon BIGINT domain)
  created: boolean;
  matched_by: "isin" | "name_norm" | "created";
}

/**
 * Resolve or create an ipo row and return its INTEGER id. Never uses
 * symbol. Never merges rows. If ISIN and name_norm point to different rows,
 * the caller sees a conflict via UNIQUE index and returns HTTP 409.
 */
export async function resolveIpoIdentity(db: D1, input: IpoIdentityInput): Promise<Resolution> {
  const isin = (input.isin ?? "").trim() || null;
  const name_norm = normaliseName(input.name_display);

  if (isin) {
    const byIsin = await db.prepare("SELECT id FROM ipo WHERE isin = ?").bind(isin).first<{ id: number }>();
    if (byIsin) return { ipo_id: byIsin.id, created: false, matched_by: "isin" };
  }

  const byName = await db
    .prepare("SELECT id, isin FROM ipo WHERE name_norm = ?")
    .bind(name_norm)
    .first<{ id: number; isin: string | null }>();

  if (byName) {
    // If we found by name and have a NEW ISIN, refuse silent rebinding —
    // let the caller surface the anomaly to the operator.
    if (isin && byName.isin && byName.isin !== isin) {
      throw new IdentityConflictError(
        `name_norm '${name_norm}' already bound to ISIN ${byName.isin}, incoming ${isin}`
      );
    }
    // Fill an ISIN if it wasn't known.
    if (isin && !byName.isin) {
      await db.prepare("UPDATE ipo SET isin = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?").bind(isin, byName.id).run();
    }
    return { ipo_id: byName.id, created: false, matched_by: "name_norm" };
  }

  // Create a new row. Rely on the UNIQUE index on name_norm to reject a
  // racy duplicate; caller retries the resolve step in that case.
  const res = await db
    .prepare(
      `INSERT INTO ipo
         (isin, symbol, name_norm, name_display, sector, industry, is_mainboard,
          status, listing_date, kite_token, bse_code)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      isin,
      input.symbol ?? null,
      name_norm,
      input.name_display,
      input.sector ?? null,
      input.industry ?? null,
      input.is_mainboard === undefined || input.is_mainboard === null ? null : (input.is_mainboard ? 1 : 0),
      input.status ?? null,
      input.listing_date ?? null,
      input.kite_token ?? null,
      input.bse_code ?? null,
    )
    .run();
  const newId = res.meta?.last_row_id;
  if (typeof newId !== "number") throw new Error("ipo insert did not return last_row_id");
  return { ipo_id: newId, created: true, matched_by: "created" };
}

export class IdentityConflictError extends Error {
  constructor(msg: string) {
    super(msg);
    this.name = "IdentityConflictError";
  }
}
