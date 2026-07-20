#!/usr/bin/env python3
"""derive_peer_pe_from_notes.py — the missing Fair-Value wire (2026-07-21).

sbi_haiku_extract has been storing peer_comparison [{name, pe, pb, ronw}] in
ipo_research_notes.full_json — its own docstring calls it "THE missing FV-v2
witness" — but NOTHING consumed it. This step does: median of the note's
valid peer P/Es -> ipo_intelligence.peer_median_pe, FILL-EMPTY ONLY
(SCHEMA.md golden rule), exact normalized-name/symbol join (strong keys).

Runs AFTER the Haiku step and BEFORE fetch_peer_pe (Screener), so:
  SBI-note peers (analyst-curated) fill first; Screener fills the remainder.
Both are fill-empty — no overwrite fights, deterministic order.

  python _scripts/derive_peer_pe_from_notes.py            # preview
  python _scripts/derive_peer_pe_from_notes.py --apply    # write
"""
import argparse
import json
import os
import statistics
import sys

PE_MIN, PE_MAX = 0.5, 500.0   # value sanity: junk/zero/typo peers excluded


def median_pe(peer_comparison) -> float | None:
    """Median of valid peer P/Es; needs >=2 valid peers (a single peer is too
    fragile to anchor fair value). Pure — unit-tested."""
    if not isinstance(peer_comparison, list):
        return None
    vals = []
    for p in peer_comparison:
        if not isinstance(p, dict):
            continue
        try:
            pe = float(p.get("pe"))
        except (TypeError, ValueError):
            continue
        if PE_MIN < pe < PE_MAX:
            vals.append(pe)
    if len(vals) < 2:
        return None
    return round(statistics.median(vals), 2)


WORK_SQL = r"""
    SELECT i.id, i.company_name, n.full_json
    FROM ipo_intelligence i
    JOIN ipo_research_notes n
      ON n.source = 'SBI' AND n.full_json IS NOT NULL
     AND (UPPER(n.nse_symbol) = UPPER(COALESCE(i.nse_symbol, i.symbol))
          OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
             = regexp_replace(lower(i.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g'))
    WHERE i.peer_median_pe IS NULL
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(db, connect_timeout=20)
    cur = conn.cursor()
    cur.execute(WORK_SQL)
    rows = cur.fetchall()
    print(f"IPOs missing peer_median_pe with a parsed SBI note: {len(rows)}")
    wrote = 0
    for iid, name, fj in rows:
        d = fj if isinstance(fj, dict) else (json.loads(fj) if fj else {})
        med = median_pe(d.get("peer_comparison"))
        n_peers = len(d.get("peer_comparison") or [])
        if med is None:
            print(f"  · {name[:40]:42} peers={n_peers} — no usable median (need >=2 valid P/Es)")
            continue
        print(f"  {'✓' if a.apply else '→'} {name[:40]:42} peers={n_peers} median PE {med}")
        if a.apply:
            # fill-empty only — the WHERE re-checks NULL at write time
            cur.execute("""UPDATE ipo_intelligence
                           SET peer_median_pe = %s
                           WHERE id = %s AND peer_median_pe IS NULL""", (med, iid))
            wrote += cur.rowcount
    if a.apply:
        conn.commit()
        print(f"APPLIED: {wrote} row(s). fetch_peer_pe (Screener) fills any remainder.")
    else:
        print("DRY-RUN — add --apply to write.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
