// workers/ingest/src/schemas.ts — per-table row validators for the 5-table
// target D1 schema (see d1/migrations/0001_ipo.sql .. 0005_source_facts.sql).
//
// Validators return `{ identity, row }`. `identity` is used by the ingest
// Worker to resolve `ipo.id` via `resolveIpoIdentity`; `row` is the
// per-table payload with primitive values ready for D1.

export type IngestMode = "coalesce_empty" | "upsert" | "append";

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

function jsonOrNull(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") {
    // Assume caller has already stringified; validate parseable.
    try { JSON.parse(v); return v; } catch { return null; }
  }
  try { return JSON.stringify(v); } catch { return null; }
}

export interface Identity {
  isin?: string | null;
  name_display: string;
  symbol?: string | null;
  sector?: string | null;
  industry?: string | null;
  is_mainboard?: 0 | 1 | null;
  status?: string | null;
  listing_date?: string | null;
  kite_token?: number | null;
  ipomatrix_id?: string | null;
  bse_code?: string | null;
}

export interface Validated<T extends Record<string, unknown>> {
  identity?: Identity;
  row: T;
}

type Validator<T extends Record<string, unknown>> = (
  raw: any, i: number, errs: ValidationError[]
) => Validated<T> | null;

function commonIdentity(raw: any, i: number, errs: ValidationError[]): Identity | null {
  const name_display = req(raw.name_display ?? raw.company_name, "name_display", i, errs);
  if (!name_display) return null;
  return {
    isin: raw.isin ?? null,
    name_display,
    symbol: raw.symbol ?? raw.nse_symbol ?? null,
    sector: raw.sector ?? null,
    industry: raw.industry ?? null,
    is_mainboard: raw.is_mainboard === undefined ? null : toBool01(raw.is_mainboard),
    status: raw.status ?? null,
    listing_date: raw.listing_date ? toDateIst(raw.listing_date, "listing_date", i, errs) : null,
    kite_token: toInt(raw.kite_token),
    ipomatrix_id: raw.ipomatrix_id ?? null,
    bse_code: raw.bse_code ?? null,
  };
}

// ---------------------------------------------------------------- ipo
// Pure identity write. The row is empty because everything lives in the
// `ipo` table already via `resolveIpoIdentity`.
export const validateIpo: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const identity = commonIdentity(raw, i, errs);
  if (!identity) return null;
  return { identity, row: {} };
};

// ---------------------------------------------------------------- fundamentals
export const validateFundamentals: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const identity = commonIdentity(raw, i, errs);
  if (!identity) return null;

  // Cross-field guardrails on price band (product contract).
  const band_lo = toDecimal(raw.band_lo, "band_lo", i, errs);
  const band_hi = toDecimal(raw.band_hi, "band_hi", i, errs);
  const issue_price = toDecimal(raw.issue_price, "issue_price", i, errs);
  if (band_lo && band_hi && parseFloat(band_lo) > parseFloat(band_hi)) {
    errs.push({ row_index: i, field: "band_lo", message: "band_lo > band_hi" });
    return null;
  }
  if (issue_price && band_lo && parseFloat(issue_price) < parseFloat(band_lo)) {
    errs.push({ row_index: i, field: "issue_price", message: "issue_price below band_lo" });
    return null;
  }
  if (issue_price && band_hi && parseFloat(issue_price) > parseFloat(band_hi)) {
    errs.push({ row_index: i, field: "issue_price", message: "issue_price above band_hi" });
    return null;
  }

  const fv = raw.fundamental_verdict == null ? null : String(raw.fundamental_verdict).trim();
  const la = raw.listing_action == null ? null : String(raw.listing_action).trim();
  if (fv && la && fv.toUpperCase() === "WEAK" && la.toUpperCase().startsWith("BUY")) {
    errs.push({
      row_index: i,
      field: "listing_action",
      message: "WEAK fundamentals cannot pair with a BUY listing_action (product contract §6)",
    });
    return null;
  }

  return {
    identity,
    row: {
      open_date: toDateIst(raw.open_date, "open_date", i, errs),
      close_date: toDateIst(raw.close_date, "close_date", i, errs),
      allotment_date: toDateIst(raw.allotment_date, "allotment_date", i, errs),

      band_lo, band_hi, issue_price,
      face_value: toDecimal(raw.face_value, "face_value", i, errs),
      lot_size: toInt(raw.lot_size),

      issue_size_cr: toDecimal(raw.issue_size_cr, "issue_size_cr", i, errs),
      fresh_cr: toDecimal(raw.fresh_cr, "fresh_cr", i, errs),
      ofs_cr: toDecimal(raw.ofs_cr, "ofs_cr", i, errs),
      market_cap_cr: toDecimal(raw.market_cap_cr, "market_cap_cr", i, errs),

      promoter_holding_pre: toDecimal(raw.promoter_holding_pre, "promoter_holding_pre", i, errs),
      promoter_holding_post: toDecimal(raw.promoter_holding_post, "promoter_holding_post", i, errs),
      registrar: raw.registrar ?? null,
      brlm_count: toInt(raw.brlm_count),
      allocation_qib_pct: toDecimal(raw.allocation_qib_pct, "allocation_qib_pct", i, errs),
      allocation_nii_pct: toDecimal(raw.allocation_nii_pct, "allocation_nii_pct", i, errs),
      allocation_retail_pct: toDecimal(raw.allocation_retail_pct, "allocation_retail_pct", i, errs),

      revenue: toDecimal(raw.revenue, "revenue", i, errs),
      total_income: toDecimal(raw.total_income, "total_income", i, errs),
      ebitda: toDecimal(raw.ebitda, "ebitda", i, errs),
      pat: toDecimal(raw.pat, "pat", i, errs),
      net_worth: toDecimal(raw.net_worth, "net_worth", i, errs),
      total_debt: toDecimal(raw.total_debt, "total_debt", i, errs),
      total_assets: toDecimal(raw.total_assets, "total_assets", i, errs),
      eps_pre: toDecimal(raw.eps_pre, "eps_pre", i, errs),
      eps_post: toDecimal(raw.eps_post, "eps_post", i, errs),
      roe: toDecimal(raw.roe, "roe", i, errs),
      roce: toDecimal(raw.roce, "roce", i, errs),
      ronw: toDecimal(raw.ronw, "ronw", i, errs),
      debt_equity: toDecimal(raw.debt_equity, "debt_equity", i, errs),
      pat_margin: toDecimal(raw.pat_margin, "pat_margin", i, errs),
      ebitda_margin: toDecimal(raw.ebitda_margin, "ebitda_margin", i, errs),
      rev_cagr_3y: toDecimal(raw.rev_cagr_3y, "rev_cagr_3y", i, errs),

      financial_history_json: jsonOrNull(raw.financial_history_json ?? raw.financial_history),

      ipo_pe: toDecimal(raw.ipo_pe, "ipo_pe", i, errs),
      pe_pre: toDecimal(raw.pe_pre, "pe_pre", i, errs),
      pe_post: toDecimal(raw.pe_post, "pe_post", i, errs),
      pb: toDecimal(raw.pb, "pb", i, errs),
      peer_median_pe: toDecimal(raw.peer_median_pe, "peer_median_pe", i, errs),
      fair_value: toDecimal(raw.fair_value, "fair_value", i, errs),
      margin_of_safety_pct: toDecimal(raw.margin_of_safety_pct, "margin_of_safety_pct", i, errs),
      valuation_score: toDecimal(raw.valuation_score, "valuation_score", i, errs),
      valuation_band: raw.valuation_band ?? null,

      qib_x: toDecimal(raw.qib_x, "qib_x", i, errs),
      nii_x: toDecimal(raw.nii_x, "nii_x", i, errs),
      bnii_x: toDecimal(raw.bnii_x, "bnii_x", i, errs),
      snii_x: toDecimal(raw.snii_x, "snii_x", i, errs),
      retail_x: toDecimal(raw.retail_x, "retail_x", i, errs),
      total_x: toDecimal(raw.total_x, "total_x", i, errs),
      anchor_amount_cr: toDecimal(raw.anchor_amount_cr, "anchor_amount_cr", i, errs),
      anchor_count: toInt(raw.anchor_count),

      listing_open: toDecimal(raw.listing_open, "listing_open", i, errs),
      d1_close: toDecimal(raw.d1_close, "d1_close", i, errs),
      gap_pct: toDecimal(raw.gap_pct, "gap_pct", i, errs),

      fundamental_verdict: fv,
      listing_action: la,

      engine_version: raw.engine_version ?? null,
      computed_at: toIsoUtc(raw.computed_at ?? new Date().toISOString(), "computed_at", i, errs),
      updated_at: toIsoUtc(raw.updated_at ?? new Date().toISOString(), "updated_at", i, errs),
    },
  };
};

// ---------------------------------------------------------------- market_observations
const ALLOWED_INTERVALS = new Set(["1d", "15m", "5m", "1m", "preopen", "tick"]);
const ALLOWED_OBS_TYPES = new Set([
  "candle", "preopen", "open", "tick", "close_d1", "orderbook", "level",
]);

export const validateMarketObservation: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const identity = commonIdentity(raw, i, errs);
  if (!identity) return null;

  const interval = req(raw.interval, "interval", i, errs);
  const observation_type = req(raw.observation_type, "observation_type", i, errs);
  const source = req(raw.source, "source", i, errs);
  if (!interval || !observation_type || !source) return null;
  if (!ALLOWED_INTERVALS.has(interval)) {
    errs.push({ row_index: i, field: "interval", message: `not allowed: ${interval}` });
    return null;
  }
  if (!ALLOWED_OBS_TYPES.has(observation_type)) {
    errs.push({ row_index: i, field: "observation_type", message: `not allowed: ${observation_type}` });
    return null;
  }

  // Daily rows use YYYY-MM-DD; everything else uses ISO instant.
  let observed_at: string | null;
  if (interval === "1d") {
    observed_at = toDateIst(raw.observed_at ?? raw.d, "observed_at", i, errs);
  } else {
    observed_at = toIsoUtc(raw.observed_at ?? raw.ts ?? raw.captured_at, "observed_at", i, errs);
  }
  if (!observed_at) return null;

  return {
    identity,
    row: {
      observed_at, interval, observation_type,
      o: toDecimal(raw.o, "o", i, errs),
      h: toDecimal(raw.h, "h", i, errs),
      l: toDecimal(raw.l, "l", i, errs),
      c: toDecimal(raw.c, "c", i, errs),
      v: toInt(raw.v),
      ltp: toDecimal(raw.ltp, "ltp", i, errs),
      buy_qty: toInt(raw.buy_qty),
      sell_qty: toInt(raw.sell_qty),
      iep: toDecimal(raw.iep, "iep", i, errs),
      traded_qty: toInt(raw.traded_qty),
      delivery_pct: toDecimal(raw.delivery_pct, "delivery_pct", i, errs),
      source,
      payload: jsonOrNull(raw.payload),
    },
  };
};

// ---------------------------------------------------------------- research_findings
const ALLOWED_FINDING_TYPES = new Set([
  "rhp", "rhp_summary", "sbi_note", "broker_note", "anchor",
  "insight", "risk_factor", "peer_comment",
]);

export const validateResearchFinding: Validator<Record<string, unknown>> = (raw, i, errs) => {
  const identity = commonIdentity(raw, i, errs);
  if (!identity) return null;

  const finding_type = req(raw.finding_type, "finding_type", i, errs);
  const source_type = req(raw.source_type, "source_type", i, errs);
  const finding = jsonOrNull(raw.finding ?? raw.full_json ?? raw.findings);
  if (!finding_type || !source_type) return null;
  if (!ALLOWED_FINDING_TYPES.has(finding_type)) {
    errs.push({ row_index: i, field: "finding_type", message: `not allowed: ${finding_type}` });
    return null;
  }
  if (!finding) {
    errs.push({ row_index: i, field: "finding", message: "required JSON body missing or unparseable" });
    return null;
  }

  return {
    identity,
    row: {
      finding_type, source_type,
      document_sha: raw.document_sha ?? raw.doc_id ?? raw.pdf_sha256 ?? null,
      finding,
      excerpt: raw.excerpt ?? raw.one_line ?? null,
      page_number: toInt(raw.page_number),
      severity: toInt(raw.severity),
      confidence: toDecimal(raw.confidence, "confidence", i, errs),
      evidence_refs: jsonOrNull(raw.evidence_refs),
      category: raw.category ?? null,
      direction: raw.direction ?? null,
      model: raw.model ?? null,
      model_version: raw.model_version ?? null,
      prompt_version: raw.prompt_version ?? null,
      cost_usd: toDecimal(raw.cost_usd, "cost_usd", i, errs),
      is_current: raw.is_current === undefined ? 1 : toBool01(raw.is_current),
      created_at: toIsoUtc(raw.created_at ?? new Date().toISOString(), "created_at", i, errs),
    },
  };
};

export const VALIDATORS: Record<string, Validator<Record<string, unknown>>> = {
  ipo: validateIpo,
  fundamentals: validateFundamentals,
  market_observations: validateMarketObservation,
  research_findings: validateResearchFinding,
};

export const PK_COLUMNS: Record<string, string[]> = {
  ipo: ["id"],
  fundamentals: ["ipo_id"],
  market_observations: ["ipo_id", "interval", "observation_type", "observed_at"],
  research_findings: ["id"],
};

export const ALLOWED_MODES: Record<string, IngestMode[]> = {
  ipo: ["coalesce_empty"],
  fundamentals: ["coalesce_empty", "upsert"],
  market_observations: ["append"],
  research_findings: ["append", "upsert"],
};
