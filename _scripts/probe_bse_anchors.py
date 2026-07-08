#!/usr/bin/env python3
"""
probe_bse_anchors.py — READ-ONLY. Is BSE's anchor-investor filing fetchable
headless for a known pre-2022 IPO? Tries the BSE announcement/circular routes
that carry the 'Anchor Investor' allocation, reports what's reachable.

No DB writes. Prints status + saves any promising payload to bse_probe_*.txt.

  python _scripts/probe_bse_anchors.py
"""
import re, sys, json, urllib.request, urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def get(url, headers=None, timeout=30):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Referer": "https://www.bseindia.com/"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    r = urllib.request.urlopen(req, timeout=timeout)
    return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)

def try_curl(url, headers=None):
    """curl_cffi first (clears many walls), fall back to urllib."""
    try:
        from curl_cffi import requests as creq
        h = {"User-Agent": UA, "Referer": "https://www.bseindia.com/"}
        if headers: h.update(headers)
        r = creq.get(url, headers=h, impersonate="chrome", timeout=30)
        return r.status_code, r.text
    except ImportError:
        try:
            s, t, _ = get(url, headers); return s, t
        except Exception as e:
            return -1, str(e)
    except Exception as e:
        return -1, str(e)

def main():
    # BSE announcement API — anchor allotment filings show as corporate announcements.
    # Test IPO: Antony Waste (BSE 543254), a 2020 listing = pre-2022 trash-tail era.
    print("== 1. BSE announcement API (corp filings) ==")
    # scrip-wise announcement endpoint
    for scrip in ("543254",):
        url = ("https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?"
               f"strCat=-1&strPrevDate=20201220&strScrip={scrip}&strSearch=P&strToDate=20210105&strType=C")
        st, body = try_curl(url, headers={"Origin": "https://www.bseindia.com"})
        print(f"  scrip {scrip}: HTTP {st}  len={len(body)}")
        if st == 200 and body.strip().startswith("{"):
            try:
                d = json.loads(body)
                rows = d.get("Table", [])
                print(f"    announcements returned: {len(rows)}")
                for r in rows[:8]:
                    head = str(r.get("NEWSSUB") or r.get("HEADLINE") or "")[:70]
                    print(f"      {r.get('NEWS_DT','?')[:10]}  {head}")
                    if "anchor" in head.lower():
                        print("        <-- ANCHOR FILING FOUND")
                open("bse_probe_ann.json", "w").write(body[:5000])
            except Exception as e:
                print("    parse err:", e)
        else:
            print(f"    not JSON/200; head: {body[:120]}")

    print("\n== 2. BSE IPO anchor report page (static) ==")
    for url in ("https://www.bseindia.com/publicissue.html",
                "https://www.bseindia.com/markets/PublicIssues/AnchorInvestor.aspx"):
        st, body = try_curl(url)
        has = "anchor" in body.lower()
        print(f"  {url}\n    HTTP {st} len={len(body)} 'anchor'={body.lower().count('anchor')}")

    print("\n== 3. NSE anchor circular (comparison) ==")
    st, body = try_curl("https://www.nseindia.com/api/corporates-corporateActions?index=equities",
                        headers={"Accept": "application/json"})
    print(f"  NSE api: HTTP {st} len={len(body)} (walls usually block cold hits)")

    print("\nREAD-ONLY. Looking for: a 200 JSON announcement list containing an "
          "'Anchor Investor' headline -> then we fetch that filing's PDF/attachment. "
          "If BSE announcement API returns clean JSON, the lane is OPEN.")

if __name__ == "__main__":
    main()
