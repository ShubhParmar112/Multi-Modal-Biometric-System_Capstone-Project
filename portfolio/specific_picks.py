"""
Specific investment picks per asset class.
Equity and Gold ETF data fetched live via yfinance (cached 1 h).
Mutual funds, Debt, and FD are curated static lists — yfinance has no
INR mutual-fund NAV support.
"""

import time
from typing import List, Optional

import numpy as np
import yfinance as yf

from utils.logger import logger

# ── Equity picks — top Nifty 50 / large-cap stocks ───────────────────────────

EQUITY_TICKERS = {
    "RELIANCE.NS":   {"name": "Reliance Industries",        "sector": "Energy & Retail"},
    "TCS.NS":        {"name": "Tata Consultancy Services",  "sector": "IT"},
    "INFY.NS":       {"name": "Infosys",                    "sector": "IT"},
    "HDFCBANK.NS":   {"name": "HDFC Bank",                  "sector": "Banking"},
    "ICICIBANK.NS":  {"name": "ICICI Bank",                 "sector": "Banking"},
    "BHARTIARTL.NS": {"name": "Bharti Airtel",              "sector": "Telecom"},
    "HINDUNILVR.NS": {"name": "Hindustan Unilever",         "sector": "FMCG"},
    "WIPRO.NS":      {"name": "Wipro",                      "sector": "IT"},
}

# ── Gold ETFs ────────────────────────────────────────────────────────────────

GOLD_TICKERS = {
    "GOLDBEES.NS": {"name": "Nippon India Gold ETF (GOLDBEES)", "sector": "Gold ETF"},
    "SGOLD.NS":    {"name": "SBI Gold ETF (SGOLD)",             "sector": "Gold ETF"},
}

_equity_cache: dict = {"data": None, "at": 0.0}
_gold_cache:   dict = {"data": None, "at": 0.0}
CACHE_H = 1.0


def _stale(cache: dict) -> bool:
    return cache["data"] is None or (time.time() - cache["at"]) / 3600 > CACHE_H


def _safe_float(val, default=None):
    """Return float or default; handles None and NaN."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f  # NaN check
    except Exception:
        return default


def _fmt_cap(rupees) -> str:
    v = _safe_float(rupees, 0)
    if v <= 0:
        return "N/A"
    cr = v / 1e7  # INR → crore
    if cr >= 1_00_000:
        return f"₹{cr / 1_00_000:.1f}L Cr"
    if cr >= 1_000:
        return f"₹{cr / 1_000:.0f}K Cr"
    return f"₹{cr:.0f} Cr"


def _fetch_ticker(ticker: str, meta: dict) -> Optional[dict]:
    try:
        fi = yf.Ticker(ticker).fast_info
        price = _safe_float(fi.last_price)
        if price is None:
            return None
        prev = _safe_float(fi.previous_close, price)
        change_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
        return {
            "ticker":      ticker.replace(".NS", ""),
            "name":        meta["name"],
            "sector":      meta.get("sector", ""),
            "price":       round(price, 2),
            "change_pct":  change_pct,
            "market_cap":  _fmt_cap(fi.market_cap),
            "week52_high": round(_safe_float(fi.fifty_two_week_high, 0), 2),
            "week52_low":  round(_safe_float(fi.fifty_two_week_low, 0), 2),
        }
    except Exception as e:
        logger.warning(f"Skipping {ticker}: {e}")
        return None


def get_equity_picks(force_refresh: bool = False) -> List[dict]:
    if not force_refresh and not _stale(_equity_cache):
        return _equity_cache["data"]
    picks = [r for t, m in EQUITY_TICKERS.items() if (r := _fetch_ticker(t, m))]
    _equity_cache.update({"data": picks, "at": time.time()})
    return picks


def get_gold_picks(force_refresh: bool = False) -> List[dict]:
    if not force_refresh and not _stale(_gold_cache):
        return _gold_cache["data"]
    picks = [r for t, m in GOLD_TICKERS.items() if (r := _fetch_ticker(t, m))]
    picks.append({
        "ticker":      "SGB",
        "name":        "Sovereign Gold Bond (SGB)",
        "sector":      "Govt. Backed",
        "price":       None,
        "change_pct":  None,
        "market_cap":  "GoI Backed",
        "week52_high": None,
        "week52_low":  None,
        "note":        "2.5% p.a. interest + gold price appreciation. Capital gains tax-free on RBI maturity. Buy via banks, post offices, or NSE.",
    })
    _gold_cache.update({"data": picks, "at": time.time()})
    return picks


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
        "equity":       get_equity_picks(),
        "mutual_funds": get_mutual_fund_picks(risk_appetite),
        "gold":         get_gold_picks(),
        "debt":         DEBT_PICKS,
        "fd":           FD_PICKS,
    }
