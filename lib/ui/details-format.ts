// lib/ui/details-format.ts — pure presentation helpers for the Complete Details
// screen. Framework-agnostic (no React) so it is unit-testable under
// lib/**/*.test.ts. The cardinal rule: NO JSON.stringify / [object Object] ever
// reaches a caller — every value is turned into a structured ValueNode that a
// renderer walks into DOM (arrays -> lists, objects -> labeled rows).

export type FieldState = "AVAILABLE" | "MISSING" | "PENDING" | "VENDOR_FALLBACK" | "STALE";
export type DetailField<T = unknown> = {
  state?: FieldState;
  value?: T | null;
  reason?: string | null;
  source?: string | null;
  as_of?: string | null;
  provenance?: Record<string, unknown> | null;
};

/** A value turned into a shape a renderer can walk without ever stringifying. */
export type ValueNode =
  | { kind: "empty" }
  | { kind: "scalar"; text: string }
  | { kind: "list"; items: ValueNode[] }
  | { kind: "rows"; rows: Array<{ label: string; value: ValueNode }> };

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Human-friendly number: up to 4 decimals, trailing zeros trimmed, grouped. */
export function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return "—";
  const rounded = Math.round(n * 10000) / 10000;
  const [int, frac] = String(rounded).split(".");
  const grouped = Number(int).toLocaleString("en-IN");
  return frac ? `${grouped}.${frac}` : grouped;
}

/** "₹1,234 Cr" style. unit defaults to Cr. */
export function fmtCr(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  return `₹${fmtNum(Number(n))} Cr`;
}

export function fmtRupee(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  return `₹${fmtNum(Number(n))}`;
}

/** snake_or.dotted_key -> "Snake or dotted key" for labeled rows. */
export function humanizeKey(key: string): string {
  const spaced = key.replace(/[_.]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Turn ANY value into a ValueNode. This is the single guard that keeps
 * JSON.stringify and [object Object] out of the DOM.
 */
export function toValueNode(v: unknown): ValueNode {
  if (v == null || v === "") return { kind: "empty" };
  if (typeof v === "number") return { kind: "scalar", text: fmtNum(v) };
  if (typeof v === "boolean") return { kind: "scalar", text: v ? "Yes" : "No" };
  if (typeof v === "string") return { kind: "scalar", text: v };
  if (Array.isArray(v)) {
    const items = v.map(toValueNode).filter((n) => n.kind !== "empty");
    return items.length ? { kind: "list", items } : { kind: "empty" };
  }
  if (isPlainObject(v)) {
    const rows = Object.entries(v)
      .map(([k, val]) => ({ label: humanizeKey(k), value: toValueNode(val) }))
      .filter((r) => r.value.kind !== "empty");
    return rows.length ? { kind: "rows", rows } : { kind: "empty" };
  }
  // Fallback for symbols/functions/bigint — never stringify an object here.
  return { kind: "scalar", text: String(v) };
}

// ── Evidence-class labels (§3 / canonical profile) ───────────────────────────
export type EvidenceClass =
  | "VERIFIED_FACT"
  | "DETERMINISTIC_PRO_FORMA"
  | "SCENARIO_OPTIONALITY"
  | "UNVERIFIED_UNKNOWN";

export const EVIDENCE_CLASS_LABEL: Record<EvidenceClass, string> = {
  VERIFIED_FACT: "VERIFIED FACT",
  DETERMINISTIC_PRO_FORMA: "DETERMINISTIC PRO-FORMA",
  SCENARIO_OPTIONALITY: "SCENARIO / OPTIONALITY",
  UNVERIFIED_UNKNOWN: "UNVERIFIED / UNKNOWN",
};

export function classLabel(c: string | null | undefined): string {
  const key = String(c ?? "").toUpperCase() as EvidenceClass;
  return EVIDENCE_CLASS_LABEL[key] ?? "UNVERIFIED / UNKNOWN";
}

// ── State → human copy for a DetailField ────────────────────────────────────
export type FieldDisplay = {
  state: FieldState;
  /** true only for AVAILABLE / VENDOR_FALLBACK / STALE — i.e. there IS a value. */
  hasValue: boolean;
  node: ValueNode;
  reason: string | null;
  source: string | null;
  as_of: string | null;
  /** VENDOR_FALLBACK provenance label, e.g. "Issue-size-derived proxy". */
  proxyLabel: string | null;
};

const stateHasValue = (s: FieldState) => s === "AVAILABLE" || s === "VENDOR_FALLBACK" || s === "STALE";

/** Normalize a raw DetailField (or a bare value) into a render-ready display. */
export function fieldDisplay(f: DetailField | null | undefined): FieldDisplay {
  const state: FieldState = (f?.state as FieldState) ?? "MISSING";
  const has = stateHasValue(state) && f?.value != null && f?.value !== "";
  const proxyLabel =
    state === "VENDOR_FALLBACK" && f?.provenance && typeof f.provenance.label === "string"
      ? (f.provenance.label as string)
      : null;
  return {
    state,
    hasValue: has,
    node: has ? toValueNode(f?.value) : { kind: "empty" },
    reason: f?.reason ?? null,
    source: f?.source ?? null,
    as_of: f?.as_of ?? null,
    proxyLabel,
  };
}

// ── Verified-evidence splitting (§5 RHP vs §6 SBI) ──────────────────────────
export type EvidenceItem = {
  excerpt?: string;
  page_number?: number | null;
  doc_id?: number | string | null;
  document?: { doc_type?: string; url?: string; sha256?: string; page_count?: number } | null;
  category?: string | null;
  direction?: string | null;
  source_type?: string | null;
};

/**
 * Verified evidence bucketed by source_type so provenance is never mislabeled:
 * - rhp:   RHP + STRUCTURED (the disclosure-document evidence, §5)
 * - sbi:   SBI research-note excerpts (§6)
 * - other: any other source_type (e.g. HOUSE_RULE) — rendered under its own
 *          label, never presented as RHP.
 */
export function splitEvidence(evidence: unknown): { rhp: EvidenceItem[]; sbi: EvidenceItem[]; other: EvidenceItem[] } {
  const list: EvidenceItem[] = Array.isArray(evidence) ? (evidence as EvidenceItem[]) : [];
  const st = (e: EvidenceItem) => String(e?.source_type ?? "").toUpperCase();
  const sbi = list.filter((e) => st(e) === "SBI");
  const rhp = list.filter((e) => st(e) === "RHP" || st(e) === "STRUCTURED");
  const other = list.filter((e) => !["SBI", "RHP", "STRUCTURED"].includes(st(e)));
  return { rhp, sbi, other };
}

// ── Presentation-derived issue metrics (§2), labeled pro-forma ──────────────
export type DerivedMetric = { available: boolean; text: string; formula: string; reason?: string };

/** Market cap at issue = issue_price × post_issue_shares_cr (crore shares). */
export function deriveMarketCap(issuePrice: unknown, postIssueSharesCr: unknown): DerivedMetric {
  const p = Number(issuePrice);
  const s = Number(postIssueSharesCr);
  const formula = "issue_price × post_issue_shares_cr";
  if (!Number.isFinite(p) || p <= 0 || !Number.isFinite(s) || s <= 0)
    return { available: false, text: "—", formula, reason: "Needs issue price and post-issue share count (from canonical pro-forma inputs)." };
  return { available: true, text: fmtCr(p * s), formula };
}

/** Lot value = lot_size × issue_price. */
export function deriveLotValue(lotSize: unknown, issuePrice: unknown): DerivedMetric {
  const lot = Number(lotSize);
  const p = Number(issuePrice);
  const formula = "lot_size × issue_price";
  if (!Number.isFinite(lot) || lot <= 0 || !Number.isFinite(p) || p <= 0)
    return { available: false, text: "—", formula, reason: "Needs lot size and issue price." };
  return { available: true, text: fmtRupee(lot * p), formula };
}

// ── Consolidated MISSING-DATA register (§10) ────────────────────────────────
export type MissingRow = { field: string; reason: string; producer: string };

/**
 * Every genuinely-absent field for THIS ipo, with the producer that would fill
 * it. Combines the MISSING/PENDING DetailFields actually in the payload with
 * the always-empty profile collections that we deliberately fold in here rather
 * than render as permanent empty cards.
 */
export function buildMissingRegister(d: Record<string, unknown>): MissingRow[] {
  const rows: MissingRow[] = [];
  const seen = new Set<string>();
  const add = (field: string, reason: string, producer: string) => {
    if (seen.has(field)) return;
    seen.add(field);
    rows.push({ field, reason, producer });
  };

  // The register quotes the SAME sentence the row on screen shows, so the two
  // can never disagree about why a field is absent.
  const facts = lifecycleFacts(d);
  const scan = (obj: unknown, branch: string, group: string) => {
    if (!isPlainObject(obj)) return;
    for (const [k, v] of Object.entries(obj)) {
      if (!isPlainObject(v)) continue;
      const state = (v as DetailField).state;
      if (state === "MISSING" || state === "PENDING") {
        const copy = absenceCopy(`${branch}.${k}`, v as DetailField, facts);
        add(`${group}: ${humanizeKey(k)}`, copy.reason ?? "Not available.", copy.producer ?? "—");
      }
    }
  };

  scan(d.issue, "issue", "Issue");
  scan(d.governance_and_risk, "governance_and_risk", "Governance");
  scan(d.valuation, "valuation", "Valuation");
  scan(d.listing_outcome, "listing_outcome", "Listing outcome");
  scan((d.identity as Record<string, unknown>) ?? {}, "identity", "Identity");

  // Always-absent from ipo-details-v1 regardless of IPO — the honest register
  // for the fields whole sections would want (see field-inventory audit).
  if (d.intelligence_profile == null)
    add("Financials: canonical profile", "Canonical financials require reported PAT, debt, post-issue shares and issue price — not all present.", "RHP financial-table extraction");
  add("Financials: revenue & margins", "Revenue is not carried in financial_statements select; margins cannot be derived.", "RHP financial-table extraction");
  add("Issue: subscription (x times, per category)", "Subscription figures are not shipped in this snapshot.", "NSE archive");
  add("Valuation: peer set / peer table", "Only the peer median multiple ships; the peer constituents are not carried.", "SBI note / RHP peer table");
  add("SBI: structured rating / target / peers", "No structured SBI extraction ships; only verbatim SBI excerpts (if any) appear as evidence.", "SBI Sonnet extraction");
  add("Demand: anchor book", "Anchor investor table / amounts are not shipped.", "NSE anchor PDF parse");
  add("GMP", "No maintained live grey-market source.", "GMP (stale)");

  return rows;
}

// ── Small helpers shared by the component ───────────────────────────────────
export const isNonEmpty = (n: ValueNode): boolean => n.kind !== "empty";

/** True when a value looks like the forbidden serialized-object leak. */
export function looksSerialized(text: string): boolean {
  return text.includes("[object Object]") || /^\s*[[{].*[\]}]\s*$/.test(text);
}

// ── Pending vs missing: honest absence copy ─────────────────────────────────
// The producer's `field()` helper stamps ONE default sentence on every absent
// scalar it does not have a specific reason for:
//
//   "Issue price — not available — Data is not available from the current V2 source."
//
// For Molbio (ipo_id 1100) that read like a defect report on a screen where the
// truth was mundane: the issue had not been priced yet. The sentence is a
// producer DEFAULT — it means "no reason was written", not "this is broken" —
// so the UI is free to substitute a specific one. What it must NOT do is
// rewrite `DetailField.state`: the state belongs to the payload, and only the
// human-readable sentence (and the lead word in front of it) is ours.
//
// Nothing here invents a lifecycle field. The only lifecycle date this snapshot
// carries is the listing date, so the two gates below are derived from what is
// already in the payload:
//   listed  — `listing_outcome` leaves are PENDING only while the IPO has not
//             listed (the producer's own `outcomePending`), MISSING after.
//   priced  — `issue.issue_price` is AVAILABLE.

/** The producer's default absence sentence. Its presence means "no reason written". */
export const GENERIC_ABSENCE_REASON = "Data is not available from the current V2 source.";

/** True when the reason is the producer's default rather than a written one. */
export function isGenericReason(reason: string | null | undefined): boolean {
  return !reason || reason.trim() === GENERIC_ABSENCE_REASON;
}

/**
 * What the payload itself says about where this IPO is in its life.
 * `listed: null` means the record carries no listing-outcome branch at all, so
 * nothing is claimed either way.
 */
export type LifecycleFacts = { listed: boolean | null; priced: boolean };
export const LIFECYCLE_UNKNOWN: LifecycleFacts = { listed: null, priced: false };

export function lifecycleFacts(details: Record<string, unknown> | null | undefined): LifecycleFacts {
  const outcome = isPlainObject(details?.listing_outcome) ? details!.listing_outcome as Record<string, unknown> : null;
  let leaves = 0;
  let pending = 0;
  if (outcome) {
    for (const v of Object.values(outcome)) {
      if (!isPlainObject(v) || typeof (v as DetailField).state !== "string") continue;
      leaves += 1;
      if ((v as DetailField).state === "PENDING") pending += 1;
    }
  }
  const issue = isPlainObject(details?.issue) ? details!.issue as Record<string, unknown> : null;
  const priceField = issue && isPlainObject(issue.issue_price) ? issue.issue_price as DetailField : undefined;
  return {
    listed: leaves === 0 ? null : pending > 0 ? false : true,
    priced: fieldDisplay(priceField).hasValue,
  };
}

/**
 * Which lifecycle event has to happen before a field can exist.
 * - "listing" — the issue terms; absent before the IPO lists is explainable.
 * - "pricing" — the scoring engine cannot run without an issue price.
 * - "decision" — mirrors the producer, which already marks the sibling
 *   `decision.reasons` / `decision.evidence` PENDING whenever no decision row
 *   has been written. `decision.verdict` is the one leaf it forgets.
 */
type AbsenceGate = "listing" | "pricing" | "decision";
type ReasonEntry = { gate: AbsenceGate; pending: string; missing: string };

/**
 * Every field whose absence the lifecycle explains. A field NOT in this book
 * keeps whatever the payload said — including the generic sentence, which is
 * then the honest answer: nobody has written a reason for it.
 */
const REASON_BOOK: Record<string, ReasonEntry> = {
  "identity.listing_date": {
    gate: "listing",
    pending: "pending — set when the exchange confirms the listing date",
    missing: "No listing date is recorded for this IPO.",
  },
  "issue.issue_price": {
    gate: "listing",
    pending: "pending — set when the issue is priced",
    missing: "No issue price is recorded for this IPO in the issue record.",
  },
  "issue.band_low": {
    gate: "listing",
    pending: "pending — set when the price band is announced",
    missing: "No price band is recorded for this IPO in the issue record.",
  },
  "issue.band_high": {
    gate: "listing",
    pending: "pending — set when the price band is announced",
    missing: "No price band is recorded for this IPO in the issue record.",
  },
  "issue.issue_size_cr": {
    gate: "listing",
    pending: "pending — set when the issue size is filed with the offer document",
    missing: "No issue size is recorded for this IPO in the issue record.",
  },
  "issue.fresh_issue_cr": {
    gate: "listing",
    pending: "pending — the fresh-issue amount is set when the offer document is filed",
    missing: "No fresh-issue amount is recorded for this IPO in the issue record.",
  },
  "issue.ofs_cr": {
    gate: "listing",
    pending: "pending — the offer-for-sale amount is set when the offer document is filed",
    missing: "No offer-for-sale amount is recorded for this IPO in the issue record.",
  },
  "issue.lot_size": {
    gate: "listing",
    pending: "pending — fixed with the price band",
    missing: "No lot size is recorded for this IPO in the issue record.",
  },
  "issue.face_value": {
    gate: "listing",
    pending: "pending — carried with the issue terms once they are filed",
    missing: "No face value is recorded for this IPO in the issue record.",
  },
  "decision.verdict": {
    gate: "decision",
    pending: "pending — a persisted decision is not yet available",
    missing: "pending — a persisted decision is not yet available",
  },
};

// The valuation leaves all wait on the same thing: a v2-score row, which the
// engine cannot compute without an issue price. One entry, applied to each.
const VALUATION_ENTRY: ReasonEntry = {
  gate: "pricing",
  pending: "pending — the v2 scoring engine runs on the issue price, which is not set yet",
  missing: "No v2-score valuation row is stored for this IPO.",
};
for (const leaf of ["score", "band", "engine_version", "computed_at", "peer_median_pe",
  "fair_value_low", "fair_value_high", "inputs_used", "missing_inputs", "pe_source", "pb_source"]) {
  REASON_BOOK[`valuation.${leaf}`] = VALUATION_ENTRY;
}

/** The keys the book covers — exported so a test can pin the sweep. */
export const HONEST_REASON_KEYS: readonly string[] = Object.keys(REASON_BOOK).sort();

/**
 * What the UI prints for a field with no value.
 * `lead` is the word in front of the reason ("pending" / "not available"); it is
 * UI copy, NOT the payload state, which keeps rendering on its own badge.
 * `producer` names who would fill the gap, so a MISSING field never hides it.
 */
export type AbsenceCopy = { lead: "pending" | "not available"; reason: string | null; producer: string | null };

export function absenceCopy(
  key: string | undefined,
  f: DetailField | null | undefined,
  facts: LifecycleFacts = LIFECYCLE_UNKNOWN,
): AbsenceCopy {
  const state: FieldState = (f?.state as FieldState) ?? "MISSING";
  const producer = f?.source ? String(f.source) : null;
  const entry = key ? REASON_BOOK[key] : undefined;
  // A reason the producer actually wrote is the producer's to keep.
  if (!isGenericReason(f?.reason) || !entry)
    return { lead: state === "PENDING" ? "pending" : "not available", reason: f?.reason ?? null, producer };
  const explainable = entry.gate === "decision"
    || (entry.gate === "listing" && facts.listed !== true)
    || (entry.gate === "pricing" && !facts.priced);
  return explainable
    ? { lead: "pending", reason: entry.pending, producer }
    : { lead: "not available", reason: entry.missing, producer };
}
