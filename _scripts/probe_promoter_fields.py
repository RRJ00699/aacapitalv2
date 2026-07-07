#!/usr/bin/env python3
"""
probe_promoter_fields.py — READ-ONLY PROBE (no DB writes): does the Chittorgarh
webnodejs family expose promoter pre/post-issue holding?

Strategy: the list report (82) gives each IPO an id/URL; individual IPO pages
have their own report ids. This probe: (1) pulls one page of report 82, prints
ALL keys of one row (the full schema we could harvest), highlighting any key
matching promoter/holding/dilution/stake; (2) if an ipo id/detail-url field
exists, fetches ONE IPO detail page HTML and greps for 'Promoter Holding'
table fragments to confirm the number exists on-page even if not in the API.

  python _scripts/probe_promoter_fields.py
"""
import json, re, sys, urllib.request

API = ("https://webnodejs.chittorgarh.com/cloud/report/data-read/"
       "82/1/7/2025/2025-26/0/mainboard/0?search=&v=21-38")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
        "Referer": "https://www.chittorgarh.com/"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")

def main():
    print("== report 82, page 1 ==")
    data = json.loads(get(API))
    rows = data.get("reportTableData") or data.get("data") or []
    if not rows:
        print("no rows; raw keys:", list(data)[:10]); return
    row = rows[0]
    keys = list(row.keys())
    print(f"row keys ({len(keys)}):")
    for k in keys:
        mark = "  <-- CANDIDATE" if re.search(r"promot|holding|dilut|stake|equity", k, re.I) else ""
        print(f"  {k}: {str(row[k])[:60]}{mark}")
    # find a detail link
    link = None
    for k, v in row.items():
        if isinstance(v, str) and "chittorgarh.com" in v and "/ipo/" in v:
            link = re.search(r'href="([^"]+)"', v)
            link = link.group(1) if link else v
            break
    if not link:
        for k, v in row.items():
            if isinstance(v, str) and v.startswith("/ipo/"):
                link = "https://www.chittorgarh.com" + v; break
    if not link:
        print("\nno detail link found in row — paste this output back."); return
    print(f"\n== detail page probe: {link} ==")
    html = get(link)
    hits = [m.start() for m in re.finditer(r"[Pp]romoter[s]?\s*[Hh]olding", html)]
    print(f"'Promoter Holding' occurrences: {len(hits)}")
    for h in hits[:3]:
        frag = re.sub(r"<[^>]+>", " ", html[h:h+400])
        print("  ...", re.sub(r"\s+", " ", frag)[:220])

if __name__ == "__main__":
    main()
