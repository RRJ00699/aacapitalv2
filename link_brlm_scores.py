"""
Links brlm_scores table -> ipo_intelligence.brlm_score and recalibrates scores.
Step 3 matcher rewritten: normalized + fuzzy, so short names (JM, BOI, IIFL) and
suffix variants ("ICICI Securities" vs "ICICI Securities Ltd.") link correctly.
"""
import psycopg2, os, re
from difflib import SequenceMatcher

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ── Step 1: Recalibrate BRLM scores ───────────────────────────────────────────
print("Recalibrating BRLM scores...")
cur.execute("SELECT brlm_name, avg_listing, pct_negative, ipo_count FROM brlm_scores")
brlms = cur.fetchall()
for brlm_name, avg_listing, pct_neg, n_ipos in brlms:
    avg = float(avg_listing or 0); pct_neg_val = float(pct_neg or 0); n = int(n_ipos or 1)
    if avg >= 50:   base = 90
    elif avg >= 30: base = 78
    elif avg >= 15: base = 65
    elif avg >= 5:  base = 50
    else:           base = 35
    if n >= 20:   base += 5
    elif n >= 10: base += 3
    elif n <= 2:  base -= 10
    if pct_neg_val > 40:   base -= 20
    elif pct_neg_val > 25: base -= 10
    elif pct_neg_val > 15: base -= 5
    score = max(20, min(98, base))
    cur.execute("UPDATE brlm_scores SET score = %s WHERE brlm_name = %s", (score, brlm_name))
conn.commit()
print(f"  Recalibrated {len(brlms)} BRLM scores")

print("\nTop 15 BRLMs after recalibration:")
cur.execute("SELECT brlm_name, score, avg_listing, ipo_count, pct_negative FROM brlm_scores ORDER BY score DESC LIMIT 15")
for r in cur.fetchall():
    print(f"  {r[0][:35]:35s} score:{r[1]:.0f} avg:{r[2]:.1f}% n:{r[3]} neg:{r[4]:.0f}%")

# ── Step 3: Link scores to ipo_intelligence (normalized fuzzy matcher) ─────────
print("\nLinking BRLM scores to ipo_intelligence...")

STOP = {"ltd", "limited", "pvt", "private", "co", "company", "llp", "the", "india",
        "indian", "and", "&"}

def normalize(name):
    s = re.sub(r"[^a-z0-9\s]", " ", str(name).lower())
    toks = [t for t in s.split() if t and t not in STOP]
    return " ".join(toks), set(toks)

cur.execute("SELECT brlm_name, score, avg_listing FROM brlm_scores")
db = []
for nm, sc, gn in cur.fetchall():
    norm, toks = normalize(nm)
    if norm:
        db.append({"orig": nm, "score": sc, "gain": gn, "norm": norm, "toks": toks})

def best_match(token):
    """Return (score, gain) for the best DB manager matching this name token, or None."""
    qn, qt = normalize(token)
    if not qn:
        return None
    best, best_r = None, 0.0
    for d in db:
        # 1) exact normalized
        if qn == d["norm"]:
            return (d["score"], d["gain"])
        # 2) containment (one inside the other), guard against tiny fragments
        if len(qn) >= 4 and (qn in d["norm"] or d["norm"] in qn):
            r = 0.95
        else:
            # 3) token overlap (Jaccard) + 4) fuzzy ratio, take the stronger signal
            inter = qt & d["toks"]
            jac = len(inter) / len(qt | d["toks"]) if (qt | d["toks"]) else 0
            ratio = SequenceMatcher(None, qn, d["norm"]).ratio()
            # a shared distinctive token (>=4 chars) is a strong signal on its own
            strong_tok = any(len(t) >= 4 for t in inter)
            r = max(ratio, jac + (0.25 if strong_tok else 0))
        if r > best_r:
            best_r, best = r, (d["score"], d["gain"])
    return best if best_r >= 0.72 else None

cur.execute("SELECT id, brlm_names FROM ipo_intelligence WHERE brlm_names IS NOT NULL AND brlm_names != ''")
ipos = cur.fetchall()

matched, unmatched_samples = 0, []
for ipo_id, brlm_names in ipos:
    best_score = best_gain = None
    any_token_unmatched = None
    for bname in re.split(r"[,;/&]", str(brlm_names)):
        bname = bname.strip()
        if not bname:
            continue
        m = best_match(bname)
        if m:
            s, g = m
            if best_score is None or s > best_score:
                best_score, best_gain = s, g
        else:
            any_token_unmatched = bname
    if best_score is not None:
        cur.execute("UPDATE ipo_intelligence SET brlm_score=%s, brlm_avg_listing_gain=%s WHERE id=%s",
                    (best_score, best_gain, ipo_id))
        matched += 1
    elif any_token_unmatched and len(unmatched_samples) < 12:
        unmatched_samples.append(any_token_unmatched)

conn.commit()
print(f"  Linked {matched}/{len(ipos)} IPOs to BRLM scores")
if unmatched_samples:
    print("  Sample still-unmatched names (for tuning):")
    for s in unmatched_samples:
        print(f"    - {s}")

conn.close()
