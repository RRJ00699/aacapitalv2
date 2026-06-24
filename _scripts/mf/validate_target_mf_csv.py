import pandas as pd
from pathlib import Path

CSV = Path("data/mf_holdings/mf_holdings_targets_only.csv")
df = pd.read_csv(CSV)

print("ROWS:", len(df))
print("\nAMC counts")
print(df["amc_name"].value_counts())

print("\nScheme counts")
print(df["scheme_name"].value_counts())

print("\nMonth range")
print(df["month"].min(), "to", df["month"].max())

print("\nBad ISIN rows")
print(len(df[~df["isin"].astype(str).str.startswith("INE")]))

print("\nNull checks")
print(df[["month","amc_name","scheme_name","stock_name","isin","quantity","market_value_cr"]].isna().sum())

print("\nPortfolio weight sums")
print(
    df.groupby(["month","amc_name","scheme_name"])["portfolio_weight_pct"]
      .sum()
      .reset_index()
      .sort_values("portfolio_weight_pct", ascending=False)
      .head(50)
)