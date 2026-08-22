// workers/ingest/src/schemas.ts — per-table row validators.
// Column names match Neon exactly (see pipeline/conftest.py V2_DDL).
// Numeric fields are validated as decimal strings and preserved as-is.

export type IngestMode = "coalesce_empty" | "upsert";

export interface ValidationError {
  row_index: number;
  field?: string;
  message: string;
}

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;

function toDecimal(v: unknown, field: string, row: number, errs: ValidationError[]): string | null {
  if (v === null || v === undefined || v === "") return null;
  const s = String(v).trim();
  if (!DECIMAL_RE.test(s)) {
    errs.push({ row_index: row, field, message: `not a decimal string: ${s}` });
    return null;
  }
  // Preserve caller's precision. Do NOT reformat — reconciliation must be
  // able to compare against the Neon NUMERIC textual representation.
  return s;
}

function toIsoUtc(v: unknown, field: string, row: number, errs: ValidationError[]): string | null {
  if (v === null || v === undefined || v === "") return null;
  const dt = new Date(String(v).trim());
  if (Number.isNaN(dt.getTime())) {
    errs.push({ row_index: row, field, message: `invalid timestamp: ${v}` });
    return null;
  }
  return dt.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function toDateIst(v: unknown, field: string, row: number, errs: ValidationError[]): string | null {
  if (v === null || v === undefined || v === "") return null;
  const s = String(v).trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    errs.push({ row_index: row, field, message: `IST date must be YYYY-MM-DD: ${v}` });
    return null;
  }
  return s;
}

function toInt(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function toBool01(v: unknown): 0 | 1 | null {
  if (v === null || v === undefined || v === "") return null;
  return v === true || v === 1 || v === "1" || v === "true" ? 1 : 0;
}

function req(v: unknown, field: string, row: number, errs: ValidationError[]): string | null {
  if (v === null || v === undefined || String(v).trim() === "") {
    errs.push({ row_index: row, field, message: "required" });
    return null;
  }
  return String(v).trim();
}

export interface Validated<T extends Record<string, unknown>> {
  row: T;
  identity?: {
    isin?: string | null;
    name_display: string;
    symbol?: string | null;
    sector?: string | null;
    industry?: string | null;
    is_mainboard?: 0 | 1 | null;
    status?: string | null;
    listing_date?: string | null;
    kite_token?: number | null;
    bse_code?: string | null;
  };
}

type Validator<T extends Record<string, unknown>> = (raw: any, i: number, errs: ValidationError[]) => Validated<T> | null;

// ---- ipo_issue ----
export const validateIpoIssue: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const name_display = req(raw.name_display ?? raw.company_name, "name_display", i, errs);
  if (!name_display) return null;
  return {
    identity: {
      isin: raw.isin ?? null,
      name_display,
      symbol: raw.symbol ?? raw.nse_symbol ?? null,
      sector: raw.sector ?? null,
      industry: raw.industry ?? null,
      is_mainboard: raw.is_mainboard === undefined ? null : toBool01(raw.is_mainboard),
      status: raw.status ?? null,
      listing_date: toDateIst(raw.listing_date, "listing_date", i, errs),
      kite_token: toInt(raw.kite_token),
      bse_code: raw.bse_code ?? null,
    },
    row: {
      open_date: toDateIst(raw.open_date, "open_date", i, errs),
      close_date: toDateIst(raw.close_date, "close_date", i, errs),
      allotment_date: toDateIst(raw.allotment_date, "allotment_date", i, errs),
      band_lo: toDecimal(raw.band_lo, "band_lo", i, errs),
      band_hi: toDecimal(raw.band_hi, "band_hi", i, errs),
      issue_price: toDecimal(raw.issue_price, "issue_price", i, errs),
      lot_size: toInt(raw.lot_size),
      face_value: toDecimal(raw.face_value, "face_value", i, errs),
      fresh_cr: toDecimal(raw.fresh_cr, "fresh_cr", i, errs),
      ofs_cr: toDecimal(raw.ofs_cr, "ofs_cr", i, errs),
      issue_size_cr: toDecimal(raw.issue_size_cr, "issue_size_cr", i, errs),
      registrar: raw.registrar ?? null,
      brlm_count: toInt(raw.brlm_count),
    },
  };
};

// ---- subscription_snapshots ----
export const validateSubscriptionSnapshot: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const name_display = req(raw.name_display ?? raw.company_name, "name_display", i, errs);
  const captured_at = toIsoUtc(raw.captured_at, "captured_at", i, errs);
  if (!name_display || !captured_at) return null;
  return {
    identity: { isin: raw.isin ?? null, name_display },
    row: {
      captured_at,
      is_final: toBool01(raw.is_final),
      qib_x: toDecimal(raw.qib_x, "qib_x", i, errs),
      nii_x: toDecimal(raw.nii_x, "nii_x", i, errs),
      bnii_x: toDecimal(raw.bnii_x, "bnii_x", i, errs),
      snii_x: toDecimal(raw.snii_x, "snii_x", i, errs),
      retail_x: toDecimal(raw.retail_x, "retail_x", i, errs),
      total_x: toDecimal(raw.total_x, "total_x", i, errs),
      anchor_amount_cr: toDecimal(raw.anchor_amount_cr, "anchor_amount_cr", i, errs),
      anchor_count: toInt(raw.anchor_count),
      applications_lakh: toDecimal(raw.applications_lakh, "applications_lakh", i, errs),
      mf_shares_bid: toDecimal(raw.mf_shares_bid, "mf_shares_bid", i, errs),
      mf_pct_qib: toDecimal(raw.mf_pct_qib, "mf_pct_qib", i, errs),
    },
  };
};

// ---- financial_statements ----
export const validateFinancialStatement: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const name_display = req(raw.name_display ?? raw.company_name, "name_display", i, errs);
  const period = req(raw.period, "period", i, errs);
  const basis = req(raw.basis, "basis", i, errs);
  if (!name_display || !period || !basis) return null;
  return {
    identity: { isin: raw.isin ?? null, name_display },
    row: {
      period, basis,
      revenue: toDecimal(raw.revenue, "revenue", i, errs),
      total_income: toDecimal(raw.total_income, "total_income", i, errs),
      ebitda: toDecimal(raw.ebitda, "ebitda", i, errs),
      pat: toDecimal(raw.pat, "pat", i, errs),
      net_worth: toDecimal(raw.net_worth, "net_worth", i, errs),
      total_debt: toDecimal(raw.total_debt, "total_debt", i, errs),
      total_assets: toDecimal(raw.total_assets, "total_assets", i, errs),
      source: raw.source ?? null,
      fetched_at: toIsoUtc(raw.fetched_at ?? new Date().toISOString(), "fetched_at", i, errs),
    },
  };
};

// ---- valuation (engine output) ----
export const validateValuation: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const name_display = req(raw.name_display ?? raw.company_name, "name_display", i, errs);
  if (!name_display) return null;
  return {
    identity: { isin: raw.isin ?? null, name_display },
    row: {
      computed_at: toIsoUtc(raw.computed_at ?? new Date().toISOString(), "computed_at", i, errs),
      engine_version: raw.engine_version ?? null,
      pe: toDecimal(raw.pe, "pe", i, errs),
      pb: toDecimal(raw.pb, "pb", i, errs),
      roe: toDecimal(raw.roe, "roe", i, errs),
      roce: toDecimal(raw.roce, "roce", i, errs),
      de: toDecimal(raw.de, "de", i, errs),
      rev_cagr_3y: toDecimal(raw.rev_cagr_3y, "rev_cagr_3y", i, errs),
      ofs_pct: toDecimal(raw.ofs_pct, "ofs_pct", i, errs),
      peer_median_pe: toDecimal(raw.peer_median_pe, "peer_median_pe", i, errs),
      score: toDecimal(raw.score, "score", i, errs),
      score_band: raw.score_band ?? null,
      inputs_used: raw.inputs_used ? JSON.stringify(raw.inputs_used) : null,
      missing_inputs: raw.missing_inputs ? JSON.stringify(raw.missing_inputs) : null,
    },
  };
};

// ---- decisions (verdict engine output) ----
export const validateDecision: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const name_display = req(raw.name_display ?? raw.company_name, "name_display", i, errs);
  const fv = req(raw.fundamental_verdict, "fundamental_verdict", i, errs);
  const la = raw.listing_action == null ? null : String(raw.listing_action).trim();
  if (!name_display || !fv) return null;
  if (fv === "WEAK" && la && la.toUpperCase().startsWith("BUY")) {
    errs.push({
      row_index: i, field: "listing_action",
      message: "WEAK fundamentals cannot pair with a BUY listing_action (product contract §6)",
    });
    return null;
  }
  return {
    identity: { isin: raw.isin ?? null, name_display },
    row: {
      decided_at: toIsoUtc(raw.decided_at ?? new Date().toISOString(), "decided_at", i, errs),
      engine_version: raw.engine_version ?? null,
      fundamental_verdict: fv,
      listing_action: la,
      reasons: raw.reasons ? JSON.stringify(raw.reasons) : null,
      evidence_refs: raw.evidence_refs ? JSON.stringify(raw.evidence_refs) : null,
    },
  };
};

export const VALIDATORS: Record<string, Validator<Record<string, unknown>>> = {
  ipo_issue: validateIpoIssue,
  subscription_snapshots: validateSubscriptionSnapshot,
  financial_statements: validateFinancialStatement,
  valuation: validateValuation,
  decisions: validateDecision,
};

export const PK_COLUMNS: Record<string, string[]> = {
  ipo_issue: ["ipo_id"],
  subscription_snapshots: ["ipo_id", "captured_at"],
  financial_statements: ["ipo_id", "period", "basis"],
  valuation: ["id"],               // AUTOINCREMENT; upsert not by ipo_id
  decisions: ["id"],
};

export const ALLOWED_MODES: Record<string, IngestMode[]> = {
  ipo_issue: ["coalesce_empty", "upsert"],
  subscription_snapshots: ["upsert"],
  financial_statements: ["coalesce_empty", "upsert"],
  valuation: ["upsert"],
  decisions: ["upsert"],
};
