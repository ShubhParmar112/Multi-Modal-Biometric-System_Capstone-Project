"""
Offline nightly refresh of daily_prices for every held ticker plus the
benchmark. Run from cron or by hand:

    python -m scripts.nightly_prices

Like scripts/build_universe.py this is allowed to reach yfinance — but even
here the fetch goes through the subprocess worker, so nothing imports
yfinance in-process.
"""

import config
from database.db_manager import DatabaseManager
from portfolio import yf_worker
from portfolio.holdings_service import BENCHMARK_TICKER


def _distinct_holding_tickers(db: DatabaseManager) -> list:
    """Every ticker anyone currently holds (raw sqlite via the manager's
    own connection — there's no public accessor for the whole table)."""
    conn = db._get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM portfolio_holdings"
        ).fetchall()
        return [r["ticker"] for r in rows]
    finally:
        conn.close()


def main():
    db = DatabaseManager()
    tickers = _distinct_holding_tickers(db)
    tickers.append(BENCHMARK_TICKER)

    histories = yf_worker.fetch_history_isolated(
        tickers, config.PORTFOLIO_PICKS_TIMEOUT, period="1y")

    stored, failed = [], []
    for ticker in tickers:
        rows = histories.get(ticker)
        if rows:
            db.upsert_daily_prices(
                ticker,
                [(r["date"], r["close"], r.get("volume", 0)) for r in rows])
            stored.append(ticker)
        else:
            failed.append(ticker)

    print(f"nightly_prices: stored {len(stored)} "
          f"[{', '.join(stored) or 'none'}]; "
          f"failed {len(failed)} [{', '.join(failed) or 'none'}]")


if __name__ == "__main__":
    main()
