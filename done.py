import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Derive listing_date = first candle in listing year
cur.execute("""
    UPDATE ipo_intelligence i SET listing_date = sub.first_date
    FROM (
        SELECT i2.id, MIN(pc.date) as first_date
        FROM ipo_intelligence i2
        JOIN ipo_history h ON LOWER(h.name) = LOWER(i2.company_name)
        JOIN price_candles pc ON pc.symbol = i2.symbol
            AND EXTRACT(YEAR FROM pc.date) = h.year
        WHERE i2.symbol IS NOT NULL AND i2.listing_date IS NULL
        GROUP BY i2.id
    ) sub
    WHERE i.id = sub.id
""")
print(f"listing_date updated: {cur.rowcount}")
conn.commit()

# Calculate returns
cur.execute("""
    SELECT i.id, i.symbol, i.issue_price, i.listing_date::text
    FROM ipo_intelligence i
    WHERE i.symbol IS NOT NULL AND i.issue_price IS NOT NULL
      AND i.listing_date IS NOT NULL AND i.return_day30 IS NULL
""")
ipos = cur.fetchall()
print(f"Calculating returns for {len(ipos)} IPOs...")

done = 0
for (iid, symbol, issue_price, listing_date) in ipos:
    ip = float(issue_price)
    cur.execute("""
        SELECT close, high, low FROM price_candles
        WHERE symbol=%s AND date >= %s::date
        ORDER BY date ASC LIMIT 120
    """, [symbol, listing_date])
    candles = cur.fetchall()
    if not candles: continue

    c = [float(x[0]) for x in candles]
    h = [float(x[1]) for x in candles]
    l = [float(x[2]) for x in candles]
    def r(p): return round((p-ip)/ip*100,2) if ip>0 else None

    d30 = r(c[20]) if len(c)>20 else None
    if d30 is None: bucket=None
    elif d30<-10: bucket="LOSS"
    elif d30<10:  bucket="FLAT"
    elif d30<20:  bucket="10PCT"
    elif d30<50:  bucket="20PCT"
    elif d30<100: bucket="50PCT"
    else:         bucket="MULTIBAGGER"

    cur.execute("""
        UPDATE ipo_intelligence SET
            return_day1_close=COALESCE(return_day1_close,%s),
            return_day7=%s, return_day30=%s, return_day90=%s, return_cmp=%s,
            max_upside_pct=%s, max_drawdown_day30=%s,
            achieved_10pct=%s, archetype=COALESCE(NULLIF(archetype,'UNKNOWN'),%s),
            updated_at=NOW()
        WHERE id=%s
    """, [r(c[1]) if len(c)>1 else None,
          r(c[4]) if len(c)>4 else None, d30,
          r(c[62]) if len(c)>62 else None, r(c[-1]),
          r(max(h[:21])), r(min(l[:21])),
          bool(max(h[:21])>ip*1.1 if h else False), bucket, iid])
    done += 1
    if done % 50 == 0:
        conn.commit()
        print(f"  {done} done...")

conn.commit()

cur.execute("""
    SELECT COUNT(*), COUNT(symbol), COUNT(listing_date),
           COUNT(return_day30), COUNT(qib_subscription_x),
           COUNT(*) FILTER (WHERE listing_gap_pct IS NOT NULL AND return_day30 IS NOT NULL AND qib_subscription_x IS NOT NULL)
    FROM ipo_intelligence
""")
t,s,d,r30,q,ready = cur.fetchone()
print(f"\nFINAL STATE:")
print(f"  Total         : {t}")
print(f"  Symbol        : {s}")
print(f"  Listing date  : {d}")
print(f"  D30 return    : {r30}")
print(f"  QIB sub       : {q}")
print(f"  ENGINE READY  : {ready}")
conn.close()
print("\nDone! Sleep well.")
