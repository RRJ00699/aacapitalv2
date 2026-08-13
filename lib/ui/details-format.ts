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

/** SBI excerpts split from everything else (RHP / STRUCTURED land in rhp). */
export function splitEvidence(evidence: unknown): { rhp: EvidenceItem[]; sbi: EvidenceItem[] } {
  const list: EvidenceItem[] = Array.isArray(evidence) ? (evidence as EvidenceItem[]) : [];
  const sbi = list.filter((e) => String(e?.source_type ?? "").toUpperCase() === "SBI");
  const rhp = list.filter((e) => String(e?.source_type ?? "").toUpperCase() !== "SBI");
  return { rhp, sbi };
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

  const scan = (obj: unknown, group: string) => {
    if (!isPlainObject(obj)) return;
    for (const [k, v] of Object.entries(obj)) {
      if (!isPlainObject(v)) continue;
      const state = (v as DetailField).state;
      if (state === "MISSING" || state === "PENDING") {
        add(`${group}: ${humanizeKey(k)}`, String((v as DetailField).reason ?? "Not available."), String((v as DetailField).source ?? "—"));
      }
    }
  };

  scan(d.issue, "Issue");
  scan(d.governance_and_risk, "Governance");
  scan(d.valuation, "Valuation");
  scan(d.listing_outcome, "Listing outcome");
  scan((d.identity as Record<string, unknown>) ?? {}, "Identity");

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
