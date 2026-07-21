Status: CURRENT
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21

# UAT FRAMEWORK — `npm run uat:all`

One command runs, in order: typecheck → production build → the full Python
suite (incl. real-Postgres API contract tests) → Playwright browser journeys
on desktop/tablet/mobile → axe accessibility → (opt-in) visual regression.
CI runs it on every PR and blocks merge; failures upload uat-report/ (HTML
report, traces, videos, screenshots, console+network logs, exact assertion).

## Determinism: zero Neon, zero paid APIs
`uat/serve.mjs` boots the PRODUCTION build with UAT_FIXTURE_JSON pointing at
uat/fixtures/seed.json — every SQL query answers from the seed (substring →
rows in lib/db; fixtureAwareNeon covers routes with private clients). The
same env opens the API auth gate — guard-tested to be impossible without
fixture mode, which also replaces the DB, so it can never expose real data.
__TODAY__ in the seed becomes the real IST date at boot so LISTING journeys
work any day. DATABASE_URL points at .invalid; Kite/LLM never touched.

## Journeys → fixtures
| J | Journey | Fixture target |
|---|---|---|
| 1/4 | Search → stage-aware action → navigate | UATGOOD (UPCOMING, complete) |
| 2 | Quality + lifecycle filters combine | all four cards |
| 3 | Incomplete never surfaces as GOOD | UATINC (no RHP/SBI ⇒ no verdict field) |
| 5 | Research states, FV, quoted evidence | UATGOOD (insights w/ excerpt) vs UATINC |
| 6 | Raw OFS stays neutral | UATINC (ofs 100%, no evidence ⇒ pending lane) |
| 7/8 | Live blocks incomplete; floor ⇒ no MoS | UATLIVE (lists __TODAY__, peerPE null) |
| 9 | Post-listing outcomes | UATPOST (INWINDOW, gap 4.2%) |
| 10 | Rules disclose n= + win% | grade panel (full table/date/version = tracker F3) |
| — | Auto-fail: console errors, exceptions, 5xx, overflow | every test (uat/tests/_base.ts) |

## Commands
- `npm run uat:all` — the PR gate (fixture-served)
- `npm run uat:smoke -- --base-url=https://…` — post-deploy, READ-ONLY
- Visual baselines: `UAT_VISUAL=1 npx playwright test uat/tests/visual --update-snapshots`, commit; PRs then fail on >2% drift

## CI round-2 fixes (2026-07-22, from the first real Actions run)
- All journeys had landed on /login: the PAGE gate (app/dashboard/layout.tsx)
  redirected logged-out visitors; only the API gate was fixture-aware. Both
  now open under UAT_FIXTURE_JSON (which also replaces the DB — guard-tested).
- tablet/mobile died on missing webkit: device profiles default to webkit but
  CI installs chromium only. Every project pins browserName chromium.
- Reporter clash: artifacts moved to sibling uat-results/ (CI uploads both).
- The color-contrast a11y finding was measured on the LOGIN page; the gate
  stays strict — the next run scores the real dashboard.

## Environment honesty
The dev sandbox has no browser binary (Playwright CDN off-network) — browser
execution is CI-verified. Everything below the browser was proven here by
direct HTTP against the production build: all four lifecycle cards served,
INCOMPLETE carries no verdict, GOOD requires CONFIRMED, Live attests
ready=false / mos.pct=null / issue-price-floor (transcript 2026-07-21).
