#!/usr/bin/env python3
"""_scripts/vm_verify.py — ONE command that verifies AACapital REALITY on the VM.

    cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/vm_verify.py

Principles (owner directive 2026-07-21):
  * Verify reality, not configuration. A step that has never run is
    NOT VERIFIED — never reported as success.
  * Five separate evidence columns per stage:
      CODE (file exists) · CRON (scheduled) · RUN (runtime executed) ·
      DB (database updated) · UI (served payload shows current data)
  * Completeness matrix for the two PRODUCTION-DISCOVERED upcoming IPOs
    (selected by query, never by hard-coded name), states:
      CONFIRMED / PARTIAL / PENDING / FAILED / NOT VERIFIED
  * Every cron entry shown in VM-local, IST and US-Central (DST-aware).
  * Exit code: 1 if any CRITICAL stage is FAILED —
      RHP download · RHP parse/Sonnet · score generation · cron execution.
    PENDING (source not yet published) is NOT a failure.

Read-only: SELECTs only. The single optional write path is the sanctioned
ipo-command ?warm=1 KV rebuild (used to capture the exact payload the UI
renders); skipped unless ADMIN_JOB_KEY + NEXT_PUBLIC_APP_URL are present.
Output: markdown to stdout — paste the whole thing back to the session.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── tiny helpers ────────────────────────────────────────────────────────────
def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(command failed: {e})"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def db():
    import psycopg2
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        return None
    try:
        return psycopg2.connect(url, connect_timeout=15)
    except Exception:
        return None


def q(conn, sql: str, args=()) -> list | None:
    """SELECT-only helper: list of rows, [] for none, None for NOT VERIFIED
    (no conn / table missing / error). Never raises."""
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    except Exception:
        conn.rollback()
        return None


# ── timezone rendering (owner=US Central, market=IST, VM=whatever it is) ───
def tz_triple(hh: int, mm: int) -> str:
    """Render an IST wall-clock time in IST + US Central for TODAY (DST-aware)."""
    try:
        from zoneinfo import ZoneInfo
        ist = ZoneInfo("Asia/Kolkata"); chi = ZoneInfo("America/Chicago")
        today = dt.datetime.now(ist).date()
        t = dt.datetime(today.year, today.month, today.day, hh, mm, tzinfo=ist)
        c = t.astimezone(chi)
        day = "" if c.date() == today else f" ({c.strftime('%a')})"
        return f"{hh:02d}:{mm:02d} IST · {c.strftime('%H:%M')} US-Central{day}"
    except Exception:
        return f"{hh:02d}:{mm:02d} IST · US-Central: tzdata unavailable"


CRON_RE = re.compile(r"^(\d{1,2})\s+(\d{1,2})\s+\S+\s+\S+\s+\S+\s+(.*)$")


def cron_section(out: list[str]) -> tuple[bool, str]:
    """Returns (vm_tz_is_ist, crontab_text)."""
    tzline = sh("timedatectl 2>/dev/null | grep 'Time zone' || cat /etc/timezone 2>/dev/null")
    is_ist = "Kolkata" in tzline or "IST" in tzline
    out.append("## 1 · VM clock & cron (VM-local · IST · US-Central)\n")
    out.append(f"- VM timezone line: `{tzline or 'NOT VERIFIED'}` → "
               + ("**IST confirmed — cron comments are truthful**" if is_ist
                  else "**⚠ NOT IST — every cron comment below is mislabeled; fix TZ or re-time the crontab**"))
    cron = sh("crontab -l")
    if not cron:
        out.append("- `crontab -l`: **NOT VERIFIED** (empty or unreadable)")
        return is_ist, ""
    out.append("\n| min hr | wall clock (IST · Central) | command (short) |")
    out.append("|---|---|---|")
    for line in cron.splitlines():
        m = CRON_RE.match(line.strip())
        if not m:
            continue
        mm_, hh_, cmd = m.groups()
        try:
            trip = tz_triple(int(hh_), int(mm_)) if is_ist else f"{hh_}:{mm_} VM-local (TZ≠IST!)"
        except ValueError:
            trip = f"{hh_} {mm_} (every-minute / range)"
        short = re.sub(r".*venv/bin/python\s+", "", cmd)[:70]
        out.append(f"| {mm_} {hh_} | {trip} | `{short}` |")
    return is_ist, cron


# ── state model ─────────────────────────────────────────────────────────────
CONF, PART, PEND, FAIL, NV = "CONFIRMED", "PARTIAL", "PENDING", "FAILED", "NOT VERIFIED"


def slugify(name: str) -> str:
    s = re.sub(r"\b(ltd|limited|pvt|private)\b", "", (name or "").lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def main() -> int:
    out: list[str] = []
    now_ist = sh("date")
    out.append(f"# AACapital VM verification — {now_ist}\n")
    out.append(f"- Working dir: `{REPO}` · commit: `{sh(f'cd {REPO} && git log -1 --format=%h·%ad·%s --date=short')}`")
    out.append(f"- origin/main: `{sh(f'cd {REPO} && git fetch -q origin 2>/dev/null; git log -1 --format=%h origin/main')}`"
               " — if these differ, the VM runs OLD code until the next pipeline self-update (08:30/17:00 IST).")

    is_ist, cron = cron_section(out)

    conn = db()
    out.append("\n## 2 · Runtime reality (never 'success' without evidence)\n")
    if conn is None:
        out.append("- DATABASE_URL missing/unreachable → every DB column below is **NOT VERIFIED**")

    # cron execution reality: pipeline_steps within 36h
    steps = q(conn, """SELECT step, ok, ran_at FROM pipeline_steps
                       WHERE ran_at > NOW() - interval '36 hours'
                       ORDER BY ran_at DESC LIMIT 200""")
    fails = q(conn, """SELECT step, script, failed_at, LEFT(stderr_tail,120)
                       FROM pipeline_failures
                       WHERE failed_at > NOW() - interval '7 days'
                       ORDER BY failed_at DESC LIMIT 20""")
    cron_exec = NV
    if steps is not None:
        cron_exec = CONF if steps else FAIL  # scheduled but no run in 36h = broken cron
    out.append(f"- **Cron execution (pipeline ran <36h)**: {cron_exec}"
               + (f" — {len(steps)} step rows, latest `{steps[0][0]}` at {steps[0][2]}" if steps else ""))
    if steps:
        bad = [s for s in steps if s[1] is False]
        out.append(f"- Step outcomes last 36h: {len(steps)-len(bad)} ok · {len(bad)} failed"
                   + (f" → failed: {sorted({b[0] for b in bad})}" if bad else ""))
    if fails is None:
        out.append("- pipeline_failures (7d): NOT VERIFIED")
    elif fails:
        out.append(f"- pipeline_failures (7d): **{len(fails)}** — " +
                   "; ".join(f"`{f[0]}` {f[2]:%m-%d %H:%M}" for f in fails[:6]))
    else:
        out.append("- pipeline_failures (7d): none recorded")

    # log freshness (runtime evidence independent of DB)
    out.append("\n| log | mtime | age verdict |")
    out.append("|---|---|---|")
    for lg in ("pipeline.log", "token.log", "scrape_am.log", "watchdog.log", "jobs.log", "ticks.log"):
        p = os.path.join(REPO, "logs", lg)
        if os.path.exists(p):
            age_h = (dt.datetime.now().timestamp() - os.path.getmtime(p)) / 3600
            verdict = "fresh" if age_h < 26 else "**stale >26h**"
            out.append(f"| {lg} | {dt.datetime.fromtimestamp(os.path.getmtime(p)):%m-%d %H:%M} | {verdict} |")
        else:
            out.append(f"| {lg} | — | NOT VERIFIED (absent) |")

    # ── the two production-discovered upcoming IPOs ─────────────────────────
    out.append("\n## 3 · Per-IPO completeness — two upcoming, production-discovered\n")
    upcoming = q(conn, """
        SELECT company_name, COALESCE(nse_symbol, symbol), isin,
               open_date, close_date, listing_date,
               price_band_low, price_band_high, issue_size_cr,
               fresh_issue_cr, ofs_cr, anchor_count, ipo_pe, peer_median_pe,
               eps_post, roe, ipo_score, score_band, quality_score, is_sme
        FROM ipo_intelligence
        WHERE COALESCE(listing_date, close_date, open_date) >= CURRENT_DATE
          AND COALESCE(is_sme, false) = false
        ORDER BY COALESCE(open_date, close_date, listing_date) ASC
        LIMIT 2""")
    crit_fail: list[str] = []
    if upcoming is None:
        out.append("**NOT VERIFIED** — discovery query unavailable (no DB).")
    elif not upcoming:
        out.append("**PENDING** — production discovery returns zero upcoming mainboard IPOs today.")
    for row in (upcoming or []):
        (name, sym, isin, od, cd, ld, plo, phi, size, fresh, ofs, anc,
         pe, ppe, eps, roe, score, band, qs, _sme) = row
        out.append(f"\n### {name} ({sym or 'symbol PENDING'})")
        slug = slugify(name)
        rhp_pdf = os.path.join(REPO, "rhps", slug, "rhp.pdf")
        rhp_dl = CONF if os.path.exists(rhp_pdf) else PEND
        rhp_dl_note = f"`{rhp_pdf}` sha256:{sha256(rhp_pdf)}" if rhp_dl == CONF else "no local PDF"
        summ = os.path.join(REPO, "rhp_summaries", f"{slug}_summary.json")
        sonnet_row = q(conn, "SELECT verdict, full_json IS NOT NULL FROM ipo_rhp_intel WHERE regexp_replace(lower(company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')=regexp_replace(lower(%s),'(ltd|limited|and|&)|[^a-z0-9]','','g') LIMIT 1", (name,))
        sonnet = NV if sonnet_row is None else (CONF if sonnet_row and sonnet_row[0][0] else
                 (PART if os.path.exists(summ) else (PART if rhp_dl == CONF else PEND)))
        sbi_rows = q(conn, "SELECT rating, full_json IS NOT NULL FROM ipo_research_notes WHERE source='SBI' AND (UPPER(nse_symbol)=UPPER(%s) OR regexp_replace(lower(company),'(ltd|limited|and|&)|[^a-z0-9]','','g')=regexp_replace(lower(%s),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1", (sym or "", name))
        sbi_pdf = any(slugify(f).startswith(slug.split("-")[0]) for f in os.listdir(os.path.join(REPO, "data", "research_notes")) ) if os.path.isdir(os.path.join(REPO, "data", "research_notes")) else False
        sbi = NV if sbi_rows is None else (CONF if sbi_rows else (PART if sbi_pdf else PEND))
        haiku = NV if sbi_rows is None else (CONF if (sbi_rows and sbi_rows[0][1]) else (PART if sbi_rows else PEND))
        run_log = q(conn, "SELECT notes FROM rhp_run_log ORDER BY run_date DESC LIMIT 1")
        rhp_failed = run_log and run_log[0][0] and "FAILED" in str(run_log[0][0])
        if rhp_failed and rhp_dl != CONF:
            rhp_dl = FAIL
        stages = [
            ("Discovery (row exists)", CONF, f"open {od} · close {cd} · list {ld or 'PENDING'}"),
            ("Identity (symbol/ISIN)", CONF if (sym and isin) else PART if sym else PEND, f"sym {sym or '—'} · isin {isin or '—'}"),
            ("Enrichment (band/size)", CONF if (phi and size) else PART if (phi or size) else PEND,
             f"band {plo}–{phi} · ₹{size}cr · fresh {fresh} · OFS {ofs} · anchors {anc if anc is not None else 'PENDING'}"),
            ("RHP downloaded", rhp_dl, rhp_dl_note),
            ("RHP extracted (summary)", CONF if os.path.exists(summ) else (PEND if rhp_dl != CONF else PART), summ if os.path.exists(summ) else "no summary json"),
            ("Sonnet analysis (DB)", sonnet, (f"verdict `{sonnet_row[0][0]}`" if sonnet_row else "no ipo_rhp_intel row")),
            ("SBI note", sbi, (f"rating `{sbi_rows[0][0]}`" if sbi_rows else ("PDF on disk, unparsed" if sbi_pdf else "not published/downloaded"))),
            ("Haiku extract (DB)", haiku, ""),
            ("Score / band", CONF if score is not None else PEND, f"score {score} · band {band} · quality {qs}"),
            ("Fair-value inputs", CONF if (eps and ppe) else PART if (eps or ppe) else PEND,
             f"eps {eps} · peerPE {ppe} · roe {roe} — missing ⇒ fair value must show UNAVAILABLE, never issue price"),
        ]
        out.append("| stage | state | evidence |")
        out.append("|---|---|---|")
        for s_name, s_state, s_ev in stages:
            out.append(f"| {s_name} | {s_state} | {s_ev} |")
        for s_name, s_state, _ in stages:
            if s_state == FAIL and any(k in s_name for k in ("RHP", "Sonnet", "Score")):
                crit_fail.append(f"{name}: {s_name}")

    # RHP directory sanity — the over-match check (ntpc / standard-chartered…)
    out.append("\n## 4 · RHP directory vs discovery (over-match tripwire)\n")
    rdir = os.path.join(REPO, "rhps")
    up_slugs = {slugify(r[0]) for r in (upcoming or [])}
    win = q(conn, """SELECT company_name FROM ipo_intelligence
                     WHERE COALESCE(listing_date, close_date, open_date) >= CURRENT_DATE - 45
                       AND COALESCE(is_sme,false)=false""")
    known = up_slugs | {slugify(r[0]) for r in (win or [])}
    if os.path.isdir(rdir):
        for d in sorted(os.listdir(rdir)):
            pdf = os.path.join(rdir, d, "rhp.pdf")
            tag = "matches a current IPO" if any(d.startswith(k[:8]) or k.startswith(d[:8]) for k in known if k) \
                  else "**SUSPECT — no matching current IPO (SEBI matcher over-matched?)**"
            out.append(f"- `{d}` · pdf={'yes ' + sha256(pdf) if os.path.exists(pdf) else 'EMPTY DIR'} · {tag}")
    else:
        out.append("- rhps/: NOT VERIFIED (absent)")

    # ── UI payload provenance spot-check via sanctioned warm ───────────────
    out.append("\n## 5 · UI payload (what the app actually serves)\n")
    app = os.environ.get("NEXT_PUBLIC_APP_URL", "").rstrip("/")
    key = os.environ.get("ADMIN_JOB_KEY", "")
    if app and key:
        try:
            import urllib.request as u
            req = u.Request(f"{app}/api/ipo-command?warm=1", headers={"x-aac-key": key})
            with u.urlopen(req, timeout=45) as r:
                payload = json.loads(r.read().decode())
            cards = payload.get("cards", [])
            out.append(f"- warm rebuild OK · {len(cards)} cards · generated_at {payload.get('generated_at')}")
            flagged = 0
            for c in cards:
                nm = c.get("company_name")
                ofs_c, fr_c = c.get("ofs_cr"), c.get("fresh_issue_cr")
                try:
                    tot = float(ofs_c or 0) + float(fr_c or 0)
                    opct = round(float(ofs_c or 0) / tot * 100) if tot > 0 else None
                except Exception:
                    opct = None
                if opct is not None and opct >= 60 and not c.get("rhp_full"):
                    out.append(f"  - `{nm}`: OFS {opct}% with NO rhp_full → UI must show the PENDING line (post-#262 behavior), never 'promoter cash-out'")
                if c.get("sbi_rating") is None and c.get("sbi_one_line"):
                    flagged += 1
                    out.append(f"  - **UNSUPPORTED**: `{nm}` has sbi_one_line without sbi_rating source row")
                if (c.get("state") in ("UPCOMING", "OPEN")) and c.get("rhp_verdict") is None and c.get("why_avoid"):
                    out.append(f"  - trace: `{nm}` why_avoid present with no RHP verdict — verify each clause is structured-data-only")
            if not flagged:
                out.append("- no orphan SBI/RHP-attributed fields detected in payload")
        except Exception as e:  # noqa: BLE001
            out.append(f"- warm call failed: {e} → UI column **NOT VERIFIED**")
    else:
        out.append("- NEXT_PUBLIC_APP_URL / ADMIN_JOB_KEY absent → UI column **NOT VERIFIED**")

    # ── verdict + exit code ────────────────────────────────────────────────
    out.append("\n## 6 · Critical verdict\n")
    if cron_exec == FAIL:
        crit_fail.append("cron execution: scheduled but zero pipeline_steps in 36h")
    if fails:
        rhp_sink = [f for f in fails if "rhp" in (f[0] or "").lower() or "rhp" in (f[1] or "").lower()]
        if rhp_sink:
            crit_fail.append(f"pipeline_failures shows RHP step failures ({len(rhp_sink)} in 7d)")
    if crit_fail:
        out.append("**EXIT 1 — critical failures:**")
        for c in crit_fail:
            out.append(f"- {c}")
    else:
        out.append("No critical FAILED stage. (PENDING/NOT VERIFIED items above still need eyes — pending ≠ pass.)")
    print("\n".join(out))
    if conn:
        conn.close()
    return 1 if crit_fail else 0


if __name__ == "__main__":
    sys.exit(main())
