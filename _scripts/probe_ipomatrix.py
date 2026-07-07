#!/usr/bin/env python3
"""
probe_ipomatrix.py — READ-ONLY. Discovers what IPOMatrix exposes for one IPO,
so an importer can be built against reality. Tries, in order:
  1. any JSON/API endpoint the page calls (webnodejs-style or /api/)
  2. the raw HTML: dumps every "Label: Value" pair and any <table> rows
No DB. Prints findings; writes the full HTML to ipomatrix_sample.html for review.

  python _scripts/probe_ipomatrix.py
  python _scripts/probe_ipomatrix.py --url https://www.ipomatrix.com/ipo/<slug>/<id>/
"""
import re, sys, json, argparse, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    r = urllib.request.urlopen(req, timeout=timeout)
    return r.read().decode("utf-8", "replace"), r.headers.get("content-type", "")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://www.ipomatrix.com/ipo/protean-egov-technologies-ipo/1545/")
    a = ap.parse_args()
    print(f"== fetching {a.url} ==")
    html, ctype = get(a.url)
    print(f"content-type={ctype}  len={len(html)}")
    open("ipomatrix_sample.html", "w", encoding="utf-8").write(html)
    print("full HTML saved -> ipomatrix_sample.html\n")

    # 1) hunt for API/JSON endpoints referenced in the page
    apis = set(re.findall(r'https?://[^\s"\'<>]+(?:api|webnodejs|data-read|/json)[^\s"\'<>]*', html, re.I))
    apis |= set(re.findall(r'(?:fetch|axios\.get)\(["\']([^"\']+)["\']', html))
    print(f"candidate API endpoints ({len(apis)}):")
    for u in list(apis)[:12]: print("  ", u[:110])

    # 2) look for an embedded JSON blob (Next.js __NEXT_DATA__ etc.)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            j = json.loads(m.group(1))
            print("\n__NEXT_DATA__ present — top keys:", list(j.keys()))
            props = j.get("props", {}).get("pageProps", {})
            print("pageProps keys:", list(props.keys())[:25])
            # dump any dict of ipo fields
            for k, v in props.items():
                if isinstance(v, dict) and len(v) > 5:
                    print(f"\n  props['{k}'] fields:")
                    for kk, vv in list(v.items())[:40]:
                        print(f"      {kk}: {str(vv)[:60]}")
        except Exception as e:
            print("  __NEXT_DATA__ parse error:", e)

    # 3) plain-text label:value pairs
    txt = re.sub(r"<[^>]+>", "|", html)
    txt = re.sub(r"\|+", "|", txt)
    pairs = re.findall(r"\|([A-Z][A-Za-z /()%.]{3,40})\|([₹]?[\d,.\-]+%?(?:\s*Cr\.?)?)\|", txt)
    seen = set()
    print(f"\nlabel:value pairs found ({len(pairs)} raw):")
    for lbl, val in pairs:
        key = lbl.strip()
        if key in seen: continue
        seen.add(key)
        print(f"  {key:32} = {val.strip()}")
        if len(seen) >= 60: break

if __name__ == "__main__":
    main()
