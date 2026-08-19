# Pipeline defect closeout — decisions

Status: decisions record — the choices behind the D1-D7 closeout, kept so they are
not re-derived or silently reversed.

Scope: `pipeline/**`, `_scripts/**` and their tests. One PR, one commit per defect.
Recorded here are only the choices a future reader would otherwise have to re-derive.

## D1 — where the security kind lives

`CANONICAL_UNIVERSE_SQL` needs a structured security-kind term, and the previous attempt
(534d3ae) put it on `ipo_issue.issue_type`. That was reverted in 89d79b5 because the
column is not on the canonical schema, which left the cohort with no kind term at all —
and id 11, Cube Highways Trust, is an InvIT carrying `is_mainboard=TRUE`, so it entered
every lane.

The kind is now a **`source_facts` row under the reserved field `security_kind`**.

- `source_facts` is written by `fill_ipo` on every upsert and is named by the V2 docs as
  the home for provenance-bearing scalar facts, so the predicate cannot fail on a
  missing column — the failure mode that caused the revert.
- The predicate is a `NOT EXISTS`, so all five consumers get it without joining anything.
- Any REIT/INVIT evidence excludes, even if a later fact disagrees. For a cohort whose
  members receive paid attention, the conservative direction is out.

**Names are never classification.** The kind is derived from NSE's own `series` code
(`IV`→INVIT, `RR`→REIT, `EQ`/`BE`/`BZ`/`BL`→EQUITY). An unrecognised series classifies
nothing: defaulting an unknown to EQUITY is precisely how a non-equity security gets in.

Rows that already exist are classified by a third bounded cohort in
`nse_identity_backfill` with its own budget (`--kind-limit`). Identity backfill only ever
looked at rows missing an ISIN or a listing date; id 11 has both, so nothing ever asked
NSE what it was.

## D3 — what the completeness percentage measures

`completeness_pct` measures **what is DUE**: `present / (present + missing)`. Not-yet-due
requirements are reported separately as `required_pending` and are excluded from both
sides of the ratio.

The alternative — counting pending in the denominator — is what made ids 1099/1100 fall
from 60.0% to 54.5% on 08-16 while gaining three facts and losing none. It also let an
IPO be `complete: true` and `0.0%` at the same time, because `complete` already ignores
pending. One of those two definitions had to move; the one that disagreed with the flag
is the one that moved.

This is **not** manufactured monotonicity. A requirement that is genuinely obtainable and
absent stays in `missing`, in the denominator, and in its retry lane.

## D5 — the snapshot step's exit code

Publication happens inside the builder. Everything after it — decoding the builder's
stream, parsing the publication record, proving the active pointer — is the wrapper's
own work, and a wrapper defect there was failing runs whose publication had fully
succeeded. The ledger now records the phase and the count of snapshots that actually went
live **before** the proof runs, and `last_known_good_kv_remains_active` is derived rather
than hardcoded, so neither the ledger nor the ntfy body can claim the old KV is still
serving once new keys are live.

## D6 — two rule layers, and why CANONICAL is empty

`CANONICAL` holds house rules the owner has ratified. It is **empty**, and that is the
honest state: no rule has been ratified against V2 evidence. Every mined rule is labelled
`DISCOVERY` in its own row, so nothing in the table can be read as a house rule.

A rule whose inputs are absent writes `NOT_EVALUABLE` and names the absent input. It is
never omitted — a rule that produced no row would be indistinguishable from a rule nobody
wrote — and never a false pass. `MIN_COHORT` applies the same discipline to sample size:
too few rows is reported, not rounded up into an edge.

Adding a rule is one `Rule(...)` in the registry. No rule gets its own code path, so no
rule can acquire its own private definition of "pass".

The V1 producer stays quarantined rather than being promoted: it reads `ipo_gold` (a view
over two V1 tables) and gates eligibility on `company_name !~* '\y(REIT|InvIT)\y'` — the
name-matching this repository refuses, and the exact defect D1 exists to close.

## D7 — the rating-evidence validator is unresolved

The 15-word ceiling no longer applies to resolved excerpts (see the commit). The separate
`'rating evidence must explicitly state the rating'` drop from the same 08-19 pilot was
**not** changed: it is a content check on the resolved bytes, not a wording ceiling, and
the brief is to verify it against the real note first. That note is not in the
repository. Decide it with the note in hand.
