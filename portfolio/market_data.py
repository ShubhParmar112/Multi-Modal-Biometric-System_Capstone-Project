"""
Market data for the portfolio optimizer - fetches real historical
return/volatility/correlation statistics via yfinance for the 4
market-traded asset classes (Equity/Debt/Gold/Mutual Funds). FD and Cash
aren't market-traded securities, so they use a fixed assumed rate with
near-zero volatility (standard treatment of the risk-free asset in MPT).

Known limitation: the proxies mix an INR index (NIFTY 50 for Equity) with
USD-denominated US ETFs (Debt/Gold/Mutual Funds) without FX-hedging. This
is an acceptable approximation for demonstrating the optimization
methodology, not a production-grade asset model.
"""

import time

import numpy as np
import yfinance as yf

import config
from utils.logger import logger

ASSET_ORDER = ["equity", "debt", "gold", "fd", "cash", "mutual_funds"]
MARKET_ASSETS = ["equity", "debt", "gold", "mutual_funds"]

# Used only if the live yfinance fetch fails for any reason.
STATIC_FALLBACK_RETURNS = {"equity": 0.12, "debt": 0.07, "gold": 0.08, "mutual_funds": 0.10}
STATIC_FALLBACK_VOLATILITY = {"equity": 0.18, "debt": 0.05, "gold": 0.14, "mutual_funds": 0.12}
STATIC_FALLBACK_CORRELATION = {
    "equity":       {"equity": 1.0, "debt": -0.1, "gold": 0.1, "mutual_funds": 0.85},
    "debt":         {"equity": -0.1, "debt": 1.0, "gold": 0.2, "mutual_funds": 0.3},
    "gold":         {"equity": 0.1, "debt": 0.2, "gold": 1.0, "mutual_funds": 0.15},
    "mutual_funds": {"equity": 0.85, "debt": 0.3, "gold": 0.15, "mutual_funds": 1.0},
}

_cache = {"data": None, "fetched_at": 0.0}


def _build_full_matrix(market_corr: dict) -> dict:
    """Expand a 4-asset correlation dict into the full 6-asset ASSET_ORDER matrix."""
    matrix = {a: {b: 0.0 for b in ASSET_ORDER} for a in ASSET_ORDER}
    for a in ASSET_ORDER:
        matrix[a][a] = 1.0
    for a in MARKET_ASSETS:
        for b in MARKET_ASSETS:
            matrix[a][b] = market_corr[a][b]
    return matrix


def _fetch_live_statistics() -> dict:
    tickers = config.PORTFOLIO_TICKERS
    closes = yf.download(
        list(tickers.values()), period=config.PORTFOLIO_HISTORY_PERIOD,
        interval="1d", progress=False, auto_adjust=True
    )["Close"]

    log_returns = np.log(closes / closes.shift(1)).dropna()

    ann_return = log_returns.mean() * 252
    ann_volatility = log_returns.std() * np.sqrt(252)
    corr = log_returns.corr()

    ticker_to_asset = {v: k for k, v in tickers.items()}
    returns = {ticker_to_asset[t]: float(ann_return[t]) for t in tickers.values()}
    volatility = {ticker_to_asset[t]: float(ann_volatility[t]) for t in tickers.values()}
    market_corr = {
        ticker_to_asset[t1]: {
            ticker_to_asset[t2]: float(corr.loc[t1, t2]) for t2 in tickers.values()
        }
        for t1 in tickers.values()
    }

    returns["fd"] = config.PORTFOLIO_FD_RATE
    returns["cash"] = config.PORTFOLIO_CASH_RATE
    volatility["fd"] = config.PORTFOLIO_FD_VOLATILITY
    volatility["cash"] = config.PORTFOLIO_CASH_VOLATILITY

    return {
        "returns": returns,
        "volatility": volatility,
        "correlation": _build_full_matrix(market_corr),
        "source": "yfinance",
    }


def _static_fallback() -> dict:
    returns = dict(STATIC_FALLBACK_RETURNS)
    volatility = dict(STATIC_FALLBACK_VOLATILITY)
    returns["fd"] = config.PORTFOLIO_FD_RATE
    returns["cash"] = config.PORTFOLIO_CASH_RATE
    volatility["fd"] = config.PORTFOLIO_FD_VOLATILITY
    volatility["cash"] = config.PORTFOLIO_CASH_VOLATILITY
    return {
        "returns": returns,
        "volatility": volatility,
        "correlation": _build_full_matrix(STATIC_FALLBACK_CORRELATION),
        "source": "static_fallback",
    }


def get_asset_statistics(force_refresh: bool = False) -> dict:
    """Returns {"returns": {...}, "volatility": {...}, "correlation": {...}, "source": ...}."""
    age_hours = (time.time() - _cache["fetched_at"]) / 3600
    if not force_refresh and _cache["data"] and age_hours < config.PORTFOLIO_CACHE_HOURS:
        return _cache["data"]

    try:
        data = _fetch_live_statistics()
        logger.success("Portfolio market data fetched live via yfinance")
    except Exception as e:
        logger.warning(f"yfinance fetch failed ({e}); using static fallback assumptions")
        data = _static_fallback()

    _cache["data"] = data
    _cache["fetched_at"] = time.time()
    return data


def get_covariance_matrix(stats: dict = None) -> np.ndarray:
    """Build the 6x6 annualized covariance matrix in ASSET_ORDER from get_asset_statistics()."""
    stats = stats or get_asset_statistics()
    vol = np.array([stats["volatility"][a] for a in ASSET_ORDER])
    corr = np.array([[stats["correlation"][a][b] for b in ASSET_ORDER] for a in ASSET_ORDER])
    return np.outer(vol, vol) * corr
