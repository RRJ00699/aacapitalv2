import os, psycopg2
c = psycopg2.connect(os.environ["DATABASE_URL"]); cur = c.cursor()

def q(label, sql):
    try:
        cur.execute(sql); print(f"\n### {label}"); [print(" ", r) for r in cur.fetchall()]
    except Exception as e:
        c.rollback(); print(f"\n### {label}\n  ERR {e}")

q("row + symbol counts", """
  SELECT 'financial_dna' t, count(*), count(distinct symbol) FROM financial_dna
  UNION ALL SELECT 'valuation', count(*), count(distinct symbol) FROM valuation
  UNION ALL SELECT 'quarterly_financials', count(*), count(distinct symbol) FROM quarterly_financials
  UNION ALL SELECT 'company_master', count(*), count(distinct nse_symbol) FROM company_master""")

q("company_master columns", """
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='company_master' ORDER BY ordinal_position""")

q("financial_dna columns", """
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='financial_dna' ORDER BY ordinal_position""")

q("valuation columns", """
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='valuation' ORDER BY ordinal_position""")

q("join-key check: do symbols line up across tables?", """
  SELECT cm.nse_symbol,
         (d.symbol IS NOT NULL) has_dna,
         (v.symbol IS NOT NULL) has_val
  FROM company_master cm
  LEFT JOIN financial_dna d ON d.symbol = cm.nse_symbol
  LEFT JOIN valuation   v ON v.symbol = cm.nse_symbol
  ORDER BY cm.nse_symbol
  LIMIT 10""")

q("sector column sample (rename in query if the column differs)", """
  SELECT nse_symbol, sector, industry FROM company_master LIMIT 5""")

c.close()
