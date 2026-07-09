"""
Runs yfinance network calls in a short-lived subprocess.

Why: the curl_cffi HTTP backend that yfinance uses segfaults the entire
Python process on this platform for several call paths (Ticker.fast_info
on any symbol, and any 4xx error response from Yahoo). A segfault inside
a FastAPI worker thread kills the whole server — the subprocess boundary
turns that crash into a recoverable fetch failure, and the subprocess
timeout doubles as a hard deadline so a hung fetch can never pin the
server's worker threads.

Parent side:  run_job({"kind": ...}, timeout)  → dict/list or None
Child side:   python -m portfolio.yf_worker    (job JSON on stdin)
"""

import json
import os
import subprocess
import sys
from typing import Optional


def run_job(job: dict, timeout: float) -> Optional[object]:
    """Execute a fetch job in a subprocess. Returns None on any failure."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "portfolio.yf_worker"],
            input=json.dumps(job),
            capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, cwd=project_root,
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout)
    except Exception:
        return None


def fetch_history_isolated(tickers: list, timeout: float,
                           period: str = "1y", max_parallel: int = 4) -> dict:
    """Daily close history per ticker, one subprocess per symbol (same
    poisoned-symbol isolation rationale as fetch_quotes_isolated).
    Returns {ticker: [{"date": "YYYY-MM-DD", "close": float, "volume": int},
    ...]} with failed symbols simply absent."""
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(symbol):
        rows = run_job({"kind": "history", "ticker": symbol,
                        "period": period}, timeout)
        return symbol, rows

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        results = list(pool.map(fetch_one, tickers))
    return {symbol: rows for symbol, rows in results if rows}


def fetch_quotes_isolated(tickers: dict, timeout: float,
                          max_parallel: int = 4) -> list:
    """One subprocess per ticker. Some symbols deterministically segfault
    the yfinance stack (observed: HDFCBANK.NS, ICICIBANK.NS, BHARTIARTL.NS)
    and a segfault can't be caught in-process — per-ticker isolation means
    a poisoned symbol only costs its own row, not the whole batch.

    The threads here only wait on subprocesses (no yfinance in the parent),
    so this is safe to run inside the server."""
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(item):
        symbol, meta = item
        rows = run_job({"kind": "quotes", "tickers": {symbol: meta}}, timeout)
        return rows[0] if rows else None

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        results = list(pool.map(fetch_one, tickers.items()))
    return [row for row in results if row]


# ── Subprocess side ───────────────────────────────────────────────────────────

def _job_stats() -> dict:
    from portfolio import market_data
    return market_data._fetch_live_statistics()


def _job_quotes(tickers: dict) -> list:
    """One batched download for all symbols — never Ticker.fast_info
    (it segfaults, see module docstring). All figures (price, day change,
    52-week range, 1-year return, annualised volatility) are computed live
    from the year of daily closes in the same request."""
    import numpy as np
    import yfinance as yf

    data = yf.download(
        list(tickers), period="1y", interval="1d", progress=False,
        auto_adjust=False, group_by="ticker", threads=False,
    )

    rows = []
    for symbol, meta in tickers.items():
        try:
            closes = data[symbol]["Close"].dropna()
            if closes.empty:
                continue
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else price

            returns_1y_pct = None
            volatility_pct = None
            if len(closes) > 30:
                first = float(closes.iloc[0])
                if first > 0:
                    returns_1y_pct = round((price / first - 1) * 100, 2)
                daily = np.log(closes / closes.shift(1)).dropna()
                volatility_pct = round(float(daily.std()) * np.sqrt(252) * 100, 2)

            rows.append({
                "ticker":         symbol.replace(".NS", ""),
                "name":           meta["name"],
                "sector":         meta.get("sector", ""),
                "price":          round(price, 2),
                "change_pct":     round((price - prev) / prev * 100, 2) if prev else 0.0,
                "returns_1y_pct": returns_1y_pct,
                "volatility_pct": volatility_pct,
                "week52_high":    round(float(closes.max()), 2),
                "week52_low":     round(float(closes.min()), 2),
            })
        except Exception:
            continue
    return rows


def _job_history(ticker: str, period: str) -> list:
    """Daily closes + volume for one symbol as
    [{"date", "close", "volume"}, ...] — batched yf.download only (never
    Ticker.history/fast_info, see docstring). volume is int, 0 when the
    Volume cell is NaN or missing."""
    import math

    import yfinance as yf

    data = yf.download(
        [ticker], period=period, interval="1d", progress=False,
        auto_adjust=True, group_by="ticker", threads=False,
    )
    frame = data[ticker].dropna(subset=["Close"])
    has_volume = "Volume" in frame.columns
    rows = []
    for idx, r in frame.iterrows():
        vol = r["Volume"] if has_volume else None
        rows.append({
            "date":   idx.strftime("%Y-%m-%d"),
            "close":  round(float(r["Close"]), 4),
            "volume": 0 if vol is None or math.isnan(vol) else int(vol),
        })
    return rows


def main():
    job = json.loads(sys.stdin.read())

    # stdout must stay pure JSON — send any stray library prints to stderr.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        if job["kind"] == "stats":
            result = _job_stats()
        elif job["kind"] == "quotes":
            result = _job_quotes(job["tickers"])
        elif job["kind"] == "history":
            result = _job_history(job["ticker"], job.get("period", "1y"))
        else:
            raise ValueError(f"Unknown job kind: {job['kind']}")
    finally:
        sys.stdout = real_stdout

    print(json.dumps(result))


if __name__ == "__main__":
    main()
