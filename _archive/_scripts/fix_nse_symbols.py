"""
Fix NSE symbols that changed or are wrong in our DB.
These 31 IPOs have no Kite instrument token because the symbol stored
is wrong/old. Map to correct current NSE symbol.
"""
import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

# Correct symbol mappings: stored_symbol -> correct_kite_symbol
SYMBOL_FIXES = {
    'ZOMATO':     'ZOMATO',      # Listed fine - may be BSE only in Kite
    'KALYAN':     'KALYANKJIL',
    'ROLEX':      'ROLEXRINGS',
    'GLS':        'GLENMARK',    # Glenmark Life Sciences
    'CHEMPLAST':  'CHEMPLASTS',
    'AMIORG':     'AMIORG',
    'SHYMMETAL':  'SHYAMMETL',
    'BARBEQUE':   'BARBEQUE',
    'MTAR':       'MTAR',
    'PDSTL':      'PDSL',        # Paras Defence
    'FINO':       'FINOPB',
    'ARWL':       'ARWL',
    'AGSTRA':     'AGSTRA',
    'HARIOM':     'HARIOMPIPE',
    'DCX':        'DCXINDIA',
    'ARCHEAN':    'ACI',
    'SAH':        'SAH',
    'AHL':        'AFSL',        # Abans Holdings
    'MML':        'MUTHOOTMF',
    'HMA':        'HMAAGRO',
    'GOPALSNACK': 'GOPALSNACK',
    'BZRSTYL':    'BZRSTYL',
    'STBAL':      'STBAL',
    'IGIIL':      'IGIIL',
    'SGLTL':      'SGLTL',
    'ATHER':      'ATHER',
    'ARISINFRA':  'ARISINFRA',
    'NSDL':       'NSDL',
    'SAATVIK':    'SAATVIKGL',
    'PHYSICS':    'PWL',
    'MML':        'MML',
}

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

fixed = 0
for old_sym, new_sym in SYMBOL_FIXES.items():
    if old_sym != new_sym:
        cur.execute("""
            UPDATE ipo_intelligence 
            SET nse_symbol = %s 
            WHERE nse_symbol = %s
        """, (new_sym, old_sym))
        if cur.rowcount > 0:
            print(f"  Fixed: {old_sym} → {new_sym} ({cur.rowcount} rows)")
            fixed += cur.rowcount

conn.commit()
conn.close()
print(f"\nTotal fixed: {fixed} symbol mappings")
print("Now run: python fix_listing_day_close.py")
