"""
Specific investment picks per asset class.
Equity and Gold ETF data fetched live via yfinance (cached 1 h).
Mutual funds, Debt, and FD are curated static lists — yfinance has no
INR mutual-fund NAV support.
"""

import json
import os
import threading
import time
from typing import List

import config
from portfolio import yf_worker
from utils.logger import logger

# ── Candidate universes ──────────────────────────────────────────────────────
# These are only symbol lookup tables (Yahoo tickers + display labels) — no
# market figures live here. Prices, day change, 1-year return, volatility and
# the 52-week range are all fetched/computed live, and the picks actually
# shown are SELECTED dynamically from that live data based on the user's risk
# appetite (see _select_equity). A symbol that fails to fetch (delisted,
# renamed, or one of the tickers that crashes the yfinance stack) is simply
# skipped — its fetch runs in an isolated subprocess.
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

EQUITY_PICK_COUNT = 6

CACHE_H = 1.0
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
# background thread refreshes them — a request never waits on Yahoo unless
# there is no data at all (the very first run).
_caches = {
    "equity": {"data": None, "at": 0.0},
    "gold":   {"data": None, "at": 0.0},
}
_TICKERS = {"equity": lambda: EQUITY_UNIVERSE, "gold": lambda: GOLD_UNIVERSE}
_lock = threading.Lock()
_refreshing: set = set()
_disk_loaded = False


# Bump when the row schema changes so stale disk caches are discarded.
_CACHE_VERSION = 2


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


def _refresh(kind: str):
    """Blocking fetch of one pick list; stores only non-empty results."""
    try:
        rows = yf_worker.fetch_quotes_isolated(
            _TICKERS[kind](), config.PORTFOLIO_PICKS_TIMEOUT)
        if kind == "gold":
            rows = rows + [_SGB_ROW]
            got_live = len(rows) > 1
        else:
            got_live = bool(rows)

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


def _get_picks(kind: str, force_refresh: bool) -> List[dict]:
    _load_disk_cache_once()

    with _lock:
        cache = _caches[kind]
        fresh = cache["data"] and (time.time() - cache["at"]) / 3600 < CACHE_H
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


def get_equity_picks(risk_appetite: str = "medium",
                     force_refresh: bool = False) -> List[dict]:
    universe = _get_picks("equity", force_refresh)
    return _select_equity(universe, risk_appetite)


def get_gold_picks(force_refresh: bool = False) -> List[dict]:
    return _get_picks("gold", force_refresh)


# ── Mutual funds — curated, risk-bucketed ─────────────────────────────────────

_MF: dict = {
    "low": [
        {"name": "HDFC Liquid Fund",              "category": "Liquid",             "rating": "5★", "risk": "Low",             "returns_1y": 7.2,  "returns_3y": 5.8,  "min_sip": 500,  "aum": "₹68,000 Cr"},
        {"name": "Axis Liquid Fund",               "category": "Liquid",             "rating": "5★", "risk": "Low",             "returns_1y": 7.1,  "returns_3y": 5.7,  "min_sip": 500,  "aum": "₹32,000 Cr"},
        {"name": "SBI Short Term Debt Fund",       "category": "Short Duration",     "rating": "4★", "risk": "Low–Moderate",   "returns_1y": 7.8,  "returns_3y": 6.4,  "min_sip": 500,  "aum": "₹12,000 Cr"},
        {"name": "ICICI Pru Corporate Bond Fund",  "category": "Corporate Bond",     "rating": "5★", "risk": "Low–Moderate",   "returns_1y": 8.1,  "returns_3y": 6.9,  "min_sip": 1000, "aum": "₹25,000 Cr"},
    ],
    "medium": [
        {"name": "Mirae Asset Large Cap Fund",     "category": "Large Cap",          "rating": "5★", "risk": "Moderately High", "returns_1y": 16.2, "returns_3y": 14.5, "min_sip": 1000, "aum": "₹37,000 Cr"},
        {"name": "Axis Bluechip Fund",             "category": "Large Cap",          "rating": "5★", "risk": "Moderately High", "returns_1y": 14.8, "returns_3y": 13.2, "min_sip": 500,  "aum": "₹31,000 Cr"},
        {"name": "Kotak Emerging Equity Fund",     "category": "Mid Cap",            "rating": "4★", "risk": "High",            "returns_1y": 22.1, "returns_3y": 18.4, "min_sip": 1000, "aum": "₹40,000 Cr"},
        {"name": "HDFC Balanced Advantage Fund",   "category": "Balanced Advantage", "rating": "5★", "risk": "Moderate",        "returns_1y": 18.5, "returns_3y": 15.7, "min_sip": 500,  "aum": "₹72,000 Cr"},
        {"name": "Parag Parikh Flexi Cap Fund",    "category": "Flexi Cap",          "rating": "5★", "risk": "Moderately High", "returns_1y": 24.3, "returns_3y": 21.5, "min_sip": 1000, "aum": "₹58,000 Cr"},
    ],
    "high": [
        {"name": "Nippon India Small Cap Fund",    "category": "Small Cap",          "rating": "5★", "risk": "Very High",       "returns_1y": 38.5, "returns_3y": 27.3, "min_sip": 100,  "aum": "₹46,000 Cr"},
        {"name": "Quant Mid Cap Fund",             "category": "Mid Cap",            "rating": "5★", "risk": "Very High",       "returns_1y": 42.1, "returns_3y": 30.8, "min_sip": 1000, "aum": "₹8,500 Cr"},
        {"name": "HDFC Mid-Cap Opportunities",     "category": "Mid Cap",            "rating": "5★", "risk": "High",            "returns_1y": 29.4, "returns_3y": 24.6, "min_sip": 100,  "aum": "₹55,000 Cr"},
        {"name": "Parag Parikh Flexi Cap Fund",    "category": "Flexi Cap",          "rating": "5★", "risk": "Moderately High", "returns_1y": 24.3, "returns_3y": 21.5, "min_sip": 1000, "aum": "₹58,000 Cr"},
        {"name": "Quant Active Fund",              "category": "Multi Cap",          "rating": "5★", "risk": "Very High",       "returns_1y": 36.2, "returns_3y": 28.9, "min_sip": 1000, "aum": "₹9,200 Cr"},
    ],
}


def get_mutual_fund_picks(risk_appetite: str = "medium") -> List[dict]:
    return _MF.get(risk_appetite.lower(), _MF["medium"])


# ── Debt instruments ──────────────────────────────────────────────────────────

DEBT_PICKS = [
    {"type": "Govt. Bond",  "name": "RBI Floating Rate Bond",      "rate": "8.05% p.a.",        "tenure": "7 years",     "risk": "Nil",        "min_invest": "₹1,000"},
    {"type": "Corp. Bond",  "name": "HDFC Corp Bond (AAA)",        "rate": "7.8–8.2% p.a.",    "tenure": "3–5 years",   "risk": "Very Low",   "min_invest": "₹10,000"},
    {"type": "PPF",         "name": "Public Provident Fund",        "rate": "7.1% p.a.",         "tenure": "15 years",    "risk": "Nil",        "min_invest": "₹500/yr"},
    {"type": "NPS",         "name": "National Pension System",      "rate": "9–12% (mkt-linked)","tenure": "Till age 60", "risk": "Low–Medium", "min_invest": "₹500"},
    {"type": "Debt MF",     "name": "HDFC Short Term Debt Fund",   "rate": "7.5–8.0% p.a.",    "tenure": "Flexible",    "risk": "Low",        "min_invest": "₹100 SIP"},
]

# ── FD rates ──────────────────────────────────────────────────────────────────

FD_PICKS = [
    {"bank": "IDFC First Bank",     "rate_1y": 7.50, "rate_3y": 7.25, "rate_5y": 7.00, "special": "Senior: +0.5%"},
    {"bank": "RBL Bank",            "rate_1y": 7.50, "rate_3y": 7.10, "rate_5y": 6.90, "special": "Senior: +0.5%"},
    {"bank": "Kotak Mahindra Bank", "rate_1y": 7.10, "rate_3y": 7.00, "rate_5y": 6.90, "special": ""},
    {"bank": "HDFC Bank",           "rate_1y": 7.00, "rate_3y": 7.00, "rate_5y": 7.00, "special": ""},
    {"bank": "SBI",                 "rate_1y": 6.80, "rate_3y": 6.75, "rate_5y": 6.50, "special": "Tax-saving FD"},
]


def get_all_picks(risk_appetite: str = "medium") -> dict:
    return {
        "equity":       get_equity_picks(risk_appetite),
        "mutual_funds": get_mutual_fund_picks(risk_appetite),
        "gold":         get_gold_picks(),
        "debt":         DEBT_PICKS,
        "fd":           FD_PICKS,
    }
