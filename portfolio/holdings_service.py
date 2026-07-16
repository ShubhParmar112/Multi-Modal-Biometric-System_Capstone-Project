"""
Holdings Service - CRUD for a user's real security holdings, a BUY/SELL
trade log that keeps the holding in sync (volume-weighted average price
on BUY, quantity reduction on SELL), local ticker search over the
project's pick universes, and price-history refresh into daily_prices
via the isolated yfinance worker.
"""

import csv
import os
from typing import List, Optional

import config
from database.db_manager import DatabaseManager
from portfolio import yf_worker
from portfolio.specific_picks import DEBT_UNIVERSE, EQUITY_UNIVERSE, GOLD_UNIVERSE
from utils import email_service
from utils.logger import logger

# NIFTY 50 — the natural INR benchmark (also the optimizer's equity proxy).
BENCHMARK_TICKER = "^NSEI"
BENCHMARK_NAME = "NIFTY 50"

_UNIVERSE_CSV = os.path.join(config.BASE_DIR, "data", "universe.csv")


def _load_search_universe() -> dict:
    """The NSE-wide universe from data/universe.csv, with the project's pick
    tables overlaid on top (pick tables win — keeps the ETFs/bonds those
    tables add searchable and with their curated names/sectors). Same
    {ticker: {"name", "sector"}} shape as before, so lookup_name/
    lookup_sector are untouched. If universe.csv hasn't been built yet, falls
    back to just the three pick universes."""
    universe = {}
    try:
        with open(_UNIVERSE_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker = row["ticker"].strip().upper()
                universe[ticker] = {"name": row.get("name", "").strip(),
                                    "sector": row.get("sector", "").strip()}
    except FileNotFoundError:
        pass  # not built yet — the pick tables below are enough on their own
    for _src in (EQUITY_UNIVERSE, GOLD_UNIVERSE, DEBT_UNIVERSE):
        universe.update(_src)
    return universe


# One searchable universe, loaded once at import time.
SEARCH_UNIVERSE = _load_search_universe()


def _bare(ticker: str) -> str:
    """Symbol without the .NS suffix (TCS.NS -> TCS)."""
    return ticker[:-3] if ticker.upper().endswith(".NS") else ticker


def search_tickers(query: str, limit: int = 8) -> List[dict]:
    """Ranked local search over the universe — purely local, no network.

    Tier 0: exact symbol match (query "TCS" or "TCS.NS" hits TCS.NS)
    Tier 1: symbol prefix
    Tier 2: substring in symbol or name
    Stable insertion order within each tier (dicts preserve it)."""
    q = query.strip().upper()
    if not q:
        return []
    q_sym = _bare(q)          # "TCS.NS" -> "TCS", "TCS" -> "TCS"
    q_lower = q.lower()

    exact, prefix, substr = [], [], []
    for ticker, meta in SEARCH_UNIVERSE.items():
        sym = _bare(ticker).upper()
        row = {"ticker": ticker, "name": meta["name"],
               "sector": meta.get("sector", "")}
        if sym == q_sym or ticker.upper() == q:
            exact.append(row)
        elif sym.startswith(q_sym):
            prefix.append(row)
        elif q_lower in ticker.lower() or q_lower in meta["name"].lower():
            substr.append(row)

    return (exact + prefix + substr)[:limit]


def lookup_name(ticker: str) -> Optional[str]:
    meta = SEARCH_UNIVERSE.get(ticker)
    return meta["name"] if meta else None


def lookup_sector(ticker: str) -> str:
    # "Others" matches universe.csv's catch-all bucket, so unknowns merge.
    meta = SEARCH_UNIVERSE.get(ticker)
    return meta.get("sector", "Others") if meta else "Others"


class HoldingsService:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    # ── Holdings CRUD ────────────────────────────────────────────────────────

    def list_holdings(self, user_id: str) -> List[dict]:
        return self.db.get_holdings(user_id)

    def portfolio_summary(self, user_id: str, spark_days: int = 30) -> dict:
        """Compact snapshot for the dashboard invest card: total value,
        1-day change, top holding, and a total-value sparkline built from
        stored closes (holdings without history are valued flat at their
        buy price so they can't distort the day change)."""
        holdings = self.db.get_holdings(user_id)
        if not holdings:
            return {"status": "empty"}

        histories = {}
        dated = set()
        for h in holdings:
            rows = self.db.get_price_history(h["ticker"], days=spark_days)
            histories[h["ticker"]] = {r["price_date"]: r["close_price"]
                                      for r in rows}
            if rows:
                dated.update(histories[h["ticker"]])

        # Dates where every holding WITH history has a close; each series
        # carries its last known close forward for any gaps.
        spark = []
        invested = sum(h["quantity"] * h["avg_buy_price"] for h in holdings)
        for d in sorted(dated):
            total = 0.0
            for h in holdings:
                hist = histories[h["ticker"]]
                past = [k for k in hist if k <= d]
                price = hist[max(past)] if past else h["avg_buy_price"]
                total += h["quantity"] * price
            spark.append(round(total, 2))

        value = spark[-1] if spark else round(invested, 2)
        prev = spark[-2] if len(spark) >= 2 else value
        day_change = round(value - prev, 2)

        def latest_price(h):
            hist = histories[h["ticker"]]
            return list(hist.values())[-1] if hist else h["avg_buy_price"]

        top = max(holdings, key=lambda h: h["quantity"] * latest_price(h))
        top_value = top["quantity"] * latest_price(top)

        return {
            "status": "ok",
            "value": round(value, 2),
            "invested": round(invested, 2),
            "day_change": day_change,
            "day_change_pct": round(day_change / prev * 100, 2) if prev else 0.0,
            "holdings_count": len(holdings),
            "top_holding": {
                "ticker": top["ticker"],
                "name": top["name"],
                "share_pct": round(top_value / value * 100, 1) if value else 0.0,
            },
            "spark": spark,
        }

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
        updated = self.db.get_holding(user_id, ticker)

        # Confirmation mail — a notification, never part of the trade itself.
        try:
            user = self.db.get_user(user_id)
            email_service.send_trade_email(
                user, action, ticker,
                (updated or holding or {}).get("name")
                or name or lookup_name(ticker) or ticker,
                quantity, price,
                remaining_qty=updated["quantity"] if updated else 0,
            )
        except Exception as e:
            logger.error(f"Trade alert failed for {user_id}: {e}")

        return {"holding": updated,
                "trades": self.db.get_portfolio_trades(user_id, limit=20)}

    def list_trades(self, user_id: str, limit: int = 100) -> List[dict]:
        return self.db.get_portfolio_trades(user_id, limit)

    # ── Price history refresh ────────────────────────────────────────────────

    def refresh_prices(self, user_id: str, period: str = "1y",
                       tickers: List[str] = None) -> dict:
        """Fetch daily closes for every holding plus the benchmark via the
        isolated yfinance worker and upsert them into daily_prices. Pass
        `tickers` to refresh just those (the benchmark is always included)."""
        if tickers is None:
            tickers = [h["ticker"] for h in self.db.get_holdings(user_id)]
        else:
            tickers = [t.strip().upper() for t in tickers]
        tickers = tickers + [BENCHMARK_TICKER]

        histories = yf_worker.fetch_history_isolated(
            tickers, config.PORTFOLIO_PICKS_TIMEOUT, period=period)

        stored, failed = {}, []
        for ticker in tickers:
            rows = histories.get(ticker)
            if rows:
                stored[ticker] = self.db.upsert_daily_prices(
                    ticker,
                    [(r["date"], r["close"], r.get("volume", 0)) for r in rows])
            else:
                failed.append(ticker)

        if failed:
            logger.warning(f"Price refresh failed for: {', '.join(failed)}")
        return {"stored": stored, "failed": failed}
