# SBI R6 strict extraction transport

Status: code contract introduced in PR #323 and revised by PR #325. No production
activation is implied by this document.

## Why R6 exists

The historical SBI pilot exposed four boundary defects: free-form JSON drift, two
inconsistent definitions of "extracted", source-fact provenance arguments that were not
persisted, and item-drop diagnostics that disappeared on later evidence/write failures.
R6 fixes those boundaries before another paid Messages call.

## Model boundary

The production SBI Messages request uses one client tool, `record_sbi_extraction`, with
`strict: true`, a closed JSON schema, and forced single-tool choice with parallel tool
use disabled. Temperature is zero. The paid path accepts only one correctly named
`tool_use` block and never falls back to parsing assistant prose. `max_tokens` remains a
truncation result and never enters parsing or writers.

`PROMPT_VERSION` is `sbi-v1.4`. The model returns one to three contiguous, page-scoped
`evidence_refs` rather than an excerpt or page number. Python resolves those references
to the exact source text and synthetic PDF page, and the resolved excerpt retains the
15-word hard limit.

## Evidence and canonical writes

Unicode and typography normalization is comparison-only; the Python-resolved source
excerpt is stored unchanged. Surviving claims/facts must cite contiguous source units
from one PDF page. Item-level schema/bound violations are recorded in `dropped_items`;
after parsing, those diagnostics are kept on successful, evidence-rejected, and
write-error records.

SBI scalar facts write the live `source_facts.doc_id` foreign key plus the supplied model
confidence. The existing fact change-detection identity remains `(ipo_id, field, source)`;
`doc_id` and confidence are provenance, not a new dedup key.

Extraction completion has one SQL predicate shared by the runner and migration verifier:
a matching SBI insight OR a matching SBI source-fact row for the same document/model/
prompt version is complete. New writes use `sbi-v1.4`; existing `sbi-v1.3` rows also
satisfy the default completion predicate so the transport upgrade does not automatically
requeue previously completed paid work. This allows a legitimate scalar-only extraction
to reach `EXTRACTION_MISSING=0`.

## Canonical worker and cost boundary

The extraction queue is the current set of pending SBI documents in the Neon documents
ledger. The worker reads the immutable R2 object, verifies its SHA-256 against the ledger,
and immediately before each document asks Anthropic `/v1/messages/count_tokens` for the
exact strict-tool request context. It budgets the greater of count+1,024 tokens or
count+10%, adds the configured maximum output cost, and permits generation only when the
guarded projection fits inside the remaining owner run cap.

After generation, evidence is validated against the asserted synthetic PDF page and
`source_facts` plus `insights` are written in one canonical transaction. A failed write
rolls back and leaves the document pending for restart. The current backlog happens to be
198 documents; 198 is not a runtime invariant, scope ceiling, or activation requirement.

## Live schema evidence

Read-only inspection of the AACapitalPvtLtd Neon branch on 2026-08-09 verified
`source_facts` contains nullable `doc_id bigint` with a foreign key to `documents(id)`
`ON DELETE SET NULL`, and `confidence numeric NOT NULL DEFAULT 1.0` constrained to 0..1.
The existing unique index remains `(ipo_id, field, source, fetched_at)`, with a separate
index on `(ipo_id, field)`. No schema migration is part of R6.

## Activation gate

Every production generation path requires `SBI_SONNET_OWNER_APPROVED=YES` in addition to
the configured price card and run cap. Without that explicit owner gate the canonical
worker returns `OWNER_NOT_APPROVED` before token counting, generation, or canonical
writes. Injected offline model functions remain available for deterministic tests.
