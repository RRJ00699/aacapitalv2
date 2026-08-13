"""Canonical structured IPO-equity universe predicate (no name matching)."""

# NSE issue_type is the structured discriminator. NULL is retained because older
# mainboard equities predate this enrichment; explicit REIT/InvIT types are excluded.
SQL = """COALESCE(i.is_mainboard,FALSE)=TRUE AND NOT EXISTS (
  SELECT 1 FROM ipo_issue universe_issue WHERE universe_issue.ipo_id=i.id
  AND upper(trim(COALESCE(universe_issue.issue_type,''))) IN ('REIT','INVIT'))"""
