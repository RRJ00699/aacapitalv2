Status: CURRENT

# AACapital — UI Requirements & Current Structure (FINAL)

**Purpose:** the single authoritative record of the frontend — design system, every
screen's structure, every data binding, and the process rules that keep UI PRs safe.
Companion to docs/specifications/IPO_BUSINESS_REQUIREMENTS.md (the rating spec). Built from the shipped
code (UI PRs #139–#145 + recovery), not memory. Read this before changing any screen.

Owner: Jammula Rakesh Reddy · US-CST · listings IST · primary device: iPhone PWA (~380px).
UI lane: frontend/visual only. Data bugs are FLAGGED in PR bodies, never fixed in UI PRs.

---

## 1. THE BAR

"A product he'd pay for, not a tool he built." Mobile-first at 380px before desktop.
Decision-first: the verdict and the one number that matters jump out; secondary data
recedes. Calm, premium, institutional. Three clean surfaces: **Command = decisions ·
Calc = calculations · Live = trading.**

## 2. DESIGN SYSTEM (LOCKED)

### Type roles (globals.css --f-* vars; fonts loaded in AppShell)
- `--f-display` **Sora** — company names, H1s, section titles, decision pills, CTA
- `--f-mono` **IBM Plex Mono** (tabular-nums) — EVERY numeral, table headers, timestamps
- `--f-body` **DM Sans** — everything else

### Theme (globals.css --t-* vars; light cream / dark navy; OS-auto + manual)
- Light: bg #F4F1EB · surface #FAF8F4 · header #E9E2D8 · gold #B8860B
- Dark: bg #0F172A · surface #1B2432 · header #111827 · gold #D4AF37
- **RULE: no hardcoded surface/text hex in components — --t-* vars only.**
  (Settings/access/admin were hardcoded-light and broke dark mode; fixed PR #141.)
  Exception: the admin log terminal is intentionally dark in both themes.

### Color roles (meaning, not decoration)
green/red = direction/outcome only · gold = brand + active state · blue = info/links
only · amber = caution/watch. No emoji on product surfaces — typographic marks
(✓ ✕ ◆ ⚑ ●) only. The lion emblem is brand, not decoration — it stays.

### Motion (one ease: --ease cubic-bezier(.2,.7,.3,1))
Dial sweep .6s · verdict/gain color .25–.3s · `.livedot` pulse 1.6s (the live
heartbeat) · countdown turns red inside 15 min · prefers-reduced-motion kills all.

### Signature — DESIGNED ABSENCE
Missing data is never a bare dash. Every empty state is a dashed, labeled "awaiting"
token that names WHAT fills it and WHEN: "awaiting peer P/E", "fills at listing",
"depth flows during pre-open", "endpoint pending". Honest-signal ethos made visual.

### PWA chrome
manifest.json: light theme (#F4F1EB bg / #E9E2D8 theme), cream icon set in
public/icons (lion on cream, maskable 62% safe-zone). Nav: aa-logo-full.png,
flexShrink:0; search flex:0 1 300px minWidth:110; tagline shrinks (never hides) on
mobile. Footer: aa-logo-full.png at 132px.

## 3. SCREEN INVENTORY & STRUCTURE

### /dashboard/ipo2 (THE app) — tabs: Live · Command · Calculator · Playbook · Open Now · Upcoming · Post-Listing · BRLM
- **Live (trading)** — 7-day window (listing_date within 7d). Multi-listing selector
  pills (livedot on capturing sym) switch per-IPO stacks. Per IPO:
  LiveDecisionPanel (countdown hero to deadline_ist/10:14 IST · eval cadence line ·
  confidence hero colored ≥65/40/40− · RuleCard ×2 static/live with ✓✕+win% ·
  MosTile sentence + anchor_source + GMP-note in amber · book tile with lean% ·
  volume tile [endpoint pending]) → .live-split: left live panel (ticks/OBIR/levels
  or "feed idle" card) · right HoldStrip (HOLD/EXIT NOW pill, gain, armed state,
  entry/floor/trail/peak, auto-expanded journey chart with floor/trail dashes).
  Auto-selects on load during IST market hours when ticks flow.
- **Command (decisions)** — status line · engine strip (spec §2A bands verbatim) ·
  verdict filter pills (All/TRADE/WATCH/CAUTION/AVOID) · IpoCard list.
- **Calculator** — share sizer, return calc, target ladder (10:14 window copy).
- **Playbook / Open Now / Upcoming / Post-Listing / BRLM** — Open Now carries the
  full pre-listing panel (GmpLine, FairValueCard, WeakOpenFlag, Reasons,
  StreetConsensus, TrustReport); Upcoming has GMP d-1 + Anchors columns; Post has
  the Call ✓hit/✕miss column + accuracy roll-up; BRLM sign-colored.

### IpoCard (components/ipo/IpoCard.tsx) — the decision unit, top→bottom:
hero (name Sora clamp / state / ★ quality promoter / verdict pill + hint / score
dial rounded-int + conf) → SETUP line (playbook ◆◆STACK/◆CORE/✕SKIP) → metrics
(FV gold-bordered or awaiting-with-reason · price · size) → GMP strip (day-before
% + band chip + lo–hi bar + locked hint) → Edge grid (anchors/OFS/PE-vs-peer/QIB/
band, locked-threshold colors, dashed awaiting) → House Rules pills (pg-array-literal
parser; max 3 + "+N") → Street/AACapital/RHP footer → gold CTA + lock8/trail12 line
→ expand: RHP trust, governance flag chips (reads full_json.db_fields; string flags
watch/weak/rising), top-3 risks, dd note, AI read.

### /dashboard/journey — deep-dive hold screen: Sora sym, 26px mono live price,
livedot, EXIT NOW filled pill, chart red-on-exit, lock-in bar, "Awaiting candles" state.

### Long tail — settings/access (theme-vars, mono secret inputs) · admin console
(theme-vars, dark terminal, typographic job marks) · tracker (own calm palette,
Sora title, lion stays) · **legacy /dashboard/ipo = FROZEN rollback surface, never restyle.**

## 4. DATA CONTRACTS (bind ONLY these; new field = ask backend first)

- **GET /api/ipo-command** → { cards[], live[], levels[], blocks[], post[], brlm[],
  dl[], track[] } (leaderboard retired). Card fields as consumed by IpoCard —
  see route.ts; every UI field must exist in the payload.
- **GET /api/ipo/journey?sym=** → { ok, hasData, entry, peak, low, live, liveSource,
  armed, floorLevel, trailLevel, gainNow, offPeak, daysHeld, lockinDaysLeft,
  decision, reason, series[] }. HoldStrip + journey page. Poll 60s, IST-market-gated.
- **GET /api/ipo/live-preopen** → { ok, book_live, listings: [{ sym, company_name,
  rules_static[]/rules_live[] {name, passed t/f/null, win, detail}, mos {pct,
  cushion_rupees, fair_anchor, anchor_source, gmp_ref, note}, open_pct, book
  {discoveryPrice, buyQty, sellQty, leanPct} | null, rules_passed, rules_total,
  confidence, deadline_ist, last_eval_ist }] }. Poll 60s gated 8:55–10:20 IST.
  NOT served yet: cum_volume_1029_1100 (tile awaiting, "endpoint pending").
- Locked numbers on screens come from docs/specifications/IPO_BUSINESS_REQUIREMENTS.md or an
  owner-executed clean run (e.g. GMP hint +54.5% recomputed 2026-07-15). NEVER
  hardcode a different figure; UI PRs NEVER touch app/api/ipo-command/route.ts.

## 5. PROCESS RULES (every UI PR — no exceptions)

1. **ONE COMMIT PER PR.** Rakesh merges from phone immediately after review;
   appended commits get stranded (happened twice: #143, #145). New scope = new PR.
2. **Gates before PR:** strict tsc (multi-file project w/ stubs) · esbuild bundle ·
   **duplicate-style-key detector** (born from the #144 build break) ·
   **binding diff** (no payload fields dropped; new fields verified against the
   route SOURCE CODE, not prose) · **locked-number grep** (54.5/50.9/+9.4/"100% win"
   must be 0 in changed files).
3. **Post-merge verification** after every merge: hash-compare local finals vs main
   + content probes. It caught both stranded commits.
4. PR body always carries: what changed, the confirmations above, any DATA-BUG FLAG
   for the backend lane (flag, don't fix), and phone-check instructions (@380px,
   dark mode when relevant).
5. Deliver via GitHub API to claude/* branches; PAT rotates at workstream end.

## 6. LOCKED vs OPEN

**LOCKED:** the design system (§2) · designed-absence doctrine · three-surface
structure · frozen legacy /ipo · no-emoji rule · --t-* only · one-commit-per-PR.
**OPEN / nice-to-haves:** skeleton loaders beyond shimmer rows · swipe-between-tabs ·
volume-confirm bind (needs backend field) · modeled-FV anchor upgrade (backend:
eps_post fix) · icon art refresh if Rakesh wants a designed mark instead of the
padded emblem.
