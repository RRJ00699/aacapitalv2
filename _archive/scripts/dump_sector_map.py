import os, psycopg2, csv
out = os.path.abspath("sector_map.csv")
cur = psycopg2.connect(os.environ["DATABASE_URL"]).cursor()
cur.execute("SELECT nse_symbol, industry, quality_flag FROM stock_quality_flags")
rows = cur.fetchall()
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["nse_symbol", "industry", "quality_flag"])
    w.writerows(rows)
print(f"wrote {len(rows)} rows to: {out}")