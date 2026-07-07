"""
Holdings Service - CRUD for a user's real security holdings, a BUY/SELL
trade log that keeps the holding in sync (volume-weighted average price
on BUY, quantity reduction on SELL), local ticker search over the
project's pick universes, and price-history refresh into daily_prices
via the isolated yfinance worker.
"""

from typing import List, Optional

import config
from database.db_manager import DatabaseManager
from portfolio import yf_worker
from portfolio.specific_picks import DEBT_UNIVERSE, EQUITY_UNIVERSE, GOLD_UNIVERSE
from utils.logger import logger

# NIFTY 50 — the natural INR benchmark (also the optimizer's equity proxy).
BENCHMARK_TICKER = "^NSEI"
BENCHMARK_NAME = "NIFTY 50"

# One searchable universe from the symbol tables that already exist.
SEARCH_UNIVERSE = {}
for _src in (EQUITY_UNIVERSE, GOLD_UNIVERSE, DEBT_UNIVERSE):
    SEARCH_UNIVERSE.update(_src)


def search_tickers(query: str, limit: int = 8) -> List[dict]:
    """Substring match on symbol or company name — purely local, no network."""
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for symbol, meta in SEARCH_UNIVERSE.items():
        if q in symbol.lower() or q in meta["name"].lower():
            results.append({"ticker": symbol, "name": meta["name"],
                            "sector": meta.get("sector", "")})
        if len(results) >= limit:
            break
    return results


def lookup_name(ticker: str) -> Optional[str]:
    meta = SEARCH_UNIVERSE.get(ticker)
    return meta["name"] if meta else None


def lookup_sector(ticker: str) -> str:
    meta = SEARCH_UNIVERSE.get(ticker)
    return meta.get("sector", "Other") if meta else "Other"


class HoldingsService:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    # ── Holdings CRUD ────────────────────────────────────────────────────────

    def list_holdings(self, user_id: str) -> List[dict]:
        return self.db.get_holdings(user_id)

    def upsert_holding(self, user_id: str, ticker: str, quantity: float,
                       avg_buy_price: float, name: str = None) -> dict:
        ticker = ticker.strip().upper()
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if avg_buy_price <= 0:
            raise ValueError("Average buy price must be positive")
        name = name or lookup_name(ticker) or ticker
        self.db.upsert_holding(user_id, ticker, name, quantity, avg_buy_price)
        return self.db.get_holding(user_id, ticker)

    def update_holding(self, user_id: str, ticker: str,
                       quantity: float = None,
                       avg_buy_price: float = None) -> Optional[dict]:
        holding = self.db.get_holding(user_id, ticker)
        if not holding:
            return None
        new_qty = quantity if quantity is not None else holding["quantity"]
        new_price = (avg_buy_price if avg_buy_price is not None
                     else holding["avg_buy_price"])
        if new_qty <= 0 or new_price <= 0:
            raise ValueError("Quantity and price must be positive")
        self.db.upsert_holding(user_id, ticker, holding["name"],
                               new_qty, new_price)
        return self.db.get_holding(user_id, ticker)

    def delete_holding(self, user_id: str, ticker: str) -> bool:
        return self.db.delete_holding(user_id, ticker)

    # ── Trades (auto-sync the holding) ───────────────────────────────────────

    def record_trade(self, user_id: str, ticker: str, action: str,
                     price: float, quantity: float, name: str = None) -> dict:
        ticker = ticker.strip().upper()
        action = action.strip().upper()
        if action not in ("BUY", "SELL"):
            raise ValueError("Action must be BUY or SELL")
        if price <= 0 or quantity <= 0:
            raise ValueError("Price and quantity must be positive")

        holding = self.db.get_holding(user_id, ticker)

        if action == "BUY":
            if holding:
                total_qty = holding["quantity"] + quantity
                vwap = ((holding["quantity"] * holding["avg_buy_price"]
                         + quantity * price) / total_qty)
                self.db.upsert_holding(user_id, ticker, holding["name"],
                                       total_qty, round(vwap, 4))
            else:
                self.db.upsert_holding(user_id, ticker,
                                       name or lookup_name(ticker) or ticker,
                                       quantity, price)
        else:  # SELL
            if not holding or holding["quantity"] < quantity:
                have = holding["quantity"] if holding else 0
                raise ValueError(
                    f"Cannot sell {quantity} of {ticker} — you hold {have}")
            remaining = holding["quantity"] - quantity
            if remaining > 1e-9:
                self.db.upsert_holding(user_id, ticker, holding["name"],
                                       remaining, holding["avg_buy_price"])
            else:
                self.db.delete_holding(user_id, ticker)

        self.db.record_portfolio_trade(user_id, ticker, action, price, quantity)
        return {"holding": self.db.get_holding(user_id, ticker),
                "trades": self.db.get_portfolio_trades(user_id, limit=20)}

    def list_trades(self, user_id: str, limit: int = 100) -> List[dict]:
        return self.db.get_portfolio_trades(user_id, limit)

    # ── Price history refresh ────────────────────────────────────────────────

    def refresh_prices(self, user_id: str, period: str = "1y") -> dict:
        """Fetch daily closes for every holding plus the benchmark via the
        isolated yfinance worker and upsert them into daily_prices."""
        tickers = [h["ticker"] for h in self.db.get_holdings(user_id)]
        tickers.append(BENCHMARK_TICKER)

        histories = yf_worker.fetch_history_isolated(
            tickers, config.PORTFOLIO_PICKS_TIMEOUT, period=period)

        stored, failed = {}, []
        for ticker in tickers:
            rows = histories.get(ticker)
            if rows:
                stored[ticker] = self.db.upsert_daily_prices(
                    ticker, [(r["date"], r["close"]) for r in rows])
            else:
                failed.append(ticker)

        if failed:
            logger.warning(f"Price refresh failed for: {', '.join(failed)}")
        return {"stored": stored, "failed": failed}
