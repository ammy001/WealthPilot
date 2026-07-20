"""Pure portfolio rebalance math — no external data.

portfolio_calc(allocation, changes) where allocation/changes map asset -> INR amount.
Returns before/after percentages and validates (no negative, positive total).
"""


def portfolio_calc(allocation: dict, changes: dict | None = None) -> dict:
    if not allocation:
        return {"error": "current allocation is required"}
    changes = changes or {}
    before_total = sum(allocation.values())
    if before_total <= 0:
        return {"error": "current allocation total must be positive"}

    after = dict(allocation)
    for asset, delta in changes.items():
        after[asset] = after.get(asset, 0.0) + delta

    negatives = [a for a, amt in after.items() if amt < -1e-6]
    if negatives:
        return {"error": f"change would make {', '.join(negatives)} negative"}

    after_total = sum(after.values())
    return {
        "before_pct": {a: round(v / before_total * 100, 1) for a, v in allocation.items()},
        "after_amounts": {a: round(v, 2) for a, v in after.items()},
        "after_pct": {a: round(v / after_total * 100, 1) for a, v in after.items()},
        "before_total": round(before_total, 2),
        "after_total": round(after_total, 2),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(portfolio_calc(
        {"equity": 60000, "debt": 35000, "gold": 5000},
        {"debt": -5000, "equity": 5000}), indent=2))
    print(json.dumps(portfolio_calc({"equity": 100}, {"equity": -200}), indent=2))  # error
