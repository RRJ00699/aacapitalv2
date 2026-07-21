Status: CURRENT
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21

# UAT TRACKER — the single place findings live (no more zombies)

Every UAT finding gets a row here WITH its guard test once fixed. A bug
without a pinned test is allowed to come back; a bug with one is not —
that's been the whole pattern of this codebase's regressions.

| # | Finding (owner, SBIFUNDS listing 2026-07-21) | Status | Root cause / next evidence | Guard |
|---|---|---|---|---|
| U1 | Confidence 84 with 4/9 beat by 89 with 2/9 | FIXED this branch | avg-of-passed only; coverage never entered. Now avg × (0.5 + 0.5·passed/scoreable) | test_ux_uat: ordering test |
| U2 | MoS waits for open; should track IEP live pre-open, then listing price | OPEN (design) | pre-open book already captures IEP (₹613.3 shown) — plumb it as a LABELED provisional anchor (`iep-provisional`), never persisted as fair value; swap to real open when it prints | pending impl |
| U3 | Domestic market zeros (FII/DII +0) + stale index values | OPEN (data) | market/global feed source stale; FII/DII scraper returns 0. Owner asks Zerodha as live source — needs a source decision (Kite quote API costs nothing extra for indices). Add advances/declines | pending impl |
| U4 | Global markets absurd percents (^NDX −479.92%) | FIXED this branch (display) | change-in-POINTS rendered with a % suffix in the global list | test_ux_uat: no %-suffix on point changes |
| U5 | In-app (mobile shell) search untappable | FIXED this branch | 64px single-row app bar crushed the input; wraps to 2 rows on ≤640px, 44px target, 16px font (no iOS zoom) | test_ux_uat: appbar css |
| U6 | Upcoming screen still shows SBIFUNDS after listing | FIXED this branch | state flips only at next pipeline run; view now drops rows with listing_date < IST-today | test_ux_uat: filter code pinned |
| U7 | SME / <₹200cr names appearing in Open Now + Command | FIXED this branch (REIT/InvIT instrument guard; sub-200 rows were already feed-excluded) | the ONE eligibility rule is in every feed (test-pinned) — so these rows have is_sme NULL/false AND size NULL/≥200 in the DB. Evidence needed: `SELECT company_name, is_sme, issue_size_cr FROM ipo_consolidated WHERE company_name ILIKE '%<offender>%'` — then fix the SCRAPER's SME flagging, not the feeds | eligibility tests exist |
| U8 | VOLUME CONFIRM still awaiting on listing day | FIXED this branch (launcher unions consolidated strong key; intelligence symbols were blank on listing morning) | cache is fine (awaiting=60s). Zero ticks captured again. Evidence: `grep -E "resolved|could not" /root/aac/logs/ticks.log \| tail -5` + `SELECT count(*) FROM ipo_tick_feed WHERE recorded_at::date=CURRENT_DATE` — tells us launcher-timing vs Sync-timing vs a third cause | ticker strong-key test exists |
| U9 | Journey/EXIT ENGINE empty right after listing | PARTIAL by design | daily candles land at the 17:00 pipeline; journey genuinely starts at D1 close. Improvement: show listing-day live ticks in the journey pane same-day | pending impl |
| F1 | Command Center fundamentals card (ROE, ROCE, P/E, Chittorgarh-style) | OPEN (feature) | ROE/PE/D-E in DB today; ROCE not captured — scraper/IPOMatrix field needed first | — |
| D1 | Complete Details view v1 shipped (payload-complete, honest gaps) | DONE this branch | see docs/DETAILS_AND_REVIEW.md matrix | J11/J12 + test_listing_review |
| D2 | Listing Review view UI (derivations shipped in lib; UI next slice) | OPEN (next) | reviewState/observations pure + tested | executed tests exist |
| D3 | Street news: table+discovery+manual override+Command/Live/Details surfacing | DONE this branch | Reuters preferred; linked never scraped; VM runtime pending first pipeline run | test_news_module_contracts |
| F2 | Listing circuit band (5/10/20%) on Live + Journey at ~09:55 | OPEN (feature) | NSE publishes the band pre-open; needs a capture source (nse_preopen_capture likely sees it) | — |
