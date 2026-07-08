"""
Holdings-based Markowitz optimizer - mean-variance optimization across the
securities the user actually owns, driven entirely by the data layer:
holdings from portfolio_holdings and return statistics from the locally
stored daily_prices history (populate via HoldingsService.refresh_prices).
Long-only, fully invested, max-Sharpe objective, with the same per-asset
weight cap as the asset-class optimizer (config.PORTFOLIO_MAX_WEIGHT) so
the result is never concentrated in a single holding. Pure computation —
no network calls.
"""

import math
from typing import Optional

import numpy as np
from scipy.optimize import minimize

import config
from database.db_manager import DatabaseManager
from portfolio.holdings_engine import _log_returns_matrix, _price_series
from portfolio.optimizer import max_weight_cap

TRADING_DAYS = 252


def _latest_prices(db: DatabaseManager, holdings: list) -> dict:
    """Latest stored close per ticker, falling back to the buy price."""
    stored = db.get_latest_prices([h["ticker"] for h in holdings])
    prices = {}
    for h in holdings:
        info = stored.get(h["ticker"])
        prices[h["ticker"]] = {
            "price": info["close_price"] if info else h["avg_buy_price"],
            "is_estimated": info is None,
        }
    return prices


def optimize_holdings(user_id: str, db: DatabaseManager) -> dict:
    """
    Returns the optimized target allocation across the user's holdings:
      {status, max_weight_pct, expected_return, expected_risk, sharpe_ratio,
       allocation: [{ticker, name, target_weight_pct, current_weight_pct,
                     latest_price, is_estimated}],
       correlation: {tickers: [...], names: [...], matrix: [[...]]}}
    status is "ok", "no_holdings" or "insufficient_history".
    """
    holdings = db.get_holdings(user_id)
    if not holdings:
        return {"status": "no_holdings",
                "message": "Add holdings to optimize your real portfolio."}

    series = {h["ticker"]: _price_series(db, h["ticker"]) for h in holdings}
    tickers, _, returns = _log_returns_matrix(series)
    if returns is None or len(tickers) < 2:
        return {"status": "insufficient_history",
                "message": "Need stored price history for at least two "
                           "holdings — use Refresh Prices first."}

    by_ticker = {h["ticker"]: h for h in holdings}
    prices = _latest_prices(db, holdings)

    mu = returns.mean(axis=0) * TRADING_DAYS
    cov = np.cov(returns.T).reshape(len(tickers), len(tickers)) * TRADING_DAYS
    corr = np.corrcoef(returns.T).reshape(len(tickers), len(tickers))

    n = len(tickers)
    cap = max_weight_cap(n)
    rf = config.PORTFOLIO_RISK_FREE_RATE

    def neg_sharpe(w):
        ret = float(w @ mu)
        vol = math.sqrt(max(float(w @ cov @ w), 1e-12))
        return -(ret - rf) / vol

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0.0, cap)] * n
    x0 = np.full(n, 1.0 / n)
    result = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds,
                      constraints=constraints,
                      options={"maxiter": 300, "ftol": 1e-9})

    weights = result.x if result.success else x0
    weights = np.clip(weights, 0.0, cap)
    weights = weights / weights.sum()

    ret = float(weights @ mu)
    vol = math.sqrt(max(float(weights @ cov @ weights), 0.0))
    sharpe = (ret - rf) / vol if vol > 0 else 0.0

    # Current weights by market value (all holdings, priced ones only
    # participate in the optimization).
    values = {t: by_ticker[t]["quantity"] * prices[t]["price"] for t in tickers}
    total_value = sum(values.values())

    allocation = []
    for i, t in enumerate(tickers):
        allocation.append({
            "ticker":             t,
            "name":               by_ticker[t]["name"],
            "target_weight_pct":  round(float(weights[i]) * 100, 2),
            "current_weight_pct": round(values[t] / total_value * 100, 2)
                                  if total_value > 0 else 0.0,
            "latest_price":       round(prices[t]["price"], 2),
            "is_estimated":       prices[t]["is_estimated"],
        })
    allocation.sort(key=lambda a: -a["target_weight_pct"])

    excluded = [h["ticker"] for h in holdings if h["ticker"] not in tickers]

    return {
        "status":          "ok",
        "max_weight_pct":  round(cap * 100, 2),
        "expected_return": round(ret * 100, 2),
        "expected_risk":   round(vol * 100, 2),
        "sharpe_ratio":    round(sharpe, 3),
        "allocation":      allocation,
        "excluded":        excluded,
        "correlation": {
            "tickers": tickers,
            "names":   [by_ticker[t]["name"] for t in tickers],
            "matrix":  [[round(float(corr[i, j]), 2) for j in range(n)]
                        for i in range(n)],
        },
    }


def build_plan(user_id: str, db: DatabaseManager, amount: float,
               optimized: Optional[dict] = None) -> dict:
    """
    Turn the optimized target weights into concrete whole-share purchases
    for `amount` — how to deploy new money to mirror the target allocation.
    """
    optimized = optimized or optimize_holdings(user_id, db)
    if optimized.get("status") != "ok":
        return optimized

    items, invested = [], 0.0
    for row in optimized["allocation"]:
        budget = amount * row["target_weight_pct"] / 100.0
        price = row["latest_price"]
        units = math.floor(budget / price) if price > 0 else 0
        cost = round(units * price, 2)
        invested += cost
        items.append({
            "ticker":       row["ticker"],
            "name":         row["name"],
            "weight_pct":   row["target_weight_pct"],
            "price":        price,
            "is_estimated": row["is_estimated"],
            "units":        units,
            "cost":         cost,
        })

    return {
        "status":           "ok",
        "total_amount":     round(amount, 2),
        "total_invested":   round(invested, 2),
        "total_uninvested": round(amount - invested, 2),
        "items":            items,
    }
