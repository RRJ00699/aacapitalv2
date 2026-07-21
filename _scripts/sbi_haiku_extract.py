#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sbi_haiku_extract.py — Haiku reads SBI Securities IPO notes. $0.50/day cap,
NEW IPOs only (close_date/listing_date current or future). Mirrors rhp_auto's
fault-proof budget architecture (own run log, remaining-cap gating, deferred
notes retry next run automatically).

What it extracts (SBI notes have a stable structure):
  rating ("Subscribe"/"Avoid"/...), one_line thesis, peer_comparison
  [{name, pe, pb, ronw}] — THE missing FV-v2 witness — strengths[], risks[],
  financial_snapshot, redflag_or_clean. Stored in ipo_research_notes.full_json.
Cost: a 10-15 page note ≈ 10-14k tokens in + ~800 out ≈ $0.015-0.02/note on
Haiku ($1/M in, $5/M out) → the $0.50 cap covers ~25 notes/day; new-IPO flow
is 1-3/day, so the cap is a fence, not a constraint.
Run:  python _scripts/sbi_haiku_extract.py           (lean step; safe to rerun)
"""
import json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2

DAILY_CAP = 0.50
MODEL = "claude-haiku-4-5-20251001"
IN_RATE, OUT_RATE = 1.0 / 1e6, 5.0 / 1e6   # USD per token

PROMPT = """You are AACapital's research extractor. Below is the full text of an
SBI Securities IPO note. Return ONLY a JSON object (no prose, no markdown):
{
 "rating": "<their recommendation verbatim, e.g. Subscribe / Subscribe for long term / Avoid / null>",
 "one_line": "<their core thesis in one sentence, your words>",
 "peer_comparison": [{"name": "", "pe": null, "pb": null, "ronw": null}],
 "strengths": ["<max 4, short, concrete — numbers over adjectives>"],
 "risks": ["<max 4, short, concrete>"],
 "financial_snapshot": {"revenue_growth": null, "pat_margin": null, "roe": null, "notes": ""},
 "valuation_comment": "<their view on pricing vs peers, one sentence, or null>",
 "clean_or_flagged": "<clean|flagged> — flagged if the note itself raises governance/litigation/auditor concerns"
}
Numbers as numbers, unknown as null. peer_comparison ONLY from an explicit peer
table/section — never invent peers. NOTE TEXT:
"""

# Work query as a module constant so tests can execute it against a seeded DB.
# WINDOW FIX 2026-07-18: was `CURRENT_DATE - 2`, which excluded every IPO that
# listed more than 2 days ago — 6 of the 9 currently-eligible notes. Widened to
# the same 30-day window the Command Center shows, on the IST clock.
TODO_SQL = r"""
    SELECT n.id, n.company, n.pdf_path
    FROM ipo_research_notes n
    JOIN ipo_intelligence i
      ON regexp_replace(lower(i.company_name), '\y(ltd|limited|pvt|private|ipo|and)\y|&|[^a-z0-9]', '', 'g')
       = regexp_replace(lower(n.company),      '\y(ltd|limited|pvt|private|ipo|and)\y|&|[^a-z0-9]', '', 'g')
    WHERE n.source = 'SBI' AND n.pdf_path IS NOT NULL AND n.full_json IS NULL
      -- LOCKED eligibility (2026-07-21): SBI publishes notes for SME/small
      -- names too; we paid to read five of them. The <200cr/SME rule now
      -- gates the SPEND, not just the feeds. NULL size stays eligible.
      AND COALESCE(i.is_sme, false) = false
      AND (i.issue_size_cr IS NULL OR i.issue_size_cr >= 200)
      AND (i.listing_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date - 30
           OR i.close_date  >= (now() AT TIME ZONE 'Asia/Kolkata')::date
           OR i.listing_date IS NULL)
    ORDER BY i.listing_date NULLS LAST"""


def ensure_log(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS sbi_haiku_run_log (
        id SERIAL PRIMARY KEY, run_date DATE DEFAULT CURRENT_DATE,
        company TEXT, spent_usd NUMERIC(8,4) NOT NULL DEFAULT 0,
        ok BOOLEAN, note TEXT, ran_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("""ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS full_json JSONB""")
    cur.execute("""ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS one_line TEXT""")
    cur.execute("""ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS ai_model TEXT""")

def spent_today(cur):
    cur.execute("SELECT COALESCE(SUM(spent_usd),0) FROM sbi_haiku_run_log WHERE run_date = CURRENT_DATE")
    return float(cur.fetchone()[0])

def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = False
    cur = conn.cursor(); ensure_log(cur); conn.commit()

    # NEW IPOs only: note exists w/ pdf, no extraction yet, and the IPO is
    # current/upcoming (canon join — one canonicalizer everywhere).
    cur.execute(TODO_SQL)
    todo = cur.fetchall()
    print(f"unextracted SBI notes (new IPOs): {len(todo)} | cap ${DAILY_CAP:.2f} | spent today ${spent_today(cur):.3f}")
    if not todo:
        conn.close(); return

    try:
        import anthropic, pdfplumber  # noqa
    except ImportError as e:
        sys.exit(f"missing dep: {e} — pip install anthropic pdfplumber --break-system-packages")
    # Phase-5 (baseline 2026-07-21: this step failed identically 2x/day with an
    # opaque trace). Preflight the key and the client so pipeline_failures'
    # stderr_tail names the EXACT fix instead of a stack dump.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY missing from VM env (.env) — Haiku extraction "
                 "cannot run. Add the key; the deferred notes retry automatically.")
    try:
        client = anthropic.Anthropic()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"anthropic client init failed: {type(e).__name__}: {str(e)[:150]}")

    for nid, company, pdf_path in todo:
        remaining = DAILY_CAP - spent_today(cur)
        if remaining < 0.03:
            cur.execute("INSERT INTO sbi_haiku_run_log (company, ok, note) VALUES (%s,false,%s)",
                        (company, f"cap hit — deferred (remaining ${remaining:.3f})"))
            conn.commit(); print(f"  CAP HIT — {company} deferred to next run"); break
        if not os.path.exists(pdf_path):
            # Windows rows: pdf_path was written on the PC with backslashes
            # ("data\research_notes\X.pdf" — VM run 2026-07-21). Normalize and
            # retry by basename before declaring it missing; repair the SOURCE
            # row when found (path was wrong, not empty — this is a fix, not a
            # fill).
            cand = os.path.join("data", "research_notes",
                                os.path.basename(pdf_path.replace("\\", "/")))
            if os.path.exists(cand):
                cur.execute("UPDATE ipo_research_notes SET pdf_path=%s WHERE id=%s", (cand, nid))
                conn.commit(); pdf_path = cand
            else:
                cur.execute("INSERT INTO sbi_haiku_run_log (company, ok, note) VALUES (%s,false,'pdf missing on disk')", (company,))
                conn.commit(); print(f"  SKIP {company}: pdf missing {pdf_path}"); continue
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for pg in pdf.pages:
                    text += (pg.extract_text() or "") + "\n"
            text = text[:60000]  # ~15k tokens ceiling
            msg = client.messages.create(model=MODEL, max_tokens=1200,
                messages=[{"role": "user", "content": PROMPT + text}])
            raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
            cost = msg.usage.input_tokens * IN_RATE + msg.usage.output_tokens * OUT_RATE
            cur.execute("""UPDATE ipo_research_notes
                           SET full_json = %s, one_line = %s, ai_model = %s WHERE id = %s""",
                        (json.dumps(data), data.get("one_line"), MODEL, nid))
            cur.execute("INSERT INTO sbi_haiku_run_log (company, spent_usd, ok, note) VALUES (%s,%s,true,%s)",
                        (company, round(cost, 4), f"peers={len(data.get('peer_comparison') or [])}"))
            conn.commit()
            try:
                from lib.stage_state import record as _rec
                _rec(conn, company, "SBI_EXTRACTED", "CONFIRMED", version=MODEL)
            except Exception:
                pass
            print(f"  ✓ {company}: ${cost:.4f} · rating={data.get('rating')} · peers={len(data.get('peer_comparison') or [])}")
        except Exception as e:
            conn.rollback()
            cur.execute("INSERT INTO sbi_haiku_run_log (company, ok, note) VALUES (%s,false,%s)",
                        (company, str(e)[:200]))
            conn.commit(); print(f"  ✗ {company}: {str(e)[:100]}")
    conn.close()

if __name__ == "__main__":
    main()
