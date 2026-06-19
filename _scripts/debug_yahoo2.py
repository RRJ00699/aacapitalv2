from yahooquery import Ticker
import pandas as pd

ticker = "0P0000XVFY.BO"
fund = Ticker(ticker)

# Test fund_top_holdings
df = fund.fund_top_holdings
print("fund_top_holdings type:", type(df))
print("fund_top_holdings:")
print(df)
print()
print("Index type:", type(df.index))
print("Columns:", df.columns.tolist() if hasattr(df, 'columns') else "no columns")
print()

# Reset index and show
df2 = df.reset_index()
print("After reset_index:")
print(df2.head(5))
print("Columns after reset:", df2.columns.tolist())
