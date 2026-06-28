import os, psycopg2
c = psycopg2.connect(os.environ["DATABASE_URL"]); cur = c.cursor()

def q(label, sql):
    try:
        cur.execute(sql); print(f"\n### {label}"); [print(" ", r) for r in cur.fetchall()]
    except Exception as e:
        c.rollback(); print(f"\n### {label}\n  ERR {e}")

# --- what the estimate model already wrote ---
q("earnings_estimates: columns", """
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='earnings_estimates' ORDER BY ordinal_position""")
q("earnings_estimates: row/symbol counts + sample", """
  SELECT count(*), count(distinct symbol) FROM earnings_estimates""")
q("earnings_estimates: 3 sample rows", "SELECT * FROM earnings_estimates LIMIT 3")

# --- where surprises would be written ---
q("earnings_events: columns", """
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='earnings_events' ORDER BY ordinal_position""")
q("earnings_events: counts", "SELECT count(*), count(distinct symbol) FROM earnings_events")
q("earnings_events: 3 sample rows", "SELECT * FROM earnings_events LIMIT 3")

# --- actuals to compare against (we built quarterly_financials in this project) ---
q("quarterly_financials: counts + latest labels", """
  SELECT count(*), count(distinct symbol), min(fiscal_label), max(fiscal_label)
  FROM quarterly_financials""")
q("quarterly_results: columns (legacy quarterly table)", """
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='quarterly_results' ORDER BY ordinal_position""")
q("quarterly_results: counts", "SELECT count(*), count(distinct symbol) FROM quarterly_results")

# --- does an earnings API / screen already exist? (avoid duplication) ---
q("any earnings tables", """
  SELECT table_name FROM information_schema.tables
  WHERE table_schema='public' AND table_name LIKE '%earning%' ORDER BY table_name""")

# --- key-format check: do estimates & actuals share a join key (symbol + period)? ---
q("estimate vs actual key alignment (sample)", """
  SELECT e.symbol, e.fiscal_year, e.fiscal_quarter,
         (SELECT count(*) FROM quarterly_financials q WHERE q.symbol=e.symbol) AS qf_rows
  FROM earnings_estimates e LIMIT 8""")

c.close()
