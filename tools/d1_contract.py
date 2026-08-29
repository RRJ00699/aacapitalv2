"""D1 lifecycle semantics; universe eligibility reuses the production predicate."""
from pipeline.nse_fetch import canonical_spine_eligible

LIFECYCLE_ORDER = {
    "ANNOUNCED": 0, "UPCOMING": 1, "OPEN": 2, "CLOSED": 3,
    "ALLOTTED": 4, "LISTED": 5, "WITHDRAWN": -1,
}
CONCEPT_DUE_AT = {
    "issue": "ANNOUNCED",
    "documents": "UPCOMING",
    "subscription": "CLOSED",
    "allotment": "ALLOTTED",
    "market": "LISTED",
}

def normalize_status(value):
    status=str(value or "ANNOUNCED").strip().upper()
    if status not in LIFECYCLE_ORDER: raise ValueError(f"invalid IPO lifecycle status: {status}")
    return status

_MISSING=object()

def concept_state(status, concept, value=_MISSING, failed=False):
    """Return NOT_DUE/PRESENT/FAILED/MISSING; numeric zero is still PRESENT."""
    status=normalize_status(status)
    if concept not in CONCEPT_DUE_AT: raise KeyError(concept)
    if status=="WITHDRAWN" or LIFECYCLE_ORDER[status] < LIFECYCLE_ORDER[CONCEPT_DUE_AT[concept]]:
        return "NOT_DUE"
    if failed:return "FAILED"
    return "PRESENT" if value is not _MISSING else "MISSING"

__all__=("canonical_spine_eligible","concept_state","normalize_status")
