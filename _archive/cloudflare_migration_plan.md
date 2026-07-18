# AACapital → Cloudflare Migration Plan
_Researched 2026-07-14. All prices verified from Cloudflare docs, current as of July 2026._

## 🔴 THE KEY FINDING (read this first)

**Cloudflare does NOT host Postgres.** Their database (D1) is SQLite, with hard limits:
- 10 GB per database max
- ~50 writes/second (single-writer)
- NO stored procedures, NO jsonb, NO arrays, NO Postgres extensions (pgvector, etc.)

**Your app uses Postgres heavily** — jsonb columns (anchor_json, peer_json, full_json,
sub_scores), complex JOINs, 30+ tables, pgvector-style needs. Converting to SQLite/D1
would be a massive, risky rewrite of your entire data layer.

**THE RIGHT ANSWER: Keep Postgres on Neon. Connect via Cloudflare Hyperdrive.**
- Hyperdrive is Cloudflare's official way to connect Workers → external Postgres
- It pools connections + caches read queries at the edge (fixes the pg-on-edge problem)
- Neon is explicitly listed as a supported/recommended Hyperdrive partner
- You keep ALL your Postgres features, jsonb, JOINs — zero DB rewrite
- Your DB already IS on Neon (cloud), so it doesn't even move

So the migration is: **Vercel → Cloudflare Pages/Workers for the APP.**
Neon stays. That's a FAR smaller, safer migration than "move everything."

---

## 💰 COST COMPARISON

### CURRENT SETUP (monthly)
| Item | Cost |
|---|---|
| Vercel (Pro, if on it — or Free w/ rate limits) | $0–20 |
| Neon Postgres (your DB) | $0–19 (free tier or Launch) |
| Hetzner VM (4GB, cron jobs) | ~$5 (€4.51) |
| Domain (aacapitalprivatelimited.com) | ~$1/mo (~$12/yr) |
| Email (currently?) | ? |
| **TOTAL** | **~$6–45/mo** |

### CLOUDFLARE SETUP (monthly)
| Item | Cost | Notes |
|---|---|---|
| Workers Paid (app + APIs + cron) | **$5** | 10M requests + 30M CPU-ms included. You'll use a tiny fraction. |
| Hyperdrive (Postgres connection) | **$0** | Included in Workers Paid, no extra charge |
| Neon Postgres (unchanged) | $0–19 | STAYS where it is |
| Cron (Workers Cron Triggers) | **$0** | Replaces the Hetzner VM entirely |
| Cloudflare Pages (static/frontend) | **$0** | Unlimited static, no bandwidth charges |
| Email Routing → Gmail | **$0** | Free forever, incoming forward |
| Gmail "Send As" (outbound) | **$0** | Uses your existing Gmail SMTP |
| Domain (move to CF Registrar) | ~$1/mo | At-cost, no markup |
| Egress/bandwidth | **$0** | Cloudflare charges nothing for bandwidth (Vercel does) |
| **TOTAL** | **~$6–25/mo** |

### THE WINS
1. **DROP THE HETZNER VM (~$5/mo)** — cron moves to Workers Cron Triggers (free)
2. **NO deploy rate limits** — the exact wall that blocked you today. CF build limits
   are far more generous.
3. **NO egress fees** — Vercel charges for bandwidth; Cloudflare doesn't
4. **Everything in ONE dashboard** — app, cron, DNS, email, domain
5. **Free custom-domain email** → Gmail (you asked for this specifically)
6. **Flat $5 base** — predictable, vs Vercel's rate-limit-or-pay model

### THE HONEST COSTS / RISKS
1. **The app must be rewritten for Workers runtime** — this is the real work:
   - lib/db.ts uses `pg` (node TCP Pool) → must switch to Hyperdrive binding
     (some journey/live routes already use @neondatabase/serverless — good, those are ready)
   - fs/path file reads won't work on Workers (edge has no filesystem)
   - NextAuth v5-beta on Workers needs testing (auth is the riskiest piece)
   - 45 API routes must each be verified edge-compatible
2. **Next.js on Cloudflare** needs @opennextjs/cloudflare adapter (not just `next build`)
3. **128MB memory limit** on Workers — heavy JSON parsing could hit it (watch the big routes)
4. **Cron rewrite** — your 9 Python pipeline jobs currently run on the VM via Python.
   Workers run JS/TS, NOT Python. THIS IS THE BIG ONE:
   → Your pipeline is PYTHON (scrapers, Kite, scoring). Workers can't run Python directly.
   → OPTIONS: (a) keep pipeline on a tiny VM/container just for Python cron,
              (b) rewrite pipeline in JS (huge), or
              (c) use Cloudflare Containers/Queues to run Python (newer, more complex)
   → HONEST: the VM may need to STAY just for the Python pipeline, OR we containerize it.

---

## ⚠️ THE REAL DECISION

Two clean options:

**OPTION A — Full move (app + cron to CF, DB stays Neon):**
- App → Cloudflare Pages/Workers (via OpenNext adapter)
- DB → Neon (unchanged, via Hyperdrive)
- Cron → ??? (Python problem above — this is the blocker)
- Email → Cloudflare Routing + Gmail
- Kills Vercel + maybe kills VM

**OPTION B — App only (pragmatic):**
- App → Cloudflare (kills Vercel + the rate limits)
- DB → Neon (unchanged)
- Cron → KEEP the Hetzner VM (it works, it's $5, Python runs fine)
- Email → Cloudflare + Gmail
- Simpler, lower-risk, still solves the deploy-limit pain

**MY HONEST RECOMMENDATION: Option B first.**
The deploy rate limit is your actual pain. Moving the APP off Vercel solves it.
The VM cron works fine and Python-on-Workers is a genuine hurdle not worth fighting now.
Do the app migration, prove it, THEN decide if the VM is worth eliminating later.
"Drop existing infra after thorough regression testing" — exactly right, and Option B
lets us regression-test the app move without also risking the pipeline.

---

## 📋 TOMORROW'S PLAN (Option B — app migration)

### Phase 0 — Prep (no changes, ~30 min)
- [ ] Inventory all 45 API routes: which use `pg` Pool vs @neondatabase/serverless vs fs/path
- [ ] List routes that read files (fs) — these need rework for edge
- [ ] Confirm Neon connection string + set up Hyperdrive binding
- [ ] Install @opennextjs/cloudflare adapter locally, test build

### Phase 1 — Parallel deploy (Vercel STAYS live)
- [ ] Set up Cloudflare Pages project pointing at the same GitHub repo
- [ ] Configure Hyperdrive → Neon
- [ ] Convert lib/db.ts: pg Pool → Hyperdrive/@neondatabase/serverless
- [ ] Fix any fs/path reads (move data to DB or bundle)
- [ ] Deploy to a CF preview URL — DON'T touch the domain yet

### Phase 2 — Regression test (both live)
- [ ] Test every screen on the CF preview URL vs Vercel
- [ ] Test auth (NextAuth) thoroughly — the riskiest piece
- [ ] Test all API routes return identical data
- [ ] Test the journey page live-price + cron-fed data

### Phase 3 — Cutover (only after tests pass)
- [ ] Point aacapitalprivatelimited.com DNS → Cloudflare
- [ ] Set up Email Routing → Gmail + Gmail Send-As
- [ ] Monitor 24–48h with Vercel still as fallback
- [ ] Only after proven: decommission Vercel

### Phase 4 — Later (separate decision)
- [ ] Evaluate moving Python cron off the VM (Containers/Queues) — or keep VM

---

## EMAIL SETUP (you asked — it's free + easy)
1. Domain DNS on Cloudflare (part of the migration anyway)
2. Cloudflare dash → Email → Email Routing → add rakesh@aacapitalprivatelimited.com
   → forward to your Gmail. Free. CF auto-adds MX/SPF/DKIM records.
3. To SEND as your domain: Gmail → Settings → Accounts → "Send mail as" →
   add the address, use Gmail SMTP (needs 2FA + App Password). Free.
4. Result: receive + send from rakesh@aacapitalprivatelimited.com, all in your Gmail. $0.
