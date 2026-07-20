import pandas as pd
from pathlib import Path

INPUT = Path("data/mf_holdings/mf_holdings_ready.csv")
OUTPUT = Path("data/mf_holdings/mf_holdings_targets_only.csv")

TARGET_KEYWORDS = [
    "hdfc small cap",
    "hdfc mid-cap opportunities",
    "hdfc mid cap opportunities",

    "canara robeco small cap",
    "canara robeco mid cap",
    "canara robeco midcap",

    "parag parikh flexi cap",
    "ppfas flexi cap",

    "sbi small cap",
    "sbi magnum midcap",
    "sbi midcap",

    "quant small cap",
    "quant mid cap",

    "nippon india small cap",
    "nippon india growth",
]

df = pd.read_csv(INPUT)

df["scheme_name_clean"] = df["scheme_name"].astype(str).str.lower()

mask = False
for k in TARGET_KEYWORDS:
    mask = mask | df["scheme_name_clean"].str.contains(k, regex=False)

out = df[mask].copy()

out = out.drop(columns=["scheme_name_clean"])

out = out.drop_duplicates(
    subset=["month", "amc_name", "scheme_name", "isin", "stock_name"],
    keep="last",
)

out.to_csv(OUTPUT, index=False)

print("Input rows:", len(df))
print("Target rows:", len(out))
print("\nAMC counts:")
print(out["amc_name"].value_counts())
print("\nScheme counts:")
print(out["scheme_name"].value_counts())
print("\nSaved:", OUTPUT)