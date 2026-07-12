"""
Offline builder for data/universe.csv — the NSE-wide equity search universe.

Run once, then commit the generated data/universe.csv. A single run() does
two phases:

  Phase 1  Download NSE's EQUITY_L.csv, keep SERIES == "EQ", and write
           ticker,name,sector rows (sector left blank for now).
  Phase 2  Fill each blank sector from yfinance, sleeping 0.5s between calls
           and rewriting the CSV every 25 lookups so a crash or Ctrl-C
           resumes from the last flush instead of restarting.

This file and scripts/nightly_prices.py are the ONLY modules permitted to
import yfinance directly; server code always goes through the subprocess
worker (portfolio/yf_worker.py).

    python -m scripts.build_universe

If you already have a pre-joined EQUITY_L + sector CSV (columns SYMBOL,
NAME OF COMPANY, SERIES, ..., YF_SYMBOL, Sector), skip both phases and
convert it directly:

    python -m scripts.build_universe --from-csv path/to/equity_with_sector.csv
"""

import argparse
import csv
import io
import os
import time

import requests
import yfinance as yf

import config
from portfolio.specific_picks import _UA

EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
UNIVERSE_CSV = os.path.join(config.BASE_DIR, "data", "universe.csv")
_FIELDS = ["ticker", "name", "sector"]
_FLUSH_EVERY = 25


def _download_equity_list() -> list:
    """Fetch EQUITY_L.csv (NSE 403s default agents — reuse the browser _UA)
    and return the SERIES == 'EQ' rows as {ticker, name, sector} dicts with
    a blank sector."""
    resp = requests.get(EQUITY_L_URL, timeout=30, headers={"User-Agent": _UA})
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    for row in reader:
        if row.get("SERIES", "").strip() != "EQ":
            continue
        symbol = row["SYMBOL"].strip().upper()
        rows.append({
            "ticker": f"{symbol}.NS",
            "name": row["NAME OF COMPANY"].strip(),
            "sector": "",
        })
    return rows


def _write_csv(rows: list):
    os.makedirs(os.path.dirname(UNIVERSE_CSV), exist_ok=True)
    with open(UNIVERSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv() -> list:
    with open(UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _known_sectors() -> dict:
    """ticker -> sector from a prior CSV, so a full-script rerun keeps the
    sectors Phase 2 already resolved."""
    try:
        return {r["ticker"]: r.get("sector", "") for r in _read_csv()}
    except FileNotFoundError:
        return {}


def _fill_sectors(rows: list):
    """Fill blank sectors from yfinance, flushing every _FLUSH_EVERY lookups
    so a crash/rerun resumes instead of restarting."""
    done = 0
    for row in rows:
        if row.get("sector", "").strip():
            continue
        try:
            info = yf.Ticker(row["ticker"]).info
            row["sector"] = info.get("sector", "") or ""
        except Exception as e:
            # ponytail: any failure (network, parse, delisted symbol) just
            # leaves the sector blank — the next rerun retries it.
            print(f"  sector lookup failed for {row['ticker']}: {e}")
            row["sector"] = ""
        time.sleep(0.5)
        done += 1
        if done % _FLUSH_EVERY == 0:
            _write_csv(rows)
            print(f"  ...flushed after {done} lookups")
    _write_csv(rows)


def import_from_csv(src_path: str):
    """Convert a pre-joined EQUITY_L + sector CSV straight into
    data/universe.csv, skipping the download and the yfinance crawl.
    Missing/"Unknown" sectors become "Others" — the app's catch-all
    sector bucket."""
    with open(src_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # EQUITY_L headers arrive with stray spaces (" SERIES") — normalize.
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        rows = []
        for src in reader:
            if src.get("SERIES", "EQ").strip() != "EQ":
                continue
            ticker = (src.get("YF_SYMBOL", "").strip().upper()
                      or f"{src['SYMBOL'].strip().upper()}.NS")
            sector = src.get("Sector", "").strip()
            if not sector or sector == "Unknown":
                sector = "Others"
            rows.append({
                "ticker": ticker,
                "name": src["NAME OF COMPANY"].strip(),
                "sector": sector,
            })
    _write_csv(rows)
    print(f"Imported {len(rows)} EQ rows from {src_path} -> {UNIVERSE_CSV}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-csv", metavar="PATH",
        help="build universe.csv from a pre-joined EQUITY_L + sector CSV "
             "instead of downloading and crawling yfinance")
    args = parser.parse_args()

    if args.from_csv:
        import_from_csv(args.from_csv)
        return

    print("Phase 1: downloading NSE EQUITY_L.csv ...")
    carried = _known_sectors()
    rows = _download_equity_list()
    for row in rows:
        row["sector"] = carried.get(row["ticker"], "") or ""
    _write_csv(rows)
    print(f"  wrote {len(rows)} EQ rows to {UNIVERSE_CSV}")

    print("Phase 2: filling blank sectors from yfinance ...")
    _fill_sectors(rows)
    print("Done.")


if __name__ == "__main__":
    main()
