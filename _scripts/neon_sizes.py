import os, psycopg2
c = psycopg2.connect(os.environ["DATABASE_URL"]).cursor()
c.execute("""
    SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
    FROM pg_catalog.pg_statio_user_tables
    ORDER BY pg_total_relation_size(relid) DESC
    LIMIT 20
""")
for name, size in c.fetchall():
    print(f"{name:30s} {size}")