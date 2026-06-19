from yahooquery import Ticker

ticker = "0P0000XVFY.BO"
fund = Ticker(ticker)

# Check what fund_equity_holdings actually returns
h = fund.fund_equity_holdings
print("Type:", type(h))
if isinstance(h, dict):
    for k, v in h.items():
        print(f"Key: {k}")
        print(f"Value type: {type(v)}")
        print(f"Value: {v}")

# Try other methods
print("\n--- fund_holding_info ---")
h2 = fund.fund_holding_info
print(type(h2))
if isinstance(h2, dict):
    for k, v in h2.items():
        print(f"  {k}: {str(v)[:200]}")

print("\n--- fund_top_holdings ---")
h3 = fund.fund_top_holdings
print(type(h3))
print(str(h3)[:300])

print("\n--- Available attributes ---")
print([a for a in dir(fund) if 'fund' in a.lower() or 'hold' in a.lower()])
