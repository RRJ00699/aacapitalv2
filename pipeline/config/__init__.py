"""Shared pipeline limits with explicit operational reasons."""
# Minimum positive operator-supplied count/retry values to avoid no-op worker settings.
MIN_POSITIVE_LIMIT = 1
# Owner default: real listing-day sessions usually have only a few IPOs, keeps Kite calls bounded.
PREOPEN_DEFAULT_IPOS = 5
# Hard guardrail: prevents an accidental broad listing capture from consuming Kite/API budget.
PREOPEN_HARD_MAX_IPOS = 15
# Owner default: bounded transient retry budget for broker hiccups.
PREOPEN_DEFAULT_RETRIES = 2
# Hard guardrail: avoids long capture loops inside the listing window.
PREOPEN_HARD_MAX_RETRIES = 3
# Weekday guard: exchanges are normally open Monday-Friday; holidays still fast-exit via no listings.
WEEKDAY_MAX_INDEX = 4
# IST capture start: 08:55, just before normal listing discovery.
PREOPEN_START_MINUTE_IST = 8 * 60 + 55
# IST capture end: 10:05, covers the pre-open/listing discovery period without all-day polling.
PREOPEN_END_MINUTE_IST = 10 * 60 + 5
# Owner default: enough for normal active IPO coverage without full-history scans.
SNAPSHOT_DEFAULT_IPOS = 25
# Owner default: balances Neon pressure and runner throughput for per-IPO Journey reads.
SNAPSHOT_DEFAULT_CONCURRENCY = 4
