from pipeline.completeness import FINANCIAL_FIELDS, SUBSCRIPTION_FIELDS, retry_lane, summarize_requirements


def fields(table, columns):
    return [f"{table}.{column}" for column in columns]


def test_no_financial_row_and_partial_row_have_fixed_denominator_and_exact_gaps():
    required = fields("financial_statements", FINANCIAL_FIELDS)
    absent = summarize_requirements([], required, {})
    partial_present = required[:2]
    partial_missing = required[2:]
    partial = summarize_requirements(partial_present, partial_missing, {})
    assert absent == {"required_present": 0, "required_total": 5,
                      "completeness_pct": 0.0, "retry_lanes": ["RHP"]}
    assert partial["required_total"] == 5
    assert partial["completeness_pct"] == 40.0
    assert partial_missing == ["financial_statements.pat", "financial_statements.net_worth",
                               "financial_statements.total_debt"]


def test_partial_to_more_complete_is_monotonic_with_exact_lane_ownership():
    required = fields("financial_statements", FINANCIAL_FIELDS)
    partial = summarize_requirements(required[:1], required[1:], {})
    more = summarize_requirements(required[:4], required[4:], {})
    assert more["required_total"] == partial["required_total"] == 5
    assert more["completeness_pct"] > partial["completeness_pct"]
    assert more["retry_lanes"] == ["RHP"]


def test_subscription_no_row_to_partial_is_fixed_and_pending_stays_in_denominator():
    required = fields("subscription_snapshots", SUBSCRIPTION_FIELDS)
    absent = summarize_requirements([], required, {})
    partial = summarize_requirements(required[:3], required[3:], {})
    pending = summarize_requirements([], [], {field: "issue not closed yet" for field in required})
    assert absent["required_total"] == partial["required_total"] == pending["required_total"] == 7
    assert partial["completeness_pct"] == 42.9
    assert partial["retry_lanes"] == ["NSE lifecycle", "anchor"]
    assert pending["completeness_pct"] == 0.0 and pending["retry_lanes"] == []
    assert retry_lane("subscription_snapshots.anchor_count") == "anchor"
