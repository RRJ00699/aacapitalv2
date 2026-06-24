#!/usr/bin/env python3
"""
canonicalize_mf_schemes.py — collapse duplicate/variant scheme names to ONE identity per fund.

CRITICAL for the conviction signal: initiation detection groups by scheme_name. If the same
fund appears under several names (casing, SEBI parenthetical suffixes, "Growth Mid Cap" vs
"Growth"), then when a new disclosure lands under a different spelling, EVERY stock looks
newly-initiated — manufacturing dozens of fake "new conviction" flags. This normalizes names
so May and June of the same fund share one identity.

It maps each raw scheme_name to a canonical name via keyword rules (AMC + cap-type), updates
mf_scheme_holdings in place, then re-dedupes on the conflict key. Idempotent.

Run BEFORE compute_mf_conviction_flags, and after any new load:
  python _scripts/mf/canonicalize_mf_schemes.py            # apply
  python _scripts/mf/canonicalize_mf_schemes.py --dry-run  # preview the mapping only
Env:  DATABASE_URL
"""
import os, sys, re, argparse
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def canonical_amc(raw: str) -> str | None:
    """Map any amc_name variant to one canonical AMC label."""
    s = (raw or "").lower()
    if "nippon" in s:  return "Nippon India"
    if "quant"  in s:  return "Quant"
    if "canara" in s:  return "Canara Robeco"
    if "parag" in s or "ppfas" in s: return "PPFAS"
    if "hdfc"   in s:  return "HDFC"
    if "sbi"    in s:  return "SBI"
    return None


def canonical(raw: str) -> str | None:
    """Map any variant to a single canonical 'AMC <CapType> Fund' name."""
    s = (raw or "").lower()
    # AMC
    if "nippon" in s:            amc = "Nippon India"
    elif "quant" in s:           amc = "Quant"
    elif "canara" in s:          amc = "Canara Robeco"
    elif "parag" in s or "ppfas" in s or "flexi" in s and "parag" in s: amc = "PPFAS"
    elif "hdfc" in s:            amc = "HDFC"
    elif "sbi" in s:             amc = "SBI"
    else:                        amc = None

    # cap type / strategy
    if "flexi" in s or "parag parikh" in s:   cap = "Flexi Cap"
    elif "small" in s:                          cap = "Small Cap"
    elif "growth" in s or "mid" in s:           cap = "Mid Cap"   # Nippon Growth == its mid-cap fund
    else:                                       cap = None

    if not amc or not cap:
        return None
    # PPFAS only has the flexi fund
    if amc == "PPFAS":
        return "PPFAS Flexi Cap Fund"
    return f"{amc} {cap} Fund"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT scheme_name FROM mf_scheme_holdings")
    raws = [r[0] for r in cur.fetchall()]

    mapping, unmapped = {}, []
    for raw in raws:
        c = canonical(raw)
        if c is None:
            unmapped.append(raw)
        elif c != raw:
            mapping[raw] = c

    print("CANONICALIZATION MAP")
    print("-" * 70)
    # group by canonical to show the collapse
    from collections import defaultdict
    grp = defaultdict(list)
    for raw, c in mapping.items():
        grp[c].append(raw)
    # include already-canonical names that other variants map into
    for raw in raws:
        c = canonical(raw)
        if c == raw and c in grp:
            grp[c].append(raw + "  (already canonical)")
    for c, variants in sorted(grp.items()):
        print(f"  {c}")
        for v in variants:
            print(f"      <- {v}")
    if unmapped:
        print("\n  UNMAPPED (left as-is — review if these are real funds):")
        for u in unmapped:
            print(f"      ? {u}")

    if args.dry_run:
        print("\n[dry-run] no changes written.")
        conn.close(); return

    if not mapping:
        print("\nNothing to canonicalize — names already clean.")
        conn.close(); return

    # Apply: update scheme_name to canonical. The unique key is (month, amc_name, scheme_name,
    # isin); merging two names for the same month+stock could collide, so delete dupes first,
    # keeping the row with the most recent id.
    for raw, c in mapping.items():
        # delete would-be duplicates (same month+amc+isin already exists under canonical)
        cur.execute("""
            DELETE FROM mf_scheme_holdings a
            USING mf_scheme_holdings b
            WHERE a.scheme_name = %s AND b.scheme_name = %s
              AND a.month = b.month AND a.amc_name = b.amc_name AND a.isin = b.isin
              AND a.id < b.id
        """, (raw, c))
        cur.execute("UPDATE mf_scheme_holdings SET scheme_name = %s WHERE scheme_name = %s", (c, raw))

    conn.commit()

    # ── set amc_name FROM the (clean) scheme_name ──
    # amc_name column is unreliable ("Unknown AMC", or even the wrong AMC on some rows).
    # scheme_name is clean and unambiguous, so derive the AMC from it. This both fixes
    # "Unknown AMC" and corrects mislabeled rows (e.g. a Nippon scheme tagged as quant).
    cur.execute("SELECT DISTINCT scheme_name FROM mf_scheme_holdings")
    schemes = [r[0] for r in cur.fetchall()]
    print("\nAMC re-derivation (from scheme_name):")
    for sch in schemes:
        amc = canonical_amc(sch)
        if not amc:
            print(f"  ?? could not derive AMC for scheme: {sch}"); continue
        # collapse any duplicate key that would collide once amc_name is unified
        cur.execute("""
            DELETE FROM mf_scheme_holdings a
            USING mf_scheme_holdings b
            WHERE a.scheme_name = %s AND b.scheme_name = %s AND a.amc_name <> %s AND b.amc_name = %s
              AND a.month = b.month AND a.isin = b.isin AND a.id < b.id
        """, (sch, sch, amc, amc))
        cur.execute("""
            UPDATE mf_scheme_holdings SET amc_name = %s
            WHERE scheme_name = %s AND (amc_name IS DISTINCT FROM %s)
        """, (amc, sch, amc))
        print(f"  {sch:34s} -> {amc}")
    conn.commit()

    cur.execute("SELECT scheme_name, COUNT(DISTINCT month), MIN(month), MAX(month) "
                "FROM mf_scheme_holdings GROUP BY scheme_name ORDER BY scheme_name")
    print("\nAFTER CANONICALIZATION — distinct funds:")
    for name, nd, mn, mx in cur.fetchall():
        print(f"  {name:34s} {nd:>3d} disclosures  {mn} .. {mx}")
    conn.close()
    print("\nNow re-run: build_isin_symbol_map.py (if needed) -> compute_mf_conviction_flags.py")


if __name__ == "__main__":
    main()
