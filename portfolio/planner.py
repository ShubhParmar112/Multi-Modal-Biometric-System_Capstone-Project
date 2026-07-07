"""
Smart investment planner - turns a recommended allocation (percentages)
plus the user's available balance into a concrete, executable plan:
whole-share counts for exchange-traded picks, fractional units for
mutual funds, and rupee amounts for FD/cash. Whatever the integer
rounding leaves uninvested is reported per bucket and rolled up.
"""

import math

from portfolio import specific_picks

# How many picks a bucket's money is split across (equally). Keeps the
# plan practical instead of spraying tiny amounts over every pick.
ITEMS_PER_BUCKET = 3

BUCKET_LABELS = {
    "equity": "Equity", "mutual_funds": "Mutual Funds", "gold": "Gold",
    "debt": "Debt", "fd": "Fixed Deposit", "cash": "Cash",
}


def _whole_unit_items(rows: list, bucket_amount: float) -> tuple:
    """Split bucket_amount equally over rows, buying whole units of each.
    Returns (items, leftover)."""
    rows = [r for r in rows if r.get("price")][:ITEMS_PER_BUCKET]
    if not rows:
        return [], bucket_amount

    per_item = bucket_amount / len(rows)
    items, leftover = [], 0.0
    for row in rows:
        price = float(row["price"])
        units = math.floor(per_item / price)
        cost = round(units * price, 2)
        leftover += per_item - cost
        items.append({
            "name":   row["name"],
            "ticker": row.get("ticker"),
            "price":  round(price, 2),
            "units":  units,
            "cost":   cost,
        })
    return items, leftover


def _mutual_fund_items(rows: list, bucket_amount: float) -> tuple:
    """Mutual funds allow fractional units, so the full amount is invested."""
    rows = [r for r in rows if r.get("nav")][:ITEMS_PER_BUCKET]
    if not rows:
        return [], bucket_amount

    per_item = bucket_amount / len(rows)
    items = []
    for row in rows:
        nav = float(row["nav"])
        items.append({
            "name":  row["name"],
            "ticker": None,
            "price": round(nav, 2),
            "units": round(per_item / nav, 2),
            "cost":  round(per_item, 2),
        })
    return items, 0.0


def build_plan(allocation: dict, amount: float, risk_appetite: str) -> dict:
    """
    allocation: dict with <asset>_pct keys (a portfolio_recommendations row).
    amount:     rupees to deploy (the profile's available_balance).
    """
    picks = specific_picks.get_all_picks(risk_appetite)
    fd_rows = picks.get("fd") or []
    best_fd = fd_rows[0] if fd_rows else None

    buckets, total_invested, total_leftover = [], 0.0, 0.0
    for asset, label in BUCKET_LABELS.items():
        pct = float(allocation.get(f"{asset}_pct", 0.0) or 0.0)
        if pct <= 0:
            continue
        bucket_amount = amount * pct / 100.0

        if asset == "mutual_funds":
            items, leftover = _mutual_fund_items(picks.get("mutual_funds") or [],
                                                 bucket_amount)
        elif asset in ("equity", "gold", "debt"):
            items, leftover = _whole_unit_items(picks.get(asset) or [],
                                                bucket_amount)
        elif asset == "fd":
            note = (f"Best live rate: {best_fd['bank']} "
                    f"({best_fd['rate_regular']})" if best_fd else None)
            items = [{"name": note or "Any DICGC-insured bank FD",
                      "ticker": None, "price": None, "units": None,
                      "cost": round(bucket_amount, 2)}]
            leftover = 0.0
        else:  # cash
            items = [{"name": "Keep liquid (savings / sweep-in)",
                      "ticker": None, "price": None, "units": None,
                      "cost": round(bucket_amount, 2)}]
            leftover = 0.0

        invested = round(sum(i["cost"] for i in items), 2)
        total_invested += invested
        total_leftover += leftover
        buckets.append({
            "asset":       asset,
            "label":       label,
            "pct":         pct,
            "amount":      round(bucket_amount, 2),
            "invested":    invested,
            "uninvested":  round(leftover, 2),
            "items":       items,
        })

    return {
        "total_amount":     round(amount, 2),
        "total_invested":   round(total_invested, 2),
        "total_uninvested": round(total_leftover, 2),
        "risk_appetite":    risk_appetite,
        "buckets":          buckets,
    }
