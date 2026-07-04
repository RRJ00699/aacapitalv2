import sys, re
import pdfplumber

path = sys.argv[1]
full = ""
tables = []
with pdfplumber.open(path) as pdf:
    for pg in pdf.pages:
        full += (pg.extract_text() or "") + "\n"
        tables += (pg.extract_tables() or [])

full = re.sub(r"[ \t]+", " ", full)
print("========== TEXT AROUND PEER / VALUATION ==========")
seen = set()
for kw in ["Peer Comparison", "Peer", "Comparative", "Valuation", "P/E", "RoE"]:
    m = re.search(kw, full, re.I)
    if m and kw.lower() not in seen:
        seen.add(kw.lower())
        s = max(0, m.start() - 150); e = min(len(full), m.start() + 500)
        print(f"\n----- '{kw}' @ {m.start()} -----\n{full[s:e]}")

print("\n\n========== TABLES MENTIONING P/E · RoE · Peer · Company ==========")
for i, t in enumerate(tables):
    flat = " ".join(" ".join((c or "") for c in row) for row in t).lower()
    if any(k in flat for k in ["p/e", "pe ", "peer", "roe", "p/b", "company", "median"]):
        print(f"\n--- table {i} ({len(t)} rows) ---")
        for row in t:
            print([ (c or "").strip() for c in row ])
