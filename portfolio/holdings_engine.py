"""
Holdings analytics engine - everything computed from a user's real
holdings and the locally stored daily_prices history: per-holding P&L
and weights, portfolio annualized volatility, correlation pairs, sector
allocation, Monte-Carlo 30-day VaR, and a Base-100 equity curve against
the NIFTY 50 benchmark. Pure computation — no network calls; prices come
from the DB (populate via HoldingsService.refresh_prices).
"""

from typing import Dict, List

import numpy as np

from database.db_manager import DatabaseManager
from portfolio.holdings_service import (
    BENCHMARK_NAME, BENCHMARK_TICKER, lookup_sector,
)

TRADING_DAYS = 252
VAR_HORIZON_DAYS = 30
VAR_SIMULATIONS = 10_000
MIN_RETURN_POINTS = 30          # need this many aligned days for vol/corr/VaR
HIGH_CORRELATION = 0.75


def _price_series(db: DatabaseManager, ticker: str) -> Dict[str, float]:
    return {row["price_date"]: row["close_price"]
            for row in db.get_price_history(ticker)}


def _log_returns_matrix(series: Dict[str, Dict[str, float]]) -> tuple:
    """Align tickers on common dates -> (tickers, dates, returns ndarray)."""
    tickers = [t for t, s in series.items() if len(s) > MIN_RETURN_POINTS]
    if len(tickers) == 0:
        return [], [], None
    common = set.intersection(*(set(series[t]) for t in tickers))
    dates = sorted(common)
    if len(dates) <= MIN_RETURN_POINTS:
        return tickers, dates, None
    closes = np.array([[series[t][d] for t in tickers] for d in dates])
    returns = np.diff(np.log(closes), axis=0)
    return tickers, dates, returns


def run_holdings_analytics(user_id: str, db: DatabaseManager) -> dict:
    holdings = db.get_holdings(user_id)
    warnings: List[str] = []
    if not holdings:
        return {"holdings": [], "summary": None, "sector_allocation": [],
                "correlation_pairs": [], "equity_curve": [],
                "benchmark_name": BENCHMARK_NAME, "warnings": []}

    tickers = [h["ticker"] for h in holdings]
    latest = db.get_latest_prices(tickers)

    # ── Per-holding metrics ──────────────────────────────────────────────────
    rows = []
    for h in holdings:
        info = latest.get(h["ticker"])
        if info:
            price, is_estimated, price_date = info["close_price"], False, info["price_date"]
        else:
            price, is_estimated, price_date = h["avg_buy_price"], True, None
        market_value = h["quantity"] * price
        cost_basis = h["quantity"] * h["avg_buy_price"]
        rows.append({
            "ticker":        h["ticker"],
            "name":          h["name"],
            "sector":        lookup_sector(h["ticker"]),
            "quantity":      h["quantity"],
            "avg_buy_price": round(h["avg_buy_price"], 2),
            "latest_price":  round(price, 2),
            "is_estimated":  is_estimated,
            "price_date":    price_date,
            "market_value":  round(market_value, 2),
            "cost_basis":    round(cost_basis, 2),
            "pnl":           round(market_value - cost_basis, 2),
            "pnl_pct":       round((market_value / cost_basis - 1) * 100, 2)
                             if cost_basis > 0 else 0.0,
        })

    total_value = sum(r["market_value"] for r in rows)
    total_cost = sum(r["cost_basis"] for r in rows)
    for r in rows:
        r["weight_pct"] = round(r["market_value"] / total_value * 100, 2) \
            if total_value > 0 else 0.0

    estimated = [r["ticker"] for r in rows if r["is_estimated"]]
    if estimated:
        warnings.append(
            "No stored prices for "
            f"{', '.join(estimated)} — using buy price. Hit Refresh Prices.")

    # ── Sector allocation ────────────────────────────────────────────────────
    sectors: Dict[str, float] = {}
    for r in rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0.0) + r["market_value"]
    sector_allocation = [
        {"sector": s, "value": round(v, 2),
         "pct": round(v / total_value * 100, 2) if total_value > 0 else 0.0}
        for s, v in sorted(sectors.items(), key=lambda kv: -kv[1])
    ]

    # ── Return-based statistics (volatility, correlation, VaR) ──────────────
    series = {t: _price_series(db, t) for t in tickers}
    priced, dates, returns = _log_returns_matrix(series)

    volatility_pct = None
    var = None
    correlation_pairs = []
    if returns is not None and len(priced) >= 1:
        values = np.array([next(r["market_value"] for r in rows
                                if r["ticker"] == t) for t in priced])
        if values.sum() > 0:
            weights = values / values.sum()
            cov_daily = np.cov(returns.T).reshape(len(priced), len(priced))
            port_var_daily = float(weights @ cov_daily @ weights)
            volatility_pct = round(
                np.sqrt(max(port_var_daily, 0.0) * TRADING_DAYS) * 100, 2)

            # Monte-Carlo 30-day VaR on the priced sleeve of the portfolio.
            mu_daily = returns.mean(axis=0)
            chol = np.linalg.cholesky(
                cov_daily * VAR_HORIZON_DAYS
                + np.eye(len(priced)) * 1e-12)
            rng = np.random.default_rng()
            z = rng.standard_normal((VAR_SIMULATIONS, len(priced)))
            sim = mu_daily * VAR_HORIZON_DAYS + z @ chol.T
            port_returns = sim @ weights
            var95 = float(np.percentile(port_returns, 5))
            sleeve_value = float(values.sum())
            var = {
                "horizon_days": VAR_HORIZON_DAYS,
                "var_95_pct": round(max(-var95, 0.0) * 100, 2),
                "var_95_amount": round(max(-var95, 0.0) * sleeve_value, 2),
                "covered_value": round(sleeve_value, 2),
            }

        if len(priced) >= 2:
            corr = np.corrcoef(returns.T)
            for i in range(len(priced)):
                for j in range(i + 1, len(priced)):
                    c = float(corr[i, j])
                    correlation_pairs.append({
                        "ticker_a": priced[i], "ticker_b": priced[j],
                        "correlation": round(c, 2),
                        "high": abs(c) >= HIGH_CORRELATION,
                    })
            correlation_pairs.sort(key=lambda p: -abs(p["correlation"]))
    elif len(rows) > len(estimated):
        warnings.append("Not enough stored price history for risk statistics "
                        "— refresh prices and try again.")

    # ── Equity curve vs benchmark (Base-100) ────────────────────────────────
    equity_curve = []
    bench = _price_series(db, BENCHMARK_TICKER)
    if returns is not None and priced:
        qty = {r["ticker"]: r["quantity"] for r in rows}
        curve_dates = [d for d in dates if d in bench] if bench else dates
        if len(curve_dates) > 1:
            first_port = sum(qty[t] * series[t][curve_dates[0]] for t in priced)
            first_bench = bench.get(curve_dates[0]) if bench else None
            for d in curve_dates:
                port_val = sum(qty[t] * series[t][d] for t in priced)
                point = {"date": d,
                         "portfolio": round(port_val / first_port * 100, 2)}
                if first_bench:
                    point["benchmark"] = round(bench[d] / first_bench * 100, 2)
                equity_curve.append(point)
    if not bench and rows:
        warnings.append("Benchmark history not stored yet — refresh prices "
                        "to enable the NIFTY 50 comparison.")

    summary = {
        "total_value":    round(total_value, 2),
        "total_cost":     round(total_cost, 2),
        "total_pnl":      round(total_value - total_cost, 2),
        "total_pnl_pct":  round((total_value / total_cost - 1) * 100, 2)
                          if total_cost > 0 else 0.0,
        "positions":      len(rows),
        "volatility_pct": volatility_pct,
        "var":            var,
    }

    return {"holdings": rows, "summary": summary,
            "sector_allocation": sector_allocation,
            "correlation_pairs": correlation_pairs,
            "equity_curve": equity_curve,
            "benchmark_name": BENCHMARK_NAME,
            "warnings": warnings}
