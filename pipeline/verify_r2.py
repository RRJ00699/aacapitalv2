#!/usr/bin/env python3
"""verify_r2.py — READ-ONLY. Prove the R2 read path works WITHOUT deleting local PDFs or
paying for extraction: for each RHP document that has an r2:// url, fetch it from R2,
confirm the sha256 matches, and open it to confirm it is a valid, readable PDF.

This is the safe way to exercise the runner read path from the laptop.

  python verify_r2.py            # every rhp document with an r2:// url
  python verify_r2.py --ipo 85   # one IPO
"""
import os, sys, io, argparse, tempfile, hashlib
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2
import r2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipo", type=int)
    a = ap.parse_args()
    if not r2.configured():
        sys.exit("R2 not configured — set R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY.")

    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    q = ("SELECT ipo_id, url, sha256, page_count FROM documents "
         "WHERE doc_type='rhp' AND url LIKE 'r2://%'")
    if a.ipo:
        cur.execute(q + " AND ipo_id=%s ORDER BY fetched_at DESC", (a.ipo,))
    else:
        cur.execute(q + " ORDER BY ipo_id")
    rows = cur.fetchall()
    if not rows:
        print("no rhp documents with an r2:// url yet — extract one first (extraction uploads to R2).")
        conn.close(); return

    ok = fail = 0
    for ipo_id, url, sha, pc in rows:
        fd, tmp = tempfile.mkstemp(suffix=".pdf"); os.close(fd)
        try:
            if not r2.get_to_file(url, tmp):
                print(f"  FAIL ipo {ipo_id}: fetch failed for {url}"); fail += 1; continue
            got = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
            if sha and got != sha:
                print(f"  FAIL ipo {ipo_id}: sha256 mismatch ({got[:12]} != stored {sha[:12]})"); fail += 1; continue
            try:
                import fitz; pages = len(fitz.open(tmp))
            except Exception as e:
                print(f"  FAIL ipo {ipo_id}: not a readable PDF ({type(e).__name__})"); fail += 1; continue
            note = "" if (pc is None or pages == pc) else f"  (page_count {pages} != stored {pc})"
            print(f"  OK   ipo {ipo_id}: sha256 ✓ · {pages} pages · {url}{note}"); ok += 1
        finally:
            try: os.remove(tmp)
            except OSError: pass

    print(f"\n{ok} OK, {fail} FAIL — R2 read path {'VERIFIED' if fail == 0 and ok else 'has failures'}")
    conn.close()
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
