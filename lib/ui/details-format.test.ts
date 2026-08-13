import test from "node:test";
import assert from "node:assert/strict";
import {
  toValueNode, fmtNum, fmtCr, fmtRupee, humanizeKey, fieldDisplay, classLabel,
  splitEvidence, deriveMarketCap, deriveLotValue, buildMissingRegister, looksSerialized,
} from "./details-format";

test("toValueNode never stringifies: arrays become lists, objects become labeled rows", () => {
  assert.deepEqual(toValueNode(["a", "b"]), { kind: "list", items: [{ kind: "scalar", text: "a" }, { kind: "scalar", text: "b" }] });
  const rows = toValueNode({ pe_source: "proxy:issue_size/pat", nested: { a: 1 } });
  assert.equal(rows.kind, "rows");
  assert.equal((rows as any).rows[0].label, "Pe source");
  assert.equal((rows as any).rows[1].value.kind, "rows"); // nested object -> nested rows, not JSON
});

test("toValueNode collapses empties and formats scalars", () => {
  assert.deepEqual(toValueNode(null), { kind: "empty" });
  assert.deepEqual(toValueNode(""), { kind: "empty" });
  assert.deepEqual(toValueNode({}), { kind: "empty" });
  assert.deepEqual(toValueNode([]), { kind: "empty" });
  assert.deepEqual(toValueNode(true), { kind: "scalar", text: "Yes" });
  assert.deepEqual(toValueNode(1234.5), { kind: "scalar", text: "1,234.5" });
});

test("a serialized object never appears — no [object Object], no JSON blob", () => {
  const node = toValueNode({ summary: { a: [1, 2] } });
  const walk = (n: any): string[] => n.kind === "scalar" ? [n.text] : n.kind === "list" ? n.items.flatMap(walk) : n.kind === "rows" ? n.rows.flatMap((r: any) => walk(r.value)) : [];
  for (const t of walk(node)) assert.equal(looksSerialized(t), false, `leaked: ${t}`);
});

test("number and currency formatting", () => {
  assert.equal(fmtNum(1234567), "12,34,567"); // en-IN grouping
  assert.equal(fmtNum(3.14159), "3.1416");
  assert.equal(fmtCr(1101.28), "₹1,101.28 Cr");
  assert.equal(fmtRupee(425), "₹425");
  assert.equal(fmtCr(null), "—");
});

test("humanizeKey and classLabel", () => {
  assert.equal(humanizeKey("fresh_issue_cr"), "Fresh issue cr");
  assert.equal(classLabel("VERIFIED_FACT"), "VERIFIED FACT");
  assert.equal(classLabel("DETERMINISTIC_PRO_FORMA"), "DETERMINISTIC PRO-FORMA");
  assert.equal(classLabel("garbage"), "UNVERIFIED / UNKNOWN");
});

test("fieldDisplay distinguishes states and surfaces proxy label", () => {
  assert.equal(fieldDisplay({ state: "AVAILABLE", value: 425 }).hasValue, true);
  assert.equal(fieldDisplay({ state: "MISSING", value: null, reason: "gone" }).hasValue, false);
  assert.equal(fieldDisplay({ state: "PENDING", value: null, reason: "not yet" }).hasValue, false);
  const proxy = fieldDisplay({ state: "VENDOR_FALLBACK", value: 20, provenance: { label: "Issue-size-derived proxy" } });
  assert.equal(proxy.hasValue, true);
  assert.equal(proxy.proxyLabel, "Issue-size-derived proxy");
  // MISSING never coerces to a value.
  assert.deepEqual(fieldDisplay({ state: "MISSING", value: null }).node, { kind: "empty" });
});

test("splitEvidence buckets SBI, RHP+STRUCTURED, and other without mislabeling", () => {
  const ev = [
    { excerpt: "rhp words", page_number: 42, source_type: "RHP" },
    { excerpt: "sbi words", page_number: 7, source_type: "SBI" },
    { excerpt: "struct", page_number: 3, source_type: "STRUCTURED" },
    { excerpt: "house", page_number: 9, source_type: "HOUSE_RULE" },
  ];
  const { rhp, sbi, other } = splitEvidence(ev);
  assert.equal(sbi.length, 1);
  assert.equal(sbi[0].excerpt, "sbi words");
  assert.equal(rhp.length, 2); // RHP + STRUCTURED
  assert.equal(other.length, 1); // HOUSE_RULE is NOT presented as RHP
  assert.equal(other[0].source_type, "HOUSE_RULE");
  assert.deepEqual(splitEvidence(null), { rhp: [], sbi: [], other: [] });
});

test("derived issue metrics are labeled and honest when inputs are missing", () => {
  const mc = deriveMarketCap(425, 15.06);
  assert.equal(mc.available, true);
  assert.equal(mc.text, fmtCr(425 * 15.06));
  assert.equal(deriveMarketCap(425, null).available, false); // no fabricated number
  assert.equal(deriveLotValue(30, 425).text, "₹12,750");
  assert.equal(deriveLotValue(null, 425).available, false);
});

test("missing register folds absent fields to filling producers, deduped", () => {
  const d = {
    intelligence_profile: null,
    issue: { reservation_split: { state: "MISSING", value: null, reason: "no noOfSharesOffered", source: "NSE ingestion" } },
    governance_and_risk: { litigation: { state: "PENDING", value: null, reason: "AI not run", source: "rhp_findings" } },
    valuation: {}, listing_outcome: {}, identity: {},
  };
  const rows = buildMissingRegister(d);
  const fields = rows.map((r) => r.field);
  assert.ok(fields.includes("Issue: Reservation split"));
  assert.ok(fields.includes("Governance: Litigation"));
  assert.ok(fields.some((f) => f.includes("revenue & margins")));
  assert.ok(fields.some((f) => f.includes("canonical profile")));
  assert.equal(new Set(fields).size, fields.length); // deduped
});
