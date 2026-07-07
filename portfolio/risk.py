"""
Portfolio risk metrics - Monte-Carlo Value-at-Risk on a recommended
allocation. Simulates correlated multi-asset returns over the horizon
using a Cholesky decomposition of the same annualized covariance matrix
the optimizer uses, so the VaR figure is consistent with the
recommendation it describes.
"""

import numpy as np

from portfolio import market_data
from portfolio.market_data import ASSET_ORDER

TRADING_DAYS = 252
N_SIMULATIONS = 10_000
HORIZON_DAYS = 30


def monte_carlo_var(allocation: dict, amount: float,
                    horizon_days: int = HORIZON_DAYS,
                    n_simulations: int = N_SIMULATIONS) -> dict:
    """
    30-day Value-at-Risk for an allocation dict holding <asset>_pct keys
    (as stored in portfolio_recommendations). `amount` is the invested
    rupee value the percentiles are scaled to.
    """
    stats = market_data.get_asset_statistics()
    weights = np.array([allocation.get(f"{a}_pct", 0.0) or 0.0
                        for a in ASSET_ORDER]) / 100.0
    if weights.sum() <= 0:
        raise ValueError("Allocation has no invested weight")
    weights = weights / weights.sum()

    mu = np.array([stats["returns"][a] for a in ASSET_ORDER])
    cov = market_data.get_covariance_matrix(stats)

    # Horizon-scaled parameters (daily i.i.d. normal returns assumption).
    scale = horizon_days / TRADING_DAYS
    mu_h = mu * scale
    cov_h = cov * scale

    # Small jitter keeps Cholesky stable when FD/Cash variance is ~0.
    chol = np.linalg.cholesky(cov_h + np.eye(len(ASSET_ORDER)) * 1e-12)

    rng = np.random.default_rng()
    z = rng.standard_normal((n_simulations, len(ASSET_ORDER)))
    asset_returns = mu_h + z @ chol.T
    portfolio_returns = asset_returns @ weights

    var95 = float(np.percentile(portfolio_returns, 5))
    var99 = float(np.percentile(portfolio_returns, 1))
    expected = float(portfolio_returns.mean())

    def loss_pct(r):
        """Worst-case loss as a positive percentage (gains floor at 0)."""
        return round(max(-r, 0.0) * 100, 2)

    return {
        "horizon_days": horizon_days,
        "simulations": n_simulations,
        "amount": round(amount, 2),
        "var_95_pct": loss_pct(var95),
        "var_99_pct": loss_pct(var99),
        "var_95_amount": round(max(-var95, 0.0) * amount, 2),
        "var_99_amount": round(max(-var99, 0.0) * amount, 2),
        "expected_return_pct": round(expected * 100, 2),
        "source": stats.get("source", "unknown"),
    }
