# AA Capital IPO Feature Quality Gate + Decision Engine

Copy these files into:

```txt
C:\aacapital-v2\_scripts\ipo\
```

Files:

```txt
ipo_feature_store.py
ipo_decision_engine.py
ipo_run_quality_decision.py
```

Run after your existing live feed, similarity, and probability engines:

```powershell
cd C:\aacapital-v2
python _scripts/ipo/ipo_run_quality_decision.py
```

This creates/updates:

```txt
ipo_feature_store
ipo_predictions.final_decision
ipo_predictions.final_confidence
ipo_predictions.feature_quality_score
ipo_predictions.feature_quality_bucket
ipo_predictions.apply_eligible
ipo_predictions.decision_reasons
```

The decision engine also updates the legacy columns `decision`, `confidence`, and `reasons`, so the existing UI/API should keep working.

Feature quality score:

```txt
live_feed       15
gmp             20
subscription    25
similarity      20
sector_history   8
issue_price      5
issue_size       5
symbol           2
```

APPLY eligibility requires:

```txt
feature_quality_score >= 70
has_gmp = true
has_subscription = true
has_similarity = true
```

The decision engine prints validation output:

```txt
Final decision summary
Top 25 APPLY
Top 25 WATCH
Top 25 AVOID
```
