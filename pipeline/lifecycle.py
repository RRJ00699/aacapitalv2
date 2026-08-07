"""Pure, per-IPO lifecycle planning for the forward IPO pipeline."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class IPOWindow:
    ipo_id: int
    symbol: str | None
    name: str
    open_date: dt.date | None
    close_date: dt.date | None
    listing_date: dt.date | None
    issue_complete: bool = False
    anchor_banked: bool = False
    final_subscription_banked: bool = False


@dataclass(frozen=True)
class IPOPlan:
    ipo: IPOWindow
    actions: tuple[str, ...]


def plan_ipo(ipo: IPOWindow, today: dt.date) -> IPOPlan:
    """Select only actions whose source can have changed for this IPO today."""
    actions: list[str] = []
    if (ipo.symbol and not ipo.issue_complete
            and (ipo.listing_date is None or today <= ipo.listing_date)):
        actions.append("nse_issue_metadata")
    if (ipo.symbol and ipo.open_date and ipo.close_date
            and ipo.open_date <= today <= ipo.close_date):
        if today < ipo.close_date:
            actions.append("subscription_forward")
        elif not ipo.final_subscription_banked:
            actions.append("subscription_final")
    anchor_from = ipo.open_date - dt.timedelta(days=1) if ipo.open_date else None
    if (ipo.symbol and not ipo.anchor_banked and anchor_from and today >= anchor_from
            and (ipo.listing_date is None or today <= ipo.listing_date)):
        actions.append("anchor_discovery")
    if ipo.listing_date == today:
        actions.append("preopen_capture")
    return IPOPlan(ipo, tuple(actions))


def plan_run(ipos: list[IPOWindow], today: dt.date) -> list[IPOPlan]:
    """Plan all IPOs independently; input order and concurrency do not leak actions."""
    return [plan_ipo(ipo, today) for ipo in ipos]
