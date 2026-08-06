import type { SqlClient } from "./sql";

export const DETAILS_SCHEMA_VERSION = "ipo-details-v1" as const;
export const DETAILS_GMP_LAST_UPDATED = "2026-07-24";
export type FieldState = "AVAILABLE" | "MISSING" | "PENDING" | "VENDOR_FALLBACK" | "STALE";
export type DetailField<T> = { state: FieldState; value: T | null; reason: string | null; source: string | null; as_of: string | null; provenance?: Record<string, unknown> | null };

const field = <T>(value: T | null | undefined, source: string, asOf: unknown = null, reason = "Data is not available from the current V2 source."): DetailField<T> =>
  value == null ? { state: "MISSING", value: null, reason, source, as_of: asOf ? String(asOf) : null }
    : { state: "AVAILABLE", value, reason: null, source, as_of: asOf ? String(asOf) : null };
const pending = <T>(reason: string, source: string): DetailField<T> => ({ state: "PENDING", value: null, reason, source, as_of: null });
const missing = <T>(reason: string, source: string): DetailField<T> => ({ state: "MISSING", value: null, reason, source, as_of: null });

export function detailsFromRow(row: Record<string, unknown>, generatedAt = new Date().toISOString()) {
  const findings = row.findings && typeof row.findings === "object" ? row.findings as Record<string, unknown> : null;
  const evidence = Array.isArray(row.verified_evidence) ? row.verified_evidence : [];
  const analyzed = Boolean(row.analyzed_at);
  const risk = (key: string, label: string): DetailField<string[]> => {
    if (!analyzed) return pending("AI analysis has not yet run.", "rhp_findings.findings");
    const value = findings?.[key];
    return { state: "AVAILABLE", value: Array.isArray(value) ? value.map(String) : [value ? String(value) : `No finding extracted for ${label}.`], reason: null, source: "rhp_findings.findings", as_of: String(row.analyzed_at) };
  };
  const ratio = (value: unknown, sourceValue: unknown, name: string): DetailField<number> => {
    if (value == null) return missing(`${name} could not be computed; see missing_inputs.`, "valuation");
    const source = String(sourceValue ?? "unavailable");
    if (source.startsWith("proxy:")) return { state: "VENDOR_FALLBACK", value: Number(value), reason: "Issue-size-derived proxy; not a disclosed or reported company ratio.", source: "valuation", as_of: row.valuation_computed_at ? String(row.valuation_computed_at) : null, provenance: { derivation: source, label: "Issue-size-derived proxy" } };
    return field(Number(value), "valuation", row.valuation_computed_at);
  };
  const issuePrice = row.issue_price == null ? null : Number(row.issue_price);
  const fvLo = row.fair_value_lo == null ? null : Number(row.fair_value_lo);
  const fvHi = row.fair_value_hi == null ? null : Number(row.fair_value_hi);
  const mosReady = issuePrice != null && issuePrice !== 0 && fvLo != null && fvHi != null;
  const verdict = row.fundamental_verdict == null ? null : String(row.fundamental_verdict);
  const reasons = Array.isArray(row.decision_reasons) ? row.decision_reasons.map(String) : [];
  const junk = Array.isArray(row.junk_signals) ? row.junk_signals.map(String) : [];
  const outcomePending = !row.listing_date || new Date(String(row.listing_date)) > new Date();
  const outcome = <T>(value: unknown, name: string): DetailField<T> => value == null
    ? (outcomePending ? pending(`Listing outcome ${name} is pending until the IPO lists.`, "listing_outcomes") : missing(`Listing outcome ${name} is unavailable because no computed outcome is stored.`, "listing_outcomes"))
    : field(value as T, "listing_outcomes", row.outcome_computed_at);

  return {
    schema_version: DETAILS_SCHEMA_VERSION, generated_at: generatedAt,
    identity: { isin: String(row.isin).toUpperCase(), symbol: row.sym ? String(row.sym) : null, company_name: String(row.company_name), listing_date: field(row.listing_date ? String(row.listing_date) : null, "ipo") },
    issue: {
      issue_price: field(issuePrice, "ipo_issue"), band_low: field(row.band_lo == null ? null : Number(row.band_lo), "ipo_issue"), band_high: field(row.band_hi == null ? null : Number(row.band_hi), "ipo_issue"),
      issue_size_cr: field(row.issue_size_cr == null ? null : Number(row.issue_size_cr), "ipo_issue"), fresh_issue_cr: field(row.fresh_cr == null ? null : Number(row.fresh_cr), "ipo_issue"), ofs_cr: field(row.ofs_cr == null ? null : Number(row.ofs_cr), "ipo_issue"),
      lot_size: field(row.lot_size == null ? null : Number(row.lot_size), "ipo_issue"), face_value: field(row.face_value == null ? null : Number(row.face_value), "ipo_issue"),
      reservation_split: missing("Current NSE ingestion does not retain noOfSharesOffered.", "NSE ingestion"), shareholding_pre_post: missing("Not extracted into V2.", "RHP extraction"),
      objects_of_issue_with_amounts: missing("Not extracted into V2.", "RHP extraction"), cash: missing("Not extracted into V2.", "RHP extraction"),
    },
    ai_analysis: analyzed ? { state: "AVAILABLE" as const, findings, model: row.analysis_model ?? null, prompt_version: row.analysis_prompt_version ?? null, confidence: row.analysis_confidence ?? null, analyzed_at: row.analyzed_at, red_flag_count: row.red_flag_count ?? null, junk_signals: junk, reason: null }
      : { state: "PENDING" as const, findings: null, model: null, prompt_version: null, confidence: null, analyzed_at: null, red_flag_count: null, junk_signals: [], reason: "AI analysis has not yet run." },
    verified_evidence: evidence,
    governance_and_risk: { sebi_actions: risk("sebi_actions", "SEBI actions"), auditor_qualifications: risk("auditor_qualifications", "auditor qualifications"), going_concern: risk("going_concern", "going concern"), litigation: risk("litigation", "litigation"), related_party: risk("related_party", "related-party concerns"), contingent_liabilities: risk("contingent_liabilities", "contingent liabilities"), promoter_concerns: risk("promoter_concerns", "promoter concerns") },
    decision: { verdict: field(verdict, "decisions", row.decided_at), reasons: verdict ? field(reasons, "decisions", row.decided_at) : pending("A persisted decision is not yet available.", "decisions"), evidence: verdict ? field((row.decision_evidence ?? {}) as Record<string, unknown>, "decisions", row.decided_at) : pending("A persisted decision is not yet available.", "decisions"), kill_reason: verdict === "JUNK" ? field({ verdict, reasons, junk_signals: junk, provenance: "Derived from persisted verdict, reasons and latest RHP junk signals." }, "derived", row.decided_at) : missing("kill_reason applies only to JUNK decisions.", "derived") },
    valuation: { score: field(row.score == null ? null : Number(row.score), "valuation", row.valuation_computed_at), band: field(row.score_band == null ? null : String(row.score_band), "valuation", row.valuation_computed_at), engine_version: field(row.engine_version == null ? null : String(row.engine_version), "valuation", row.valuation_computed_at), computed_at: field(row.valuation_computed_at == null ? null : String(row.valuation_computed_at), "valuation"), pe: ratio(row.pe, row.pe_source, "P/E"), pb: ratio(row.pb, row.pb_source, "P/B"), pe_source: field(row.pe_source == null ? null : String(row.pe_source), "valuation"), pb_source: field(row.pb_source == null ? null : String(row.pb_source), "valuation"), peer_median_pe: field(row.peer_median_pe == null ? null : Number(row.peer_median_pe), "valuation", row.valuation_computed_at), fair_value_low: field(fvLo, "valuation", row.valuation_computed_at), fair_value_high: field(fvHi, "valuation", row.valuation_computed_at), inputs_used: field((row.inputs_used ?? null) as Record<string, unknown> | null, "valuation", row.valuation_computed_at), missing_inputs: field((row.missing_inputs ?? []) as string[], "valuation", row.valuation_computed_at), margin_of_safety: mosReady ? field({ mos_low_pct: ((fvLo! - issuePrice!) / issuePrice!) * 100, mos_high_pct: ((fvHi! - issuePrice!) / issuePrice!) * 100, label: "Derived margin-of-safety range", formula: "(fair_value - issue_price) / issue_price * 100", inputs: { fair_value_low: fvLo, fair_value_high: fvHi, issue_price: issuePrice } }, "derived", row.valuation_computed_at) : missing("Issue price and both fair-value bounds are required.", "derived") },
    listing_outcome: { listing_open: outcome(row.listing_open, "listing_open"), gap_pct: outcome(row.gap_pct, "gap_pct"), d1_close: outcome(row.d1_close, "d1_close"), best_close: outcome(row.best_close, "best_close"), worst_close: outcome(row.worst_close, "worst_close"), pool: outcome(row.pool, "pool"), hold_positive_vs_open: outcome(row.hold_positive_vs_open, "hold_positive_vs_open"), winner_35: outcome(row.winner_35, "winner_35"), ceiling_20: { ...outcome(row.ceiling_20, "ceiling_20"), label: "Historical ceiling indicator — non-executable" }, computed_at: outcome(row.outcome_computed_at, "computed_at"), dataset_version: outcome(row.dataset_version, "dataset_version") },
    gmp: { state: "STALE" as const, available: false as const, last_updated: DETAILS_GMP_LAST_UPDATED, reason: "No maintained live source" },
  };
}

export async function fetchDetailsRows(sql: SqlClient, ipoIds: Array<string | number>) {
  if (!ipoIds.length) return [];
  return sql`
    SELECT i.id AS ipo_id, i.isin, UPPER(COALESCE(i.symbol,'')) AS sym, i.name_display AS company_name, i.listing_date,
      iss.issue_price,iss.band_lo,iss.band_hi,iss.issue_size_cr,iss.fresh_cr,iss.ofs_cr,iss.lot_size,iss.face_value,
      v.score,v.score_band,v.engine_version,v.computed_at AS valuation_computed_at,v.pe,v.pb,v.peer_median_pe,v.fair_value_lo,v.fair_value_hi,v.inputs_used,v.missing_inputs,v.inputs_used->>'pe_source' AS pe_source,v.inputs_used->>'pb_source' AS pb_source,
      rf.findings,rf.model AS analysis_model,rf.prompt_version AS analysis_prompt_version,rf.confidence AS analysis_confidence,rf.analyzed_at,rf.red_flag_count,rf.junk_signals,
      de.fundamental_verdict,de.reasons AS decision_reasons,de.evidence_refs AS decision_evidence,de.decided_at,
      lo.listing_open,lo.gap_pct,lo.d1_close,lo.best_close,lo.worst_close,lo.pool,lo.hold_positive_vs_open,lo.winner_35,lo.ceiling_20,lo.computed_at AS outcome_computed_at,lo.dataset_version,
      COALESCE((SELECT json_agg(json_build_object('excerpt',s.excerpt,'page_number',s.page_number,'doc_id',s.doc_id,'document',json_build_object('doc_type',doc.doc_type,'url',doc.url,'sha256',doc.sha256,'page_count',doc.page_count),'category',s.category,'direction',s.direction,'source_type',s.source_type) ORDER BY s.id) FROM insights s JOIN documents doc ON doc.id=s.doc_id WHERE s.ipo_id=i.id AND s.is_current AND s.excerpt IS NOT NULL AND s.page_number IS NOT NULL), '[]'::json) AS verified_evidence
    FROM ipo i JOIN ipo_issue iss ON iss.ipo_id=i.id
    LEFT JOIN LATERAL (SELECT * FROM valuation x WHERE x.ipo_id=i.id AND x.engine_version LIKE 'v2-score-%' ORDER BY x.computed_at DESC LIMIT 1) v ON true
    LEFT JOIN LATERAL (SELECT * FROM rhp_findings x WHERE x.ipo_id=i.id ORDER BY x.analyzed_at DESC LIMIT 1) rf ON true
    LEFT JOIN LATERAL (SELECT * FROM decisions x WHERE x.ipo_id=i.id ORDER BY x.decided_at DESC LIMIT 1) de ON true
    LEFT JOIN listing_outcomes lo ON lo.ipo_id=i.id WHERE i.id = ANY(${ipoIds})`;
}
