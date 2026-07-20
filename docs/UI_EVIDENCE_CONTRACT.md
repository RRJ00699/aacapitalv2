Status: CURRENT
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21
Verified commit: PR #265 head

# UI EVIDENCE CONTRACT

What any AACapital surface may claim, and what it must render when it cannot.

## Hard rules (test-enforced)

1. **No research inference in the frontend.** The UI formats; it never
   invents promoter intent, growth conclusions, SBI recommendations,
   governance conclusions, or fair value from raw numbers.
   Enforced: `test_evidence_and_filters.py`, `test_phase6_insights_ui.py`,
   `test_phase8_uat_contracts.py`.
2. **RHP-derived claims** render only from `insights` rows (server-supplied,
   excerpt-bearing, `is_current`) or, transitionally, from `rhp_full` evidence
   fields — each with the "RHP · quoted" badge / quoted-words list
   (`components/ipo/IpoCard.tsx`). No insight & no evidence field ⇒ the
   claim does not exist.
3. **SBI claims** render only from a parsed note (`sbi_full`/`sbi_rating`).
   Absent ⇒ exactly: *"SBI research note not available or not yet parsed."*
   Never an invented recommendation. Footer: *their call, not ours*.
4. **OFS ladder** (structure category): insight-negative (quoted) →
   insight-non-negative (evidence read; silence — no negative, no pending
   line) → legacy `structure.ofs_heavy`+detail → gray PENDING lane:
   *"…offer for sale confirmed. Seller rationale and use-of-proceeds
   assessment pending RHP analysis."* Bare `ofs_pct` is a neutral fact.
5. **Strengths never sit under the negative heading** — the
   "…and in its favour" divider is mandatory.
6. **Structured/backtest lane** (P/E vs peer, D/E, ROE, growth, HOUSE
   STACK, gap buckets) may render from numbers directly — these are
   STRUCTURED/BACKTEST source types, with null-coded-zero protection
   (a missing number never manufactures a negative).
7. **Fair value**: inputs missing ⇒ *"Fair value unavailable — requires
   valid EPS and comparable peer valuation"*; MoS then reports unavailable,
   never a synthetic pass.
8. **Live readiness**: `research_ready===false` ⇒ amber RESEARCH INCOMPLETE
   chip naming `research_missing[]` (server-attested), and any go-signal is
   demoted to WATCH in copy.
9. **Provenance footer** states what was actually used ("From filings &
   issue data — RHP not yet read" vs "From the RHP + filings").

## State rendering

CONFIRMED ⇒ full claim + badge/quote · PARTIAL ⇒ artifact acknowledged,
claim withheld ("legacy/stale" for un-fingerprinted verdicts in audits) ·
PENDING ⇒ the exact pending sentence for that source · FAILED ⇒ visible in
Admin/StepBoard + ntfy, never rendered as a conclusion.

## Known transitional exception (recorded, not hidden)

Until the first post-merge fan-out run, `insights` is NULL and cards fall
back to `rhp_full` evidence fields (still evidence-gated, still quoted where
available). This fallback is deliberately preserved and test-pinned; it
retires naturally as fan-out backfills.
