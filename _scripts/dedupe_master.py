#!/usr/bin/env python3
"""
dedupe_master.py — merges the 9 audited duplicate groups in ipo_intelligence.
For each pair: snapshot both rows to CSV -> COALESCE every column of the loser
into the keeper's NULLs -> delete the loser. Keepers chosen from audit evidence
(correct symbol wins; -BE/-SM mismaps and dataless shells lose).

  python _scripts/dedupe_master.py            # dry: shows keeper/loser + field gains
  python _scripts/dedupe_master.py --apply
"""
import os, csv, sys, argparse

# (keeper_id, loser_id, why)
PAIRS = [
    (718, 714, "Advit: keeper has RAMBHAJO + listing date; loser dataless shell"),
    (910, 851, "Bharti Infratel: keeper INDUSTOWER (successor); loser mismapped BHARTIARTL"),
    (926, 5,   "Equitas SFB: keeper has symbol+date; loser dataless shell"),
    (918, 779, "Khadim: keeper plain KHADIM; loser -BE series variant"),
    (909, 859, "Onelife: keeper plain ONELIFECAP; loser -BE variant"),
    (907, 860, "Taksheel: keeper TAKSHEEL; loser mismapped TAKE-BE (Take Solutions!)"),
    (912, 853, "Tara Jewels: keeper TARAJEWELS; loser mismapped KKJEWELS-SM"),
    (913, 854, "VKS: keeper has VKSPL; loser symbol-less"),
    (717, 710, "Waterways/Cordelia: keeper has CORDELIA symbol; loser has size -> merged in"),
]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='ipo_intelligence' ORDER BY ordinal_position""")
    cols = [r[0] for r in cur.fetchall()]
    non_id = [c for c in cols if c != "id"]

    snap = "dedupe_master_snapshot.csv"
    rows_out = []
    for keeper, loser, why in PAIRS:
        cur.execute(f"SELECT {', '.join(cols)} FROM ipo_intelligence WHERE id IN (%s,%s)",
                    (keeper, loser))
        got = {r[0]: r for r in cur.fetchall()}
        if keeper not in got or loser not in got:
            print(f"SKIP ({keeper},{loser}): missing — already merged?"); continue
        rows_out += [got[keeper], got[loser]]
        k, l = got[keeper], got[loser]
        gains = [c for i, c in enumerate(cols) if c != "id" and k[i] is None and l[i] is not None]
        print(f"keep {keeper} / drop {loser} — {why}")
        print(f"    fields keeper gains from loser: {len(gains)} {gains[:8]}{'...' if len(gains)>8 else ''}")
        if a.apply:
            sets = ", ".join(f"{c}=COALESCE(ipo_intelligence.{c}, loser.{c})" for c in non_id)
            cur.execute(f"""UPDATE ipo_intelligence SET {sets}
                            FROM ipo_intelligence loser
                            WHERE ipo_intelligence.id=%s AND loser.id=%s""", (keeper, loser))
            cur.execute("DELETE FROM ipo_intelligence WHERE id=%s", (loser,))
    if a.apply:
        with open(snap, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(rows_out)
        conn.commit()
        print(f"\nAPPLIED. Pre-merge snapshot of all touched rows -> {snap}")
        cur.execute("SELECT COUNT(*) FROM ipo_intelligence"); print("master rows now:", cur.fetchone()[0])
    else:
        print("\nDRY RUN — --apply merges + deletes (snapshot written first).")
    conn.close()

if __name__ == "__main__":
    main()
