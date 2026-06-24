import pandas as pd
from pathlib import Path

CSV = Path("data/mf_holdings/mf_holdings_ready.csv")

df = pd.read_csv(CSV)

print("ROWS:", len(df))
print("COLUMNS:", df.columns.tolist())

print("\nAMC counts")
print(df["amc_name"].value_counts())

print("\nScheme counts top 30")
print(df["scheme_name"].value_counts().head(30))

print("\nMonth range")
print(df["month"].min(), "to", df["month"].max())

print("\nRows per month")
print(df.groupby("month").size().tail(24))

print("\nNull checks")
print(df[["month","amc_name","scheme_name","stock_name","isin","quantity","market_value_cr"]].isna().sum())

print("\nBad ISIN rows")
bad_isin = df[~df["isin"].astype(str).str.startswith("INE")]
print(len(bad_isin))
print(bad_isin.head(20))

print("\nNegative/zero quantity")
bad_qty = df[df["quantity"].fillna(0) <= 0]
print(len(bad_qty))
print(bad_qty.head(20))

print("\nTop holdings by portfolio weight")
print(
    df.sort_values("portfolio_weight_pct", ascending=False)
      [["month","amc_name","scheme_name","stock_name","isin","portfolio_weight_pct"]]
      .head(30)
)

print("\nDuplicate keys")
dupes = df[df.duplicated(["month","amc_name","scheme_name","isin","stock_name"], keep=False)]
print(len(dupes))
print(dupes.head(30))

print("\nPortfolio weight sum sample")
sample = (
    df.groupby(["month","amc_name","scheme_name"])["portfolio_weight_pct"]
      .sum()
      .reset_index()
      .sort_values("portfolio_weight_pct", ascending=False)
)
print(sample.head(30))
print(sample.tail(30))