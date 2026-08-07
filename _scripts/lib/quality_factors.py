"""Canonical pure Quality Score factor definitions shared by production and research."""

TIER1 = ("kotak", "icici", "axis", "jm financial", "citigroup", "morgan stanley",
         "goldman", "jefferies", "bofa", "nomura", "motilal")


def fnum(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def factors(row):
    (rhp, qp, pledge, ofs_cr, fresh_cr, ipo_pe, peer_pe,
     roe, cagr, de, sbi, brlm) = row
    pledge, ofs_cr, fresh_cr = fnum(pledge), fnum(ofs_cr), fnum(fresh_cr)
    ipo_pe, peer_pe, roe, cagr, de = (fnum(v) for v in (ipo_pe, peer_pe, roe, cagr, de))
    result = {}
    gate = litigation = integrity = related = concentration = None
    if rhp:
        db = (rhp.get("db_fields") or {}) if isinstance(rhp, dict) else {}
        gate = db.get("quality_gate")
        litigation = db.get("criminal_litigation")
        integrity = db.get("numbers_integrity_flag")
        related = db.get("related_party_concern")
        concentration = db.get("customer_concentration_high")
    result["rhp_gate"] = 20 if gate == "clean" else 8 if gate == "watch" else 0 if gate else None
    result["no_criminal"] = None if litigation is None else (6 if litigation is False else 0)
    result["numbers_ok"] = None if integrity is None else (5 if integrity in ("ok", "clean") else 0)
    result["related_ok"] = None if related is None else (4 if related in (False, "none", None) else 0)
    result["concentration_ok"] = None if concentration is None else (5 if concentration is False else 0)
    result["promoter_quality"] = None if qp is None else (10 if qp else 0)
    result["pledge_low"] = None if pledge is None else (5 if pledge < 5 else 0)
    total = (ofs_cr or 0) + (fresh_cr or 0)
    ofs_pct = (ofs_cr / total * 100) if (total and ofs_cr is not None) else None
    result["structure"] = None if ofs_pct is None else (10 if ofs_pct < 20 else 5 if ofs_pct <= 60 else 0)
    ratio = (ipo_pe / peer_pe) if (ipo_pe and peer_pe and peer_pe > 0) else None
    result["valuation"] = None if ratio is None else (10 if ratio < .8 else 6 if ratio <= 1.2 else 3 if ratio <= 1.5 else 0)
    result["roe"] = None if roe is None else (5 if roe >= 18 else 0)
    result["cagr"] = None if cagr is None else (4 if cagr >= 20 else 0)
    result["de"] = None if de is None else (3 if de <= .5 else 0)
    result["sbi"] = None if not sbi else (5 if "subscribe" in str(sbi).lower() else 0)
    result["brlm_t1"] = None if not brlm else (3 if any(t in str(brlm).lower() for t in TIER1) else 0)
    weights = [("rhp_gate",20),("no_criminal",6),("numbers_ok",5),("related_ok",4),
               ("concentration_ok",5),("promoter_quality",10),("pledge_low",5),
               ("structure",10),("valuation",10),("roe",5),("cagr",4),("de",3),
               ("sbi",5),("brlm_t1",3)]
    available_weight = sum(weight for key, weight in weights if result[key] is not None)
    points = sum(value for value in result.values() if value is not None)
    score = round(points / available_weight * 100) if available_weight else None
    confidence = min(100, round(available_weight / 85 * 100))
    return result, score, confidence
