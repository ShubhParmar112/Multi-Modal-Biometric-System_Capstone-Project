"""
Specific investment picks per asset class — all fetched live.

  Equity / Gold ETFs  → Yahoo Finance (isolated subprocess, see yf_worker)
  Mutual funds        → AMFI NAV history via api.mfapi.in (free, no key)
  Debt                → NSE-listed debt ETFs (gilt / PSU bond / liquid) via Yahoo
  FD rates            → scraped from BankBazaar's rate comparison table

Nothing shown to the user is hardcoded market data: prices, NAVs, returns,
volatility and rates are computed from the live feeds at request time, and
the picks themselves are re-selected from that data based on the user's
risk appetite. Every feed is cached (memory + disk) and served
stale-while-refreshing so a slow source never blocks a request.
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import List

import requests

import config
from portfolio import yf_worker
from utils.logger import logger

# ── Candidate universes ──────────────────────────────────────────────────────
# These are only symbol/scheme lookup tables — no market figures live here.
# A symbol that fails to fetch is simply skipped.
EQUITY_UNIVERSE = {
    "RELIANCE.NS":   {"name": "Reliance Industries",        "sector": "Energy & Retail"},
    "TCS.NS":        {"name": "Tata Consultancy Services",  "sector": "IT"},
    "INFY.NS":       {"name": "Infosys",                    "sector": "IT"},
    "HCLTECH.NS":    {"name": "HCL Technologies",           "sector": "IT"},
    "WIPRO.NS":      {"name": "Wipro",                      "sector": "IT"},
    "HDFCBANK.NS":   {"name": "HDFC Bank",                  "sector": "Banking"},
    "ICICIBANK.NS":  {"name": "ICICI Bank",                 "sector": "Banking"},
    "KOTAKBANK.NS":  {"name": "Kotak Mahindra Bank",        "sector": "Banking"},
    "SBIN.NS":       {"name": "State Bank of India",        "sector": "Banking"},
    "BAJFINANCE.NS": {"name": "Bajaj Finance",              "sector": "Financial Services"},
    "BHARTIARTL.NS": {"name": "Bharti Airtel",              "sector": "Telecom"},
    "HINDUNILVR.NS": {"name": "Hindustan Unilever",         "sector": "FMCG"},
    "ITC.NS":        {"name": "ITC",                        "sector": "FMCG"},
    "NESTLEIND.NS":  {"name": "Nestlé India",               "sector": "FMCG"},
    "LT.NS":         {"name": "Larsen & Toubro",            "sector": "Infrastructure"},
    "MARUTI.NS":     {"name": "Maruti Suzuki",              "sector": "Auto"},
    "TATAMOTORS.NS": {"name": "Tata Motors",                "sector": "Auto"},
    "SUNPHARMA.NS":  {"name": "Sun Pharma",                 "sector": "Pharma"},
    "TITAN.NS":      {"name": "Titan Company",              "sector": "Consumer"},
    "ASIANPAINT.NS": {"name": "Asian Paints",               "sector": "Consumer"},
}

GOLD_UNIVERSE = {
    "GOLDBEES.NS":  {"name": "Nippon India Gold ETF (GOLDBEES)", "sector": "Gold ETF"},
    "SETFGOLD.NS":  {"name": "SBI Gold ETF (SETFGOLD)",          "sector": "Gold ETF"},
    "KOTAKGOLD.NS": {"name": "Kotak Gold ETF",                   "sector": "Gold ETF"},
    "HDFCGOLD.NS":  {"name": "HDFC Gold ETF",                    "sector": "Gold ETF"},
    "AXISGOLD.NS":  {"name": "Axis Gold ETF",                    "sector": "Gold ETF"},
}

# Exchange-traded fixed-income instruments (all NSE symbols) — live prices
# and yields replace the old hardcoded rate table.
DEBT_UNIVERSE = {
    "LIQUIDBEES.NS": {"name": "Nippon India Liquid BeES",       "sector": "Liquid ETF"},
    "GILT5YBEES.NS": {"name": "Nippon India 5Y Gilt BeES",      "sector": "Gilt ETF"},
    "LTGILTBEES.NS": {"name": "Nippon India Long Term Gilt",    "sector": "Gilt ETF"},
    "SETF10GILT.NS": {"name": "SBI 10-Year Gilt ETF",           "sector": "Gilt ETF"},
    "EBBETF0430.NS": {"name": "Bharat Bond ETF (April 2030)",   "sector": "PSU Bond ETF"},
    "EBBETF0431.NS": {"name": "Bharat Bond ETF (April 2031)",   "sector": "PSU Bond ETF"},
}

# AMFI scheme codes (api.mfapi.in) — Direct-Growth plans. Fund names and
# categories are taken from the live API metadata, not from here.
MF_SCHEME_CODES = [
    119091,  # HDFC Liquid Fund
    120389,  # Axis Liquid Fund
    111972,  # ICICI Prudential Corporate Bond Fund
    118825,  # Mirae Asset Large Cap Fund
    119598,  # SBI Large Cap Fund
    145110,  # Axis Large & Mid Cap Fund
    118968,  # HDFC Balanced Advantage Fund
    120377,  # ICICI Prudential Balanced Advantage Fund
    122639,  # Parag Parikh Flexi Cap Fund
    118989,  # HDFC Mid Cap Fund
    118778,  # Nippon India Small Cap Fund
    120828,  # Quant Small Cap Fund
]
MFAPI_URL = "https://api.mfapi.in/mf/{code}"
MF_PICK_COUNT = 5

FD_RATES_URL = "https://www.bankbazaar.com/fixed-deposit-rate.html"
FD_MAX_BANKS = 10
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

EQUITY_PICK_COUNT = 6

# Per-kind cache freshness (hours). MF NAVs update once a day and FD rates
# change rarely — no point hammering those sources hourly.
CACHE_H = {"equity": 1.0, "gold": 1.0, "mf": 12.0, "debt": 1.0, "fd": 24.0}
PICKS_CACHE_FILE = os.path.join(config.BASE_DIR, "portfolio", "picks_cache.json")

_SGB_ROW = {
    "ticker":      "SGB",
    "name":        "Sovereign Gold Bond (SGB)",
    "sector":      "Govt. Backed",
    "price":       None,
    "change_pct":  None,
    "market_cap":  "GoI Backed",
    "week52_high": None,
    "week52_low":  None,
    "note":        "2.5% p.a. interest + gold price appreciation. Capital gains tax-free on RBI maturity. Buy via banks, post offices, or NSE.",
}

# kind -> {"data": [...] | None, "at": epoch}. Persisted to disk so a server
# restart doesn't refetch. Stale entries are served immediately while a
# background thread refreshes them — a request never waits on the source
# unless there is no data at all (the very first run).
_caches = {kind: {"data": None, "at": 0.0} for kind in CACHE_H}
_lock = threading.Lock()
_refreshing: set = set()
_disk_loaded = False


# Bump when the row schema changes so stale disk caches are discarded.
_CACHE_VERSION = 3


def _load_disk_cache_once():
    global _disk_loaded
    if _disk_loaded:
        return
    _disk_loaded = True
    try:
        with open(PICKS_CACHE_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("version") != _CACHE_VERSION:
            return
        for kind in _caches:
            if saved.get(kind, {}).get("data"):
                _caches[kind] = saved[kind]
        logger.info("Investment picks restored from disk cache")
    except Exception:
        pass


def _save_disk_cache():
    try:
        payload = {"version": _CACHE_VERSION, **_caches}
        tmp = PICKS_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, PICKS_CACHE_FILE)
    except Exception as e:
        logger.warning(f"Could not persist picks cache: {e}")


# ── Live fetchers (one per pick kind) ─────────────────────────────────────────


def _fetch_equity() -> List[dict]:
    return yf_worker.fetch_quotes_isolated(
        EQUITY_UNIVERSE, config.PORTFOLIO_PICKS_TIMEOUT)


def _fetch_gold() -> List[dict]:
    rows = yf_worker.fetch_quotes_isolated(
        GOLD_UNIVERSE, config.PORTFOLIO_PICKS_TIMEOUT)
    return rows + [_SGB_ROW] if rows else []


def _fetch_debt() -> List[dict]:
    rows = yf_worker.fetch_quotes_isolated(
        DEBT_UNIVERSE, config.PORTFOLIO_PICKS_TIMEOUT)
    for row in rows:
        row["type"] = row.get("sector", "Debt ETF")
    return rows


def _risk_label(volatility_pct) -> str:
    """Risk bucket from live annualised volatility — same scale funds
    use on their riskometer, roughly."""
    if volatility_pct is None:
        return "Unrated"
    if volatility_pct < 2:
        return "Low"
    if volatility_pct < 8:
        return "Low–Moderate"
    if volatility_pct < 14:
        return "Moderate"
    if volatility_pct < 18:
        return "Moderately High"
    if volatility_pct < 24:
        return "High"
    return "Very High"


def _nav_on_or_before(history: List[dict], target: datetime):
    """history is newest-first [(date 'dd-mm-YYYY', nav str), ...]."""
    for entry in history:
        d = datetime.strptime(entry["date"], "%d-%m-%Y")
        if d <= target:
            return float(entry["nav"])
    return None


def _fetch_one_mf(code: int):
    resp = requests.get(MFAPI_URL.format(code=code),
                        timeout=25, headers={"User-Agent": _UA})
    resp.raise_for_status()
    payload = resp.json()
    meta, history = payload.get("meta", {}), payload.get("data", [])
    if not history:
        return None

    latest = history[0]
    nav = float(latest["nav"])
    nav_date = datetime.strptime(latest["date"], "%d-%m-%Y")

    def trailing_return(days):
        base = _nav_on_or_before(history, nav_date - timedelta(days=days))
        if not base or base <= 0:
            return None
        years = days / 365.0
        total = nav / base
        # Annualise multi-year returns (CAGR); keep 1y as plain return.
        pct = (total ** (1 / years) - 1) * 100 if years > 1.5 else (total - 1) * 100
        return round(pct, 2)

    # Annualised volatility from the last year of daily NAVs.
    volatility = None
    year_navs = [float(e["nav"]) for e in history[:250]]
    if len(year_navs) > 30:
        import numpy as np
        arr = np.array(year_navs[::-1])  # oldest → newest
        daily = np.diff(np.log(arr))
        volatility = round(float(np.std(daily)) * (252 ** 0.5) * 100, 2)

    category = meta.get("scheme_category", "")
    # "Equity Scheme - Large Cap Fund" → "Large Cap Fund"
    category = category.split(" - ")[-1] if " - " in category else category

    return {
        "name":        meta.get("scheme_name", f"Scheme {code}"),
        "fund_house":  meta.get("fund_house", ""),
        "category":    category,
        "risk":        _risk_label(volatility),
        "nav":         round(nav, 2),
        "nav_date":    nav_date.strftime("%d %b %Y"),
        "returns_1y":  trailing_return(365),
        "returns_3y":  trailing_return(365 * 3),
        "volatility_pct": volatility,
    }


def _fetch_mf() -> List[dict]:
    """Live NAVs + trailing returns for the whole MF universe (parallel)."""
    from concurrent.futures import ThreadPoolExecutor

    def safe(code):
        # mfapi.in throttles parallel bursts — one retry rescues most misses.
        for attempt in (1, 2):
            try:
                return _fetch_one_mf(code)
            except Exception as e:
                if attempt == 2:
                    logger.warning(f"MF scheme {code} fetch failed: {e}")
        return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(safe, MF_SCHEME_CODES))
    return [r for r in rows if r]


def _fetch_fd() -> List[dict]:
    """Scrape BankBazaar's FD rate comparison table: bank name + the
    regular and senior-citizen rate ranges (server-rendered HTML)."""
    resp = requests.get(FD_RATES_URL, timeout=25, headers={"User-Agent": _UA})
    resp.raise_for_status()
    html = resp.text

    rows, seen = [], set()
    for tr in re.split(r"<tr[\s>]", html):
        bank_match = re.search(
            r'<a href="[^"]*fixed-deposit[^"]*"[^>]*>([^<]{3,60})</a>', tr)
        rates = re.findall(r"(\d{1,2}\.\d{2})%\s*-\s*(\d{1,2}\.\d{2})%", tr)
        if not bank_match or len(rates) < 2:
            continue
        bank = bank_match.group(1).strip()
        if bank.lower() in seen:
            continue
        seen.add(bank.lower())
        (reg_lo, reg_hi), (sen_lo, sen_hi) = rates[0], rates[1]
        rows.append({
            "bank":         bank,
            "rate_regular": f"{reg_lo}% – {reg_hi}%",
            "rate_senior":  f"{sen_lo}% – {sen_hi}%",
            "rate_max":     float(reg_hi),
        })
        if len(rows) >= FD_MAX_BANKS:
            break

    # Best offers first.
    rows.sort(key=lambda r: r["rate_max"], reverse=True)
    return rows


_FETCHERS = {
    "equity": _fetch_equity,
    "gold":   _fetch_gold,
    "mf":     _fetch_mf,
    "debt":   _fetch_debt,
    "fd":     _fetch_fd,
}


# ── Cache machinery (stale-while-refresh, single-flight) ─────────────────────


def _refresh(kind: str):
    """Blocking fetch of one pick list; stores only non-empty results."""
    try:
        try:
            rows = _FETCHERS[kind]()
        except Exception as e:
            logger.warning(f"Live {kind} picks fetch failed: {e}")
            rows = []
        # The gold list always contains the static SGB row — live data
        # means at least one row beyond it.
        got_live = len(rows) > 1 if kind == "gold" else bool(rows)

        with _lock:
            if got_live or not _caches[kind]["data"]:
                _caches[kind] = {"data": rows, "at": time.time()}
                _save_disk_cache()
            if got_live:
                logger.success(f"Live {kind} picks refreshed ({len(rows)} rows)")
            else:
                logger.warning(f"Live {kind} picks fetch returned nothing")
    finally:
        with _lock:
            _refreshing.discard(kind)


def _get_picks(kind: str, force_refresh: bool = False) -> List[dict]:
    _load_disk_cache_once()

    with _lock:
        cache = _caches[kind]
        fresh = cache["data"] and (time.time() - cache["at"]) / 3600 < CACHE_H[kind]
        if fresh and not force_refresh:
            return cache["data"]

        has_data = bool(cache["data"])
        already_refreshing = kind in _refreshing
        if not already_refreshing:
            _refreshing.add(kind)

    if has_data:
        # Serve stale data now; refresh in the background (single-flight).
        if not already_refreshing:
            threading.Thread(target=_refresh, args=(kind,),
                             daemon=True, name=f"picks-{kind}").start()
        return _caches[kind]["data"]

    # First-ever fetch: nothing to serve, so this one blocks.
    if not already_refreshing:
        _refresh(kind)
    return _caches[kind]["data"] or []


# ── Risk-based selection from live data ───────────────────────────────────────


def _select_equity(rows: List[dict], risk_appetite: str) -> List[dict]:
    """Pick the top stocks for the user's risk profile from live data:
    low risk → most stable (lowest annualised volatility with a positive
    1-year return where possible); high risk → strongest 1-year momentum;
    medium → best return-per-unit-of-risk. Selection changes as the
    market data changes."""
    usable = [r for r in rows
              if r.get("returns_1y_pct") is not None and r.get("volatility_pct")]
    if not usable:
        return rows[:EQUITY_PICK_COUNT]

    risk = risk_appetite.lower()
    if risk == "low":
        # Stable stocks first, preferring those with a positive year —
        # but always fill the list even in a bearish market.
        ranked = sorted(usable,
                        key=lambda r: (r["returns_1y_pct"] <= 0, r["volatility_pct"]))
    elif risk == "high":
        ranked = sorted(usable, key=lambda r: r["returns_1y_pct"], reverse=True)
    else:
        ranked = sorted(usable,
                        key=lambda r: r["returns_1y_pct"] / r["volatility_pct"],
                        reverse=True)
    return ranked[:EQUITY_PICK_COUNT]


def _select_mf(rows: List[dict], risk_appetite: str) -> List[dict]:
    """Same idea as _select_equity but on live NAV-derived figures:
    low → calmest funds (liquid/debt end up here naturally), high →
    strongest 1-year performers, medium → best return per unit of risk."""
    usable = [r for r in rows
              if r.get("returns_1y") is not None and r.get("volatility_pct")]
    if not usable:
        return rows[:MF_PICK_COUNT]

    risk = risk_appetite.lower()
    if risk == "low":
        ranked = sorted(usable, key=lambda r: r["volatility_pct"])
    elif risk == "high":
        ranked = sorted(usable, key=lambda r: r["returns_1y"], reverse=True)
    else:
        ranked = sorted(usable,
                        key=lambda r: r["returns_1y"] / max(r["volatility_pct"], 0.05),
                        reverse=True)
    return ranked[:MF_PICK_COUNT]


# ── Public API ────────────────────────────────────────────────────────────────


def get_equity_picks(risk_appetite: str = "medium",
                     force_refresh: bool = False) -> List[dict]:
    return _select_equity(_get_picks("equity", force_refresh), risk_appetite)


def get_gold_picks(force_refresh: bool = False) -> List[dict]:
    return _get_picks("gold", force_refresh)


def get_mutual_fund_picks(risk_appetite: str = "medium",
                          force_refresh: bool = False) -> List[dict]:
    return _select_mf(_get_picks("mf", force_refresh), risk_appetite)


def get_debt_picks(force_refresh: bool = False) -> List[dict]:
    return _get_picks("debt", force_refresh)


def get_fd_picks(force_refresh: bool = False) -> List[dict]:
    return _get_picks("fd", force_refresh)


def get_all_picks(risk_appetite: str = "medium") -> dict:
    return {
        "equity":       get_equity_picks(risk_appetite),
        "mutual_funds": get_mutual_fund_picks(risk_appetite),
        "gold":         get_gold_picks(),
        "debt":         get_debt_picks(),
        "fd":           get_fd_picks(),
    }
