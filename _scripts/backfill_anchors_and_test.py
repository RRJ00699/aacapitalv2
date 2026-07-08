#!/usr/bin/env python3
"""
backfill_anchors_and_test.py — fills anchor_count/anchor_names from Chittorgarh
detail pages (same __next_f + AnchorTable method as enrich_ipo_chittorgarh.py,
via curl_cffi to clear the bot wall), then runs the count-vs-return backtest.

Detail URL comes from the Company href already stored, or is built from slug.
Fill-empty only. Resume-safe (skips IPOs that already have anchor_count).

  python _scripts/backfill_anchors_and_test.py --limit 5          # test fetch
  python _scripts/backfill_anchors_and_test.py --apply            # full backfill
  python _scripts/backfill_anchors_and_test.py --test-only        # just the backtest
"""
import os, re, sys, json, time, argparse

def clean_str(v):
    if v is None: return None
    s = str(v).strip()
    return None if s.lower() in ("", "na", "n/a", "-", "null", "none") else s

def parse_anchors(html):
    mt = re.search(r"id=['\"]AnchorTable['\"].*?</table>", html, re.S)
    if not mt: return []
    out = []
    for am in re.finditer(r'ipo-anchor-list-vs-listing-gain/\d+/\w+/\d+"[^>]*>\s*([^<]+?)\s*</a>', mt.group()):
        nm = clean_str(am.group(1))
        if nm: out.append(nm)
    return out

def fetch(url):
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome", timeout=30)
        return r.text
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})
        return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2], sum(rets)/n

def run_backtest(cur):
    cur.execute("""SELECT anchor_count, listing_gap_pct, d10_best_pct
                   FROM ipo_intelligence
                   WHERE anchor_count IS NOT NULL AND d10_best_pct IS NOT NULL""")
    rows = cur.fetchall()
    print(f"\n=== ANCHOR COUNT vs d10 — n={len(rows)} ===")
    if len(rows) < 30:
        print("coverage still thin (<30). Backfill more, then --test-only.")
        return
    def bucket(c):
        c = int(c)
        return "1-5" if c <= 5 else ("6-10" if c <= 10 else ("11-20" if c <= 20 else "20+"))
    def gb(g):
        try: g = float(g)
        except (TypeError, ValueError): return "?"
        return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")
    pooled, cross = {}, {}
    for c, g, d10 in rows:
        b = bucket(c); d = float(d10)
        pooled.setdefault(b, []).append(d)
        cross.setdefault((b, gb(g)), []).append(d)
    print(f"{'anchors':8} {'n':>4} {'win%':>6} {'med':>6} {'mean':>6}")
    for b in ("1-5", "6-10", "11-20", "20+"):
        st = stats(pooled.get(b, []))
        if st: print(f"{b:8} {st[0]:>4} {st[1]:>6.1f} {st[2]:>+6.1f} {st[3]:>+6.1f}")
    print("\nby gap bucket:")
    for (b, g), v in sorted(cross.items(), key=lambda t:(t[0][1],t[0][0])):
        st = stats(v)
        if st: print(f"  {g:4} {b:8} n={st[0]:<3} win={st[1]:5.1f}% med={st[2]:+6.1f}")
    print("\nBar: n>=30, win-gap >=8pts vs 72% baseline, monotonic in count.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--test-only", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    if a.test_only:
        run_backtest(cur); return
    cur.execute("""SELECT id, company_name FROM ipo_intelligence
                   WHERE anchor_count IS NULL AND listing_date IS NOT NULL
                   ORDER BY listing_date DESC""")
    todo = cur.fetchall()
    print(f"IPOs needing anchors: {len(todo)}")
    filled = fetched = 0
    for pid, name in todo:
        if a.limit and fetched >= a.limit: break
        slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
        slug = re.sub(r"-(ltd|limited|pvt|private)$", "", slug)
        url = f"https://www.chittorgarh.com/ipo/{slug}-ipo/"
        fetched += 1
        try:
            names = parse_anchors(fetch(url))
        except Exception as e:
            print(f"  {name[:30]}: {e}"); continue
        time.sleep(a.sleep)
        if not names:
            print(f"  {name[:30]}: no anchor table (slug miss: {slug})"); continue
        filled += 1
        print(f"  {name[:30]:32} anchors={len(names)}")
        if a.apply:
            cur.execute("""UPDATE ipo_intelligence SET
                anchor_names=COALESCE(anchor_names,%s), anchor_count=COALESCE(anchor_count,%s)
                WHERE id=%s""", (json.dumps(names), len(names), pid))
    if a.apply: conn.commit()
    print(f"\n{'WROTE' if a.apply else 'DRY'}: filled {filled}/{fetched} fetched")
    run_backtest(cur)
    conn.close()

if __name__ == "__main__":
    main()
