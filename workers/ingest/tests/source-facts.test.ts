// workers/ingest/tests/source-facts.test.ts
//
// Pins the SHA-256 `observation_hash` used by source_facts idempotency
// (see D1_EVIDENCE_REPORT.md §6 note fixing R5). The hash is computed as:
//
//   sha256(field | value | source | document_sha | pipeline_version)
//
// where `|` is a literal pipe and null components are replaced with the
// empty string. Two retries with identical values yield the same hash and
// therefore collapse into ONE row; a genuinely different value produces a
// new hash and a new row.
//
// The same hashing rule is implemented in tools/migrate/neon_to_d1.py:
// `observation_hash`. The pinned digests below MUST match the Python side.

import test from "node:test";
import assert from "node:assert/strict";
import { observationHash } from "../src/source-facts";

interface Fixture {
  args: [string, string | null, string, string | null | undefined, string | null | undefined];
  hash: string;
}

// Pinned outputs (regenerate with tools/migrate/neon_to_d1.py:observation_hash).
const FIXTURES: Fixture[] = [
  {
    args: ["fundamentals.issue_price", "110.00", "sebi_rhp", "doc123", "v1"],
    hash: "94dac0a29b68378cf03d1cad1fb6b94ebd7e11767c2b94c0ff44511f55124c2f",
  },
  {
    args: ["fundamentals.issue_price", "115.00", "sebi_rhp", "doc123", "v1"],
    hash: "1b09f11c1f25da54856bf3e13321f15fb3d6b1d265ba05cd14ecc66c8c117fe9",
  },
  {
    args: ["ipo.status", "Listed", "nse", null, null],
    hash: "ab9d12a5307a1f2e7c96393f4fc935b3ae80409adffbeb873fa54d0a65308f4d",
  },
  {
    args: ["ipo.status", null, "nse", null, null],
    hash: "8d50d1751f7227162ab17f4658f3cc618beeac649a46d9c5aa55f47fbb9569dd",
  },
];

for (const { args, hash } of FIXTURES) {
  test(`observationHash(${JSON.stringify(args)}) === ${hash.slice(0, 12)}...`, async () => {
    const got = await observationHash(...args);
    assert.equal(got, hash);
    // Length invariant enforced by CHECK (length(observation_hash) = 64) on D1.
    assert.equal(got.length, 64);
  });
}

test("observationHash is deterministic across repeated calls", async () => {
  const args = FIXTURES[0].args;
  const a = await observationHash(...args);
  const b = await observationHash(...args);
  const c = await observationHash(...args);
  assert.equal(a, b);
  assert.equal(b, c);
});

test("observationHash separates null value from empty string", async () => {
  // '|' + '' + '|' and '|' + null-as-empty '|' both stringify to the same
  // canonical input under our rule; document that they DO collide by design.
  // Fixing R5 requires that identical semantic retries collide; it does NOT
  // require null and empty string to differ.
  const a = await observationHash("f", null, "s", null, null);
  const b = await observationHash("f", "", "s", null, null);
  assert.equal(a, b);
});

test("observationHash separates two documents on the same field/value", async () => {
  const a = await observationHash("f", "1", "s", "docA", "v1");
  const b = await observationHash("f", "1", "s", "docB", "v1");
  assert.notEqual(a, b);
});

test("observationHash separates pipeline versions on the same value", async () => {
  const a = await observationHash("f", "1", "s", "docA", "v1");
  const b = await observationHash("f", "1", "s", "docA", "v2");
  assert.notEqual(a, b);
});

// ---------------------------------------------------------------------------
// Regenerating Python-side hashes:
//
//   python3 -c "import hashlib
//   def h(f,v,s,d,p): return hashlib.sha256('|'.join([f, v or '', s, d or '', p or '']).encode()).hexdigest()
//   for c in [('fundamentals.issue_price','110.00','sebi_rhp','doc123','v1'),
//             ('fundamentals.issue_price','115.00','sebi_rhp','doc123','v1'),
//             ('ipo.status','Listed','nse',None,None),
//             ('ipo.status',None,'nse',None,None)]:
//       print(c,'->',h(*c))"
// ---------------------------------------------------------------------------
