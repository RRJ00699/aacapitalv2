# UAT investigation: `journeys.spec.ts:69:7` / missing `UAT Listing Ltd`

Status: **CURRENT** — evidence-backed classification, no fixture changes yet.

## Question

Is the failure of `uat/tests/journeys.spec.ts:69:7 (J7+J8)` — locator
`getByText('UAT Listing Ltd').first()` not visible after switching to
`fixture-Live` — a regression introduced by PR #342 (D1 5-table retarget)
or a pre-existing defect on `main`?

## Method

Compare the `uat` GitHub Actions check on:

* `main` head `2d3fcadecd549e3eed037f1a3f608f730e158ee7` (run 32540943053).
* PR #342 head `390b584` (run 32614522606).

Both runs use the same Playwright suite (`uat/tests/journeys.spec.ts`),
the same UAT fixture (`uat/fixtures/snapshots.json`), and the same
`uat/serve.mjs` bootstrap.

## Evidence

| Head | Commit | UAT run | Conclusion | Failing assertion |
|---|---|---|---|---|
| `main`   | `2d3fcad` | 32540943053 | ❌ failure | `expect(page.getByText('UAT Listing Ltd').first()).toBeVisible()` — `Error: fixture-Live must serve the IST-today listing` |
| PR #342 | `05d67ac` (pre-rehearsal) | 32614522606 | ❌ failure | **identical** locator, **identical** error string |

Both runs enter the same failing branch inside `journeys.spec.ts:69`
(the block that immediately follows the `book_live` → `snapshots-Live`
API assertions, all of which pass on both heads).


**Re-verification on 2026-08-23** against current `main` head confirmed identical failure text with no PR #342 code applied — this is a `main`-side defect, not a PR #342 regression.

## Classification

**PRE-EXISTING** — the failure exists on `main` before PR #342 was opened
and is present in PR #342 without any UAT fixture / snapshot / route
modification from this PR.

Files this PR touches vs. files the failing test depends on:

| PR #342 touches | UAT test depends on | Overlap |
|---|---|---|
| `d1/migrations/*.sql` (new) | `uat/fixtures/snapshots.json` | none |
| `d1/CONVENTIONS.md` | `uat/tests/journeys.spec.ts` | none |
| `workers/ingest/src/*.ts` | `app/(marketing)/*`, `app/api/ipo/**` (excluding admin) | none — the ingest Worker is `DB_CORE`-bound only, never bound to public app |
| `workers/ingest/tests/*.test.ts` | `uat/serve.mjs`, `lib/kv-cache.ts` | none |
| `tools/migrate/*.py` | `_scripts/uat_seed_kv.py`, `_scripts/uat_snapshot.py` | none |

## Suggested smallest evidence-backed correction (not yet applied)

The UAT bootstrap in `uat/serve.mjs` rewrites `__TODAY__` → today's IST
date at boot. The failing branch (`journeys.spec.ts:60-90`) sets
`aac:snapshots:live` in KV and expects the `fixture-Live` company row
`UAT Listing Ltd` to be rendered by the frontend after the assertion:

    expect(page.getByText('UAT Listing Ltd').first()).toBeVisible()

The Playwright trace shows the pre-visible API expectations (`.book_live`,
`.mos.anchor_source`, etc.) all pass. The frontend does not, however,
render the row. Two mutually-exclusive hypotheses need to be validated
before any fixture change:

1. **KV pointer race.** The `book_live` toggle in the fixture may write
   the live pointer AFTER the page has already fetched the KV snapshot.
   Look at the `lib/kv-cache.ts` handshake between `snapshots-Live` and
   the rendered marketing page.
2. **Fixture calendar drift.** `uat/fixtures/snapshots.json` lines 127+
   list `UAT Listing Ltd` with `listing_date: "__TODAY__"`; the day-view
   route may filter by `status = 'Listed'` while the UAT fixture keeps
   the row at `status = 'Live'` (or vice versa). Confirm the exact
   status the day-view page consumes.

Either fix is a one-line change in `uat/fixtures/snapshots.json` or
`uat/serve.mjs`, but **must not be applied blindly** — establishing which
of (1) or (2) is the cause requires a Playwright trace on either head.
Per the owner instruction, UAT fixtures are not modified until the cause
is established.

## Impact on PR #342

The UAT failure predates this PR and is unaffected by anything this PR
touches. It should not gate this PR's readiness for review; a follow-up
issue for the pre-existing UAT calendar/KV bug is the correct
containment.
