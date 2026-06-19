# AA Capital IPO Similarity + Probability Engine

Copy these files into:

```txt
C:\aacapital-v2\_scripts\ipo\
```

Files:

```txt
ipo_live_feed.py
ipo_similarity_engine.py
ipo_listing_probability_engine.py
ipo_run_all.py
```

Run from project root:

```powershell
cd C:\aacapital-v2

python _scripts/ipo/ipo_run_all.py
```

Expected flow:

```txt
ipo_live_feed.py
  -> truncates and rebuilds ipo_live_feed from ipo_historical_results only

ipo_similarity_engine.py
  -> creates ipo_similarity_results
  -> creates top 7 similar IPOs per IPO

ipo_listing_probability_engine.py
  -> creates/updates ipo_predictions
  -> calculates LQI, P(>10%), P(>20%), P(loss), expected return, confidence, APPLY/WATCH/AVOID
```

Important expected counts with your current DB:

```txt
ipo_master = 944
ipo_historical_results = 330
ipo_live_feed = 330
ipo_similarity_results = about 6600
ipo_predictions = 944
```

The current historical data supports 330 IPOs with GMP/subscription/listing result data.
The remaining master IPOs will still get baseline predictions, but with lower confidence until live or historical features exist.
