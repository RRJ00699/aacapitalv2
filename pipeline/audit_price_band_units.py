#!/usr/bin/env python3
"""Bounded official-NSE audit and owner-gated exact-identity price-band repair."""
import argparse, json, os
from nse_fetch import API, HEADERS, parse_issue_info, prime
from fill_v2 import validate_issue_economics

APPROVAL = "REPAIR_VERIFIED_NSE_PRICE_BANDS"
MAX_ROWS = 25

def classify(row):
    ipo_id, isin, symbol, face, lo, hi, price, source, raw, gap, pool, winner, observed_floor = row
    values={"face_value":face,"band_lo":lo,"band_hi":hi,"issue_price":price}
    threshold = float(observed_floor) / 10 if observed_floor is not None else None
    reason=validate_issue_economics(values, threshold)
    if not reason and face and hi and threshold is None: reason="source_invalid_unit:face_band_reference_unavailable"
    classifications=[]
    if reason: classifications.append(reason.split(":",1)[-1])
    if threshold is not None and face and hi and hi / face < threshold: classifications.append("suspected_scale_suffix_loss")
    return {"ipo_id":ipo_id,"isin":isin,"symbol":symbol,"face_value":face,"band_lo":lo,
            "band_hi":hi,"issue_price":price,"inconsistency_reason":reason,
            "classifications":classifications,"source_provenance":source,"stored_official_raw":raw,
            "persisted_derived_affected":{"gap_pct":gap,"pool":pool,"winner_35":winner}}

def select_candidates(conn, limit=MAX_ROWS):
    cur=conn.cursor(); cur.execute("""WITH stats AS (SELECT percentile_cont(0.01) WITHIN GROUP
      (ORDER BY band_hi/face_value) AS observed_floor FROM ipo_issue WHERE face_value>0 AND band_hi>=face_value)
      SELECT i.id,i.isin,i.symbol,ii.face_value,ii.band_lo,ii.band_hi,ii.issue_price,
      sf.source,raw.value,lo.gap_pct,lo.pool,lo.winner_35,stats.observed_floor
      FROM ipo i JOIN ipo_issue ii ON ii.ipo_id=i.id CROSS JOIN stats
      LEFT JOIN listing_outcomes lo ON lo.ipo_id=i.id
      LEFT JOIN LATERAL (SELECT source FROM source_facts WHERE ipo_id=i.id AND field IN ('band_lo','band_hi') ORDER BY created_at DESC LIMIT 1) sf ON true
      LEFT JOIN LATERAL (SELECT value FROM source_facts WHERE ipo_id=i.id AND field='official_price_range_raw' ORDER BY created_at DESC LIMIT 1) raw ON true
      WHERE ii.band_lo IS NOT NULL OR ii.band_hi IS NOT NULL ORDER BY i.id DESC LIMIT %s""",(min(MAX_ROWS,limit),))
    return [classify(row) for row in cur.fetchall() if classify(row)["inconsistency_reason"]]

def official_evidence(session, symbol):
    try:
        response=session.get(API.format(sym=symbol),headers=HEADERS,timeout=15)
        if response.status_code != 200: return {"status":"official_source_unavailable","http_status":response.status_code}
        record,extras,notes=parse_issue_info(response.json())
        raw=extras.get("official_price_range_raw")
        if not raw or "band_lo" not in record or "band_hi" not in record:
            return {"status":"source_invalid_unit","raw":raw,"notes":notes}
        return {"status":"verified","raw":raw,"proposed":{"band_lo":record["band_lo"],"band_hi":record["band_hi"]},"notes":notes}
    except Exception as exc:
        return {"status":"official_source_unavailable","error_class":type(exc).__name__}

def apply_verified(conn, item, evidence):
    if evidence.get("status")!="verified": raise RuntimeError("official feed evidence required")
    proposed=evidence["proposed"]
    invalid=validate_issue_economics({**item,**proposed})
    if invalid: raise RuntimeError(invalid)
    identity_field="isin" if item.get("isin") else "symbol"; identity=item.get(identity_field)
    if not identity: raise RuntimeError("exact stable identity unavailable")
    cur=conn.cursor(); cur.execute(f"""UPDATE ipo_issue ii SET band_lo=%s,band_hi=%s,updated_at=now()
      FROM ipo i WHERE ii.ipo_id=i.id AND i.id=%s AND i.{identity_field}=%s
      AND (ii.band_lo IS DISTINCT FROM %s OR ii.band_hi IS DISTINCT FROM %s)""",
      (proposed["band_lo"],proposed["band_hi"],item["ipo_id"],identity,proposed["band_lo"],proposed["band_hi"]))
    changed=cur.rowcount==1
    if changed:
        from fill_ipo import _log_fact
        source="owner_repair:nse-official-price-range:v1"
        _log_fact(cur,item["ipo_id"],"band_lo",proposed["band_lo"],source)
        _log_fact(cur,item["ipo_id"],"band_hi",proposed["band_hi"],source)
        _log_fact(cur,item["ipo_id"],"official_price_range_raw",evidence["raw"],source)
    conn.commit(); return changed

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--write",action="store_true"); ap.add_argument("--owner-approval"); ap.add_argument("--limit",type=int,default=MAX_ROWS); args=ap.parse_args(argv)
    if args.write and args.owner_approval != APPROVAL: raise SystemExit(f"--owner-approval={APPROVAL} required")
    import psycopg2
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=25,options="-c statement_timeout=30000 -c lock_timeout=5000")
    try:
        candidates=select_candidates(conn,args.limit)
        try:
            from curl_cffi import requests
            session=prime(requests,sleep=lambda *_:None)
        except Exception: session=None
        changed=0; report=[]
        for item in candidates:
            evidence=official_evidence(session,item["symbol"]) if session else {"status":"official_source_unavailable"}
            if evidence["status"] == "official_source_unavailable": item["classifications"].append("official_source_unavailable")
            item.update(official_raw_value=evidence.get("raw"),proposed_normalized_values=evidence.get("proposed"),official_status=evidence["status"])
            if args.write: changed += int(apply_verified(conn,item,evidence))
            report.append(item)
        print(json.dumps({"mode":"write" if args.write else "preview","rows":report,"totals":{"candidates":len(report),"proposed":sum(bool(x.get('proposed_normalized_values')) for x in report),"changed":changed},"recompute_preview":"python pipeline/kite_fetch.py --ids <verified_ids> --dry-run"},default=str,sort_keys=True))
    finally: conn.close()

if __name__=="__main__": main()
