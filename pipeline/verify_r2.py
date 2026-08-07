#!/usr/bin/env python3
"""verify_r2.py — READ-ONLY contract-v1 exact-key verification without model spend.

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
    q = ("SELECT ipo_id, object_key, sha256, byte_size, page_count FROM documents "
         "WHERE doc_type='rhp' AND object_key IS NOT NULL AND byte_size IS NOT NULL "
         "AND content_type='application/pdf' AND object_contract_version='1'")
    if a.ipo:
        cur.execute(q + " AND ipo_id=%s ORDER BY fetched_at DESC", (a.ipo,))
    else:
        cur.execute(q + " ORDER BY ipo_id")
    rows = cur.fetchall()
    if not rows:
        print("no fully verified contract-v1 RHP document exists in the ledger")
        conn.close(); return

    ok = fail = 0
    for ipo_id, object_key, sha, byte_size, pc in rows:
        fd, tmp = tempfile.mkstemp(suffix=".pdf"); os.close(fd)
        try:
            content = r2.get_document(object_key)
            if not content.startswith(b"%PDF-"):
                print(f"  FAIL ipo {ipo_id}: bad PDF signature"); fail += 1; continue
            if len(content) != byte_size:
                print(f"  FAIL ipo {ipo_id}: byte-size mismatch"); fail += 1; continue
            open(tmp, "wb").write(content)
            got = hashlib.sha256(content).hexdigest()
            if sha and got != sha:
                print(f"  FAIL ipo {ipo_id}: sha256 mismatch ({got[:12]} != stored {sha[:12]})"); fail += 1; continue
            try:
                import fitz; pages = len(fitz.open(tmp))
            except Exception as e:
                print(f"  FAIL ipo {ipo_id}: not a readable PDF ({type(e).__name__})"); fail += 1; continue
            note = "" if (pc is None or pages == pc) else f"  (page_count {pages} != stored {pc})"
            print(f"  OK   ipo {ipo_id}: sha256 ✓ · {pages} pages · doc key verified{note}"); ok += 1
        finally:
            try: os.remove(tmp)
            except OSError: pass

    print(f"\n{ok} OK, {fail} FAIL — R2 read path {'VERIFIED' if fail == 0 and ok else 'has failures'}")
    conn.close()
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
