"""
Markowitz mean-variance portfolio optimization. Long-only (no short
selling), fully invested (weights sum to 1). Risk appetite maps to a
volatility cap; within that cap, the allocation that maximizes the
Sharpe ratio is selected (standard MPT approach).
"""

import numpy as np
from scipy.optimize import minimize

import config
from portfolio import market_data
from portfolio.market_data import ASSET_ORDER

PCT_KEYS = {
    "equity": "equity_pct", "debt": "debt_pct", "gold": "gold_pct",
    "fd": "fd_pct", "cash": "cash_pct", "mutual_funds": "mutual_funds_pct",
}


def _portfolio_stats(weights: np.ndarray, returns_vec: np.ndarray,
                     cov: np.ndarray) -> tuple:
    ret = float(weights @ returns_vec)
    vol = float(np.sqrt(max(weights @ cov @ weights, 0.0)))
    return ret, vol


def _load_inputs():
    stats = market_data.get_asset_statistics()
    returns_vec = np.array([stats["returns"][a] for a in ASSET_ORDER])
    cov = market_data.get_covariance_matrix(stats)
    return stats, returns_vec, cov


def _to_allocation_dict(weights: np.ndarray, ret: float, vol: float,
                        sharpe: float) -> dict:
    result = {PCT_KEYS[a]: round(float(w) * 100, 2)
              for a, w in zip(ASSET_ORDER, weights)}
    result["expected_return"] = round(ret * 100, 2)
    result["expected_risk"] = round(vol * 100, 2)
    result["sharpe_ratio"] = round(sharpe, 3)
    return result


def optimize_portfolio(risk_appetite: str) -> dict:
    """
    Maximizes expected return subject to a volatility cap (rather than
    maximizing Sharpe directly) — with a near-risk-free asset (FD) whose
    Sharpe ratio dominates the risky assets, a pure max-Sharpe objective
    collapses to ~100% FD regardless of the cap (the cap never binds,
    since the unconstrained max-Sharpe portfolio is already far below
    every cap). Maximizing return *forces* each risk bucket to spend its
    full risk budget, producing genuinely different low/medium/high
    allocations — the standard approach used by risk-bucketed model
    portfolios in practice. The resulting Sharpe ratio is still reported.
    """
    if risk_appetite not in config.PORTFOLIO_VOLATILITY_CAPS:
        raise ValueError(f"Unknown risk appetite: {risk_appetite}")

    _, returns_vec, cov = _load_inputs()
    n = len(ASSET_ORDER)
    cap = config.PORTFOLIO_VOLATILITY_CAPS[risk_appetite]
    rf = config.PORTFOLIO_RISK_FREE_RATE

    def neg_return(w):
        return -float(w @ returns_vec)

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1},
        {"type": "ineq", "fun": lambda w: cap - np.sqrt(max(w @ cov @ w, 0.0))},
    ]
    bounds = [(0.0, 1.0)] * n
    x0 = np.full(n, 1.0 / n)

    result = minimize(neg_return, x0, method="SLSQP", bounds=bounds,
                      constraints=constraints,
                      options={"maxiter": 200, "ftol": 1e-9})

    weights = result.x if result.success else x0
    weights = np.clip(weights, 0.0, None)
    weights = weights / weights.sum()

    ret, vol = _portfolio_stats(weights, returns_vec, cov)
    sharpe = (ret - rf) / vol if vol > 0 else 0.0
    return _to_allocation_dict(weights, ret, vol, sharpe)


def _min_variance_return(returns_vec: np.ndarray, cov: np.ndarray,
                         bounds: list, x0: np.ndarray) -> float:
    """Return of the global minimum-variance portfolio (long-only, fully invested)."""
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    result = minimize(lambda w: w @ cov @ w, x0, method="SLSQP",
                      bounds=bounds, constraints=constraints,
                      options={"maxiter": 200, "ftol": 1e-9})
    weights = np.clip(result.x, 0.0, None)
    weights = weights / weights.sum()
    return float(weights @ returns_vec)


def efficient_frontier(n_points: int = 20) -> list:
    """
    Only the efficient (upper) branch of the Markowitz frontier — target
    returns swept from the global minimum-variance portfolio's own return
    up to the highest single-asset return. Below the min-variance return
    lies the *inefficient* lower branch (higher risk for less return),
    which would otherwise make the plotted (risk, return) series look
    non-monotonic near the start.
    """
    _, returns_vec, cov = _load_inputs()
    n = len(ASSET_ORDER)
    bounds = [(0.0, 1.0)] * n
    x0 = np.full(n, 1.0 / n)

    min_var_return = _min_variance_return(returns_vec, cov, bounds, x0)
    targets = np.linspace(min_var_return, float(returns_vec.max()), n_points)
    frontier = []

    for target in targets:
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},
            {"type": "eq", "fun": lambda w, t=target: w @ returns_vec - t},
        ]
        result = minimize(lambda w: w @ cov @ w, x0, method="SLSQP",
                          bounds=bounds, constraints=constraints,
                          options={"maxiter": 200, "ftol": 1e-9})
        if not result.success:
            continue
        weights = np.clip(result.x, 0.0, None)
        weights = weights / weights.sum()
        ret, vol = _portfolio_stats(weights, returns_vec, cov)
        frontier.append({"return": round(ret * 100, 2), "risk": round(vol * 100, 2)})

    return frontier
