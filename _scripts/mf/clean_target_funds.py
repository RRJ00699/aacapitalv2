import pandas as pd
from pathlib import Path


class MFHoldingsCleaner:

    INPUT = Path("data/mf_holdings/mf_holdings_ready.csv")
    OUTPUT = Path("data/mf_holdings/mf_holdings_final.csv")

    TARGET_FUNDS = {
        "NIPPON INDIA SMALL CAP FUND": {
            "amc": "Nippon India Mutual Fund",
            "scheme": "Nippon India Small Cap Fund",
        },
        "NIPPON INDIA GROWTH FUND": {
            "amc": "Nippon India Mutual Fund",
            "scheme": "Nippon India Growth Fund",
        },
        "HDFC MID CAP": {
            "amc": "HDFC Mutual Fund",
            "scheme": "HDFC Mid Cap Fund",
        },
        "SBI SMALL CAP": {
            "amc": "SBI Mutual Fund",
            "scheme": "SBI Small Cap Fund",
        },
        "SBI MID CAP": {
            "amc": "SBI Mutual Fund",
            "scheme": "SBI Mid Cap Fund",
        },
        "PARAG PARIKH FLEXI CAP": {
            "amc": "PPFAS Mutual Fund",
            "scheme": "Parag Parikh Flexi Cap Fund",
        },
        "QUANT SMALL CAP": {
            "amc": "quant Mutual Fund",
            "scheme": "quant Small Cap Fund",
        },
        "QUANT MID CAP": {
            "amc": "quant Mutual Fund",
            "scheme": "quant Mid Cap Fund",
        },
        "CANARA ROBECO SMALL CAP": {
            "amc": "Canara Robeco Mutual Fund",
            "scheme": "Canara Robeco Small Cap Fund",
        },
        "CANARA ROBECO MID CAP": {
            "amc": "Canara Robeco Mutual Fund",
            "scheme": "Canara Robeco Mid Cap Fund",
        },
    }

    def load(self):
        return pd.read_csv(self.INPUT)

    def normalize_month(self, df):
        df["month"] = pd.to_datetime(df["month"])
        df["month"] = df["month"].dt.to_period("M").dt.to_timestamp()
        return df

    def remove_bad_rows(self, df):
        df = df[df["isin"].notna()]
        df = df[df["quantity"].notna()]
        df = df[df["market_value_cr"].notna()]
        df = df[df["quantity"] > 0]
        df = df[df["market_value_cr"] > 0]
        return df

    def remove_debt_rows(self, df):

        debt_keywords = [
            "NCD",
            "BOND",
            "TREASURY",
            "T-BILL",
            "COMMERCIAL PAPER",
            "CERTIFICATE OF DEPOSIT",
            "CD ",
            "CP ",
            "SDL",
        ]

        pattern = "|".join(debt_keywords)

        return df[
            ~df["stock_name"]
            .astype(str)
            .str.upper()
            .str.contains(pattern, na=False)
        ]

    def classify_target_funds(self, df):

        scheme_upper = df["scheme_name"].astype(str).str.upper()

        cleaned = []

        for key, meta in self.TARGET_FUNDS.items():

            mask = scheme_upper.str.contains(key, na=False)

            subset = df[mask].copy()

            if subset.empty:
                continue

            subset["amc_name"] = meta["amc"]
            subset["scheme_name"] = meta["scheme"]

            cleaned.append(subset)

        return pd.concat(cleaned, ignore_index=True)

    def dedupe(self, df):

        return df.drop_duplicates(
            subset=[
                "month",
                "amc_name",
                "scheme_name",
                "isin",
            ],
            keep="last",
        )

    def validate(self, df):

        print("\nRows:", len(df))

        print("\nAMC Counts")
        print(df["amc_name"].value_counts())

        print("\nScheme Counts")
        print(df["scheme_name"].value_counts())

        print("\nMonth Range")
        print(df["month"].min(), "->", df["month"].max())

        print("\nDuplicates")

        dupes = df.duplicated(
            ["month", "scheme_name", "isin"],
            keep=False,
        ).sum()

        print(dupes)

    def save(self, df):

        df.to_csv(self.OUTPUT, index=False)

        print("\nSaved:")
        print(self.OUTPUT)

    def run(self):

        df = self.load()

        df = self.normalize_month(df)

        df = self.remove_bad_rows(df)

        df = self.remove_debt_rows(df)

        df = self.classify_target_funds(df)

        df = self.dedupe(df)

        self.validate(df)

        self.save(df)


if __name__ == "__main__":
    MFHoldingsCleaner().run()