import os
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("DATABASE_URL")
CSV = Path("data/mf_holdings/mf_holdings_targets_only.csv")
TABLE = "mf_scheme_holdings"

if not DATABASE_URL:
    raise Exception("DATABASE_URL missing")

df = pd.read_csv(CSV)

df = df[
    [
        "month",
        "amc_name",
        "scheme_name",
        "stock_name",
        "isin",
        "sector",
        "nse_symbol",
        "quantity",
        "market_value_cr",
        "portfolio_weight_pct",
        "market_value_lakh",
    ]
]

engine = create_engine(DATABASE_URL)

df.to_sql(
    TABLE,
    engine,
    if_exists="append",
    index=False,
    chunksize=5000,
)

print("Loaded rows:", len(df))