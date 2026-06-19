# AA Capital IPO Patch

Replace these two files in:

```txt
C:\aacapital-v2\_scripts\ipo\
```

Files:

```txt
ipo_similarity_engine.py
ipo_decision_engine.py
```

Then run:

```powershell
cd C:\aacapital-v2

python _scripts/ipo/ipo_similarity_engine.py
python _scripts/ipo/ipo_listing_probability_engine.py
python _scripts/ipo/ipo_run_quality_decision.py
```

What this fixes:

1. `ipo_similarity_engine.py`
   - Preserves `ipo_id` after pandas merge.
   - Fixes `KeyError: 'ipo_id'`.

2. `ipo_decision_engine.py`
   - Casts `decision_reasons` and `reasons` to JSONB during update.
   - Fixes PostgreSQL `DatatypeMismatch`.
