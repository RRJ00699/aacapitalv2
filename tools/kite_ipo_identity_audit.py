from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

import psycopg2
from kiteconnect import KiteConnect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "kite-ipo-identity-audit.json"


def norm_name(v: str | None) -> str:
    s = (v or "").lower()
    s = re.sub(r"\b(limited|ltd|private|pvt|company|co)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def db_url() -> str:
    url = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise SystemExit("NEON_READONLY_DATABASE_URL (preferred) or DATABASE_URL is required")
    return url


def main() -> int:
    conn = psycopg2.connect(db_url(), connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    cur = conn.cursor()
    cur.execute("""
      SELECT i.id,i.name_display,i.symbol,i.isin,i.listing_date,COALESCE(i.lock30,i.listing_date+30),i.kite_token
      FROM ipo i
      WHERE COALESCE(i.is_mainboard,false)=true
        AND i.listing_date IS NOT NULL
        AND i.listing_date >= DATE '2016-01-01'
        AND i.listing_date <= CURRENT_DATE
      ORDER BY i.listing_date,i.id
    """)
    rows = cur.fetchall()
    cur.execute("SELECT key,value FROM platform_config WHERE key IN ('kite_api_key','kite_access_token')")
    cfg = dict(cur.fetchall())
    cur.close(); conn.close()

    api_key = cfg.get('kite_api_key') or os.environ.get('KITE_API_KEY')
    token = cfg.get('kite_access_token') or os.environ.get('KITE_ACCESS_TOKEN')
    if not api_key or not token:
        raise SystemExit('Kite credentials unavailable; refresh token first')
    kite = KiteConnect(api_key=api_key); kite.set_access_token(token)
    profile = kite.profile(); print(f"Kite token valid for user_id={profile.get('user_id')}")
    inst = [i for i in kite.instruments('NSE') if i.get('segment') == 'NSE']

    by_token = {int(i['instrument_token']): i for i in inst if i.get('instrument_token')}
    by_symbol = {str(i.get('tradingsymbol') or '').upper(): i for i in inst if i.get('tradingsymbol')}
    by_name = defaultdict(list)
    for i in inst:
        n = norm_name(i.get('name'))
        if n:
            by_name[n].append(i)

    audited=[]; counts=defaultdict(int)
    for ipo_id,name,symbol,isin,listing_date,lock30,stored_token in rows:
        sym = str(symbol or '').strip().upper()
        nn = norm_name(name)
        st = int(stored_token) if stored_token is not None else None
        current_for_token = by_token.get(st) if st is not None else None
        symbol_match = by_symbol.get(sym) if sym else None
        name_matches = by_name.get(nn, [])
        exact_name_unique = name_matches[0] if len(name_matches) == 1 else None

        chosen = None; reason = None; status = None
        if current_for_token:
            tok_sym = str(current_for_token.get('tradingsymbol') or '').upper()
            tok_name = norm_name(current_for_token.get('name'))
            if (sym and tok_sym == sym) or (nn and tok_name == nn):
                chosen = st; status='VERIFIED_CURRENT_TOKEN'; reason='stored token matches current symbol/name'
            else:
                replacement = exact_name_unique or symbol_match
                if replacement and int(replacement['instrument_token']) != st:
                    chosen = int(replacement['instrument_token']); status='RECOVERED_CURRENT_IDENTITY'; reason='stored token mismatched; recovered by exact current company identity'
                else:
                    status='TOKEN_IDENTITY_MISMATCH'; reason=f"stored token currently maps to {tok_sym}/{current_for_token.get('name')}"
        else:
            replacement = exact_name_unique or symbol_match
            if replacement:
                chosen = int(replacement['instrument_token'])
                status='RECOVERED_CURRENT_IDENTITY'; reason='recovered by exact current company identity'
            elif st is not None:
                chosen = st
                status='HISTORICAL_TOKEN_UNVERIFIED'; reason='stored token not in current NSE instrument list'
            else:
                status='UNRESOLVED'; reason='no stored token and no exact current symbol/name match'

        counts[status]+=1
        audited.append({
            'ipo_id':int(ipo_id),'name':name,'symbol':sym or None,'isin':isin,
            'listing_date':str(listing_date),'lock30':str(lock30),'stored_token':st,
            'chosen_token':chosen,'status':status,'reason':reason,
            'current_token_symbol': (str(current_for_token.get('tradingsymbol')) if current_for_token else None),
            'current_token_name': (current_for_token.get('name') if current_for_token else None),
        })

    report={'eligible_ipos':len(rows),'status_counts':dict(sorted(counts.items())),'rows':audited}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({'eligible_ipos':len(rows),'status_counts':dict(sorted(counts.items())),'output':str(OUT.relative_to(ROOT))},sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
