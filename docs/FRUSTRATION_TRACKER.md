Status: CURRENT — owner-visible accountability log (Admin console renders it)

# Frustration Tracker

Redundant work, wrong claims, and avoidable churn — logged by date, owned
by whoever caused it. The Admin console shows the latest entries.

## 2026-07-22 (Wednesday)
- **Assistant claimed "today is Saturday" on a Wednesday** and explained the
  missing 17:00 ntfy ping with a fabricated weekday theory. The assistant's
  internal session dates had drifted (07-23→"07-25") and were trusted over
  the calendar. Consequence: the real 17:00-cron miss is still undiagnosed.
  Rule going forward: dates come from `date` on the machine, never from
  narrative memory.
- **smoke `ipo_research_notes.company_name` fix delayed** — flagged by the
  owner, fixed a cycle later (alias `nw` + parser regression test now in
  the golden-week branch). Flags get fixed in the same cycle.
- **Patch/branch drift caused a failed `git am` + a repeat crash** — the
  owner's branch already held commits 1–5; the cumulative 6-commit patch
  conflicted, and the missing commit 6 was exactly the crash fix. Patches
  now state their base explicitly; cumulative patches only onto clean main.
- **Local consolidate crashed with UndefinedColumn** — the miner assumed
  Schema sync had run. Jobs must introspect and degrade, never traceback
  (fixed: golden columns introspected, skips printed).
