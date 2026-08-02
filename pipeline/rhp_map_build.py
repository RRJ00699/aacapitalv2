#!/usr/bin/env python3
"""
rhp_map_build.py — resolve local rhps/<folder>/ to ipo.id, with evidence.

WHY THIS IS NOT AUTOMATIC
  A folder slug is a filename. Rule 5 says resolve on ISIN, never a fuzzy name — so
  this script PROPOSES matches and shows what it matched on. It writes a DRAFT map;
  you confirm before anything paid runs against it.

  Resolution order, strongest first:
    1. ISIN from the folder's metadata.json (if present)   -> exact, trustworthy
    2. exact normalized-name equality                       -> strong
    3. normalized-name prefix / containment                 -> PROPOSED ONLY, flagged

  python rhp_map_build.py                 # show candidates, write rhp_map.draft.json
  python rhp_map_build.py --write-map     # promote the draft to rhp_map.json
"""
import os, sys, io, re, json, glob, argparse
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception: pass
import psycopg2

RHP_DIR = "rhps"
DRAFT = "rhp_map.draft.json"
FINAL = "rhp_map.json"

STOP = r"\b(red herring|prospectus|limited|ltd|private|pvt|india|inc|corporation|corp|company|co)\b"


def norm(s):
    s = re.sub(STOP, " ", (s or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def folder_meta(folder):
    """company name + ISIN from metadata.json if the downloader wrote one."""
    mp = os.path.join(RHP_DIR, folder, "metadata.json")
    if not os.path.exists(mp):
        return None, None
    try:
        m = json.load(open(mp, encoding="utf-8"))
    except Exception:
        return None, None
    return (m.get("company") or m.get("name") or m.get("company_name"),
            m.get("isin") or m.get("ISIN"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-map", action="store_true")
    a = ap.parse_args()

    if a.write_map:
        if not os.path.exists(DRAFT):
            sys.exit(f"no {DRAFT} — run without --write-map first and review it")
        d = json.load(open(DRAFT, encoding="utf-8"))
        confirmed = {k: v["folder"] for k, v in d.items() if v.get("confidence") != "weak"}
        json.dump(confirmed, open(FINAL, "w", encoding="utf-8"), indent=2)
        print(f"  wrote {FINAL} with {len(confirmed)} confirmed mappings")
        weak = [k for k, v in d.items() if v.get("confidence") == "weak"]
        if weak:
            print(f"  EXCLUDED {len(weak)} weak match(es): {weak} — map them by hand if correct")
        return

    folders = sorted(d for d in os.listdir(RHP_DIR)
                     if os.path.isdir(os.path.join(RHP_DIR, d))) if os.path.isdir(RHP_DIR) else []
    if not folders:
        sys.exit(f"no folders under {RHP_DIR}/")

    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    cur.execute("""SELECT id, isin, symbol, name_display, name_norm, listing_date, status
                     FROM ipo""")
    rows = cur.fetchall()
    by_isin = {(r[1] or "").upper(): r for r in rows if r[1]}
    by_norm = {}
    for r in rows:
        by_norm.setdefault(norm(r[3]), []).append(r)

    draft = {}
    print(f"  {len(folders)} RHP folders · {len(rows)} IPOs in the spine\n")
    for f in folders:
        pdfs = glob.glob(os.path.join(RHP_DIR, f, "*.pdf"))
        cname, cisin = folder_meta(f)
        key = norm(cname or f.replace("-", " "))
        hit, how, conf = None, None, None

        if cisin and cisin.upper() in by_isin:
            hit, how, conf = by_isin[cisin.upper()], f"isin={cisin}", "strong"
        elif key in by_norm and len(by_norm[key]) == 1:
            hit, how, conf = by_norm[key][0], f"exact name '{key}'", "strong"
        else:
            cands = [r for k, v in by_norm.items() if k and (k.startswith(key) or key.startswith(k)
                     or key in k or k in key) for r in v]
            uniq = {r[0]: r for r in cands}
            if len(uniq) == 1:
                hit, how, conf = list(uniq.values())[0], f"name containment '{key}'", "weak"
            elif len(uniq) > 1:
                how, conf = f"{len(uniq)} candidates for '{key}'", "ambiguous"

        pdf_note = f"{len(pdfs)} pdf" if pdfs else "NO PDF"
        if hit:
            mark = "OK  " if conf == "strong" else "WEAK"
            print(f"  [{mark}] {f:30} -> id={hit[0]:<5} {str(hit[3])[:32]:34} "
                  f"isin={str(hit[1]):<14} listed={hit[5]}  ({how})  [{pdf_note}]")
            draft[str(hit[0])] = {"folder": f, "name": hit[3], "isin": hit[1],
                                  "matched_on": how, "confidence": conf, "pdfs": len(pdfs)}
        else:
            print(f"  [MISS] {f:30} -> no confident match  ({how or 'no candidates'})  [{pdf_note}]")
            if conf == "ambiguous":
                for r in list({r[0]: r for k, v in by_norm.items() if key in k for r in v}.values())[:5]:
                    print(f"           candidate id={r[0]:<5} {str(r[3])[:40]} isin={r[1]}")

    json.dump(draft, open(DRAFT, "w", encoding="utf-8"), indent=2, default=str)
    strong = sum(1 for v in draft.values() if v["confidence"] == "strong")
    print(f"\n  {len(draft)} mapped ({strong} strong) -> {DRAFT}")
    print(f"  Review it, then:  python rhp_map_build.py --write-map")
    print(f"  Weak matches are EXCLUDED from the final map unless you add them by hand.")
    conn.close()


if __name__ == "__main__":
    main()
