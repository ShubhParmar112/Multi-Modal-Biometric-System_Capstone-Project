"""
AI Financial Advisor — powered by Groq (Llama 3.1 70B).

Strategy: pull the user's live financial data from the DB, inject it as
context into the system prompt, then let the LLM answer freely. This
gives accurate, nuanced responses without any hand-coded keyword rules.
"""

from datetime import datetime
from typing import List

from groq import Groq

import config
from analytics.reports import _shift_month
from database.db_manager import DatabaseManager
from portfolio.service import PortfolioService
from utils.logger import logger

INCOME_TYPES  = {"deposit", "transfer_in"}
EXPENSE_TYPES = {"withdraw", "transfer_out"}

ASSET_LABELS = {
    "equity": "Equity", "debt": "Debt", "gold": "Gold",
    "fd": "Fixed Deposits", "cash": "Cash", "mutual_funds": "Mutual Funds",
}

# Lazily constructed so a missing key breaks only the advisor endpoint,
# not the import of every router that transitively pulls this module in.
_groq = None


def _get_client():
    global _groq
    if _groq is None and config.GROQ_API_KEY:
        _groq = Groq(
            api_key=config.GROQ_API_KEY,
            timeout=config.GROQ_TIMEOUT,
            max_retries=1,
        )
    return _groq


# ── Context builder ───────────────────────────────────────────────────────────

def _month_key(ts: str) -> str:
    return ts[:7]


def _build_context(user_id: str, db: DatabaseManager) -> str:
    lines: List[str] = []
    now = datetime.now()
    this_mk = f"{now.year:04d}-{now.month:02d}"

    # ── Account & balance ─────────────────────────────────────────────────────
    accounts = db.get_accounts_by_user(user_id)
    if not accounts:
        return "No bank account found for this user."
    acc = accounts[0]
    lines.append(f"Account Number : {acc['account_number']}")
    lines.append(f"Account Type   : {acc['account_type']}")
    lines.append(f"Current Balance: ₹{acc['balance']:,.2f}")
    lines.append("")

    # ── Transaction history (last 200, excluding blocked) ────────────────────
    raw = db.get_transactions(acc["account_id"], limit=200)
    txns = [t for t in raw if t["status"] != "blocked"]

    # This month
    this_txns = [t for t in txns if _month_key(t["timestamp"]) == this_mk]
    inc_this  = sum(t["amount"] for t in this_txns if t["txn_type"] in INCOME_TYPES)
    exp_this  = sum(t["amount"] for t in this_txns if t["txn_type"] in EXPENSE_TYPES)
    cats_this: dict = {}
    for t in this_txns:
        if t["txn_type"] in EXPENSE_TYPES:
            c = t.get("category") or "Other"
            cats_this[c] = cats_this.get(c, 0.0) + t["amount"]

    lines.append(f"=== This Month ({this_mk}) ===")
    lines.append(f"  Income  : ₹{inc_this:,.2f}")
    lines.append(f"  Expenses: ₹{exp_this:,.2f}")
    lines.append(f"  Net     : ₹{inc_this - exp_this:,.2f}")
    if cats_this:
        top = sorted(cats_this.items(), key=lambda x: -x[1])
        lines.append("  Category breakdown:")
        for cat, amt in top:
            lines.append(f"    - {cat}: ₹{amt:,.2f}")
    lines.append("")

    # Last 3 months summary
    lines.append("=== Last 3 Months ===")
    for i in range(1, 4):
        y, m = _shift_month(now.year, now.month, -i)
        mk = f"{y:04d}-{m:02d}"
        mo_txns = [t for t in txns if _month_key(t["timestamp"]) == mk]
        inc = sum(t["amount"] for t in mo_txns if t["txn_type"] in INCOME_TYPES)
        exp = sum(t["amount"] for t in mo_txns if t["txn_type"] in EXPENSE_TYPES)
        lines.append(f"  {mk}: Income ₹{inc:,.2f} | Expenses ₹{exp:,.2f} | Savings ₹{inc - exp:,.2f}")
    lines.append("")

    # Last 5 transactions
    lines.append("=== 5 Most Recent Transactions ===")
    for t in txns[:5]:
        sign = "+" if t["txn_type"] in INCOME_TYPES else "-"
        cat  = t.get("category") or "Other"
        lines.append(
            f"  {t['timestamp'][:10]}  {sign}₹{t['amount']:,.2f}"
            f"  [{t['txn_type']}]  [{cat}]"
        )
    lines.append("")

    # ── Investment profile & recommendation ───────────────────────────────────
    svc     = PortfolioService(db)
    profile = svc.get_profile(user_id)
    if profile:
        lines.append("=== Investment Profile ===")
        lines.append(f"  Risk Appetite     : {profile['risk_appetite']}")
        lines.append(f"  Horizon           : {profile['investment_horizon_years']} years")
        lines.append(f"  Monthly Savings   : ₹{profile['monthly_savings']:,.2f}")
        lines.append(f"  Available Balance : ₹{profile['available_balance']:,.2f}")
        lines.append("")

        rec = svc.get_latest_recommendation(user_id)
        if rec:
            lines.append("=== Latest Portfolio Recommendation ===")
            for key, label in ASSET_LABELS.items():
                pct = rec.get(f"{key}_pct", 0)
                if pct > 0:
                    lines.append(f"  {label}: {pct}%")
            lines.append(f"  Expected Return : {rec['expected_return']}%")
            lines.append(f"  Expected Risk   : {rec['expected_risk']}%")
            lines.append(f"  Sharpe Ratio    : {rec['sharpe_ratio']}")

    snapshot = _market_snapshot()
    if snapshot:
        lines.append("")
        lines.append(snapshot)

    return "\n".join(lines)


def _market_snapshot() -> str:
    """Live market context (served from the portfolio module's caches) so
    the advisor can answer general market questions, not just personal ones."""
    try:
        from portfolio import market_data, specific_picks

        lines = ["=== Live Market Snapshot ==="]
        stats = market_data.get_asset_statistics()
        market_labels = {"equity": "Equity (NIFTY 50)", "debt": "Debt",
                         "gold": "Gold", "mutual_funds": "Mutual Funds"}
        for key, label in market_labels.items():
            ret = stats["returns"].get(key)
            vol = stats["volatility"].get(key)
            if ret is not None and vol is not None:
                lines.append(f"  {label}: annualised return {ret * 100:.1f}%, "
                             f"volatility {vol * 100:.1f}%")

        equity = specific_picks.get_equity_picks("medium")
        if equity:
            lines.append("  Top NSE large-caps (live prices):")
            for row in equity[:6]:
                extra = ""
                if row.get("returns_1y_pct") is not None:
                    extra = f", 1Y return {row['returns_1y_pct']:+.1f}%"
                lines.append(f"    - {row['name']}: ₹{row['price']:,} "
                             f"({row['change_pct']:+.2f}% today{extra})")
        return "\n".join(lines)
    except Exception:
        return ""


# ── LLM call ─────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are NoryvX's AI Financial Advisor — a helpful, concise expert on the \
user's personal finances. You have access to their real account data below.

STRICT SCOPE — read carefully:
- You may ONLY discuss finance and money: the user's accounts, transactions, \
spending, savings, budgeting, investments, markets, banking products, loans, \
insurance, taxes, and general personal-finance concepts.
- If the user asks about ANYTHING else (coding, homework, entertainment, \
trivia, health, relationships, politics, etc.), do not answer it. Reply only: \
"That's out of my range of abilities — I can only help with finance and \
money-related questions." Do not add anything after that sentence.
- For general finance or market questions, answer from the Live Market \
Snapshot below plus your general financial knowledge, with a note that \
markets change quickly.
- Never invent numbers about the user's personal accounts — if a personal \
figure is not in the data, say so and suggest what the user can do.

STYLE: Format currency in Indian style with the ₹ symbol (e.g. ₹1,23,456.78). \
Use **bold** for key numbers. Keep replies under 200 words unless a detailed \
breakdown is genuinely needed.

--- LIVE FINANCIAL DATA ---
{context}
--- END DATA ---\
"""


def answer(user_id: str, question: str, history: list,
           db: DatabaseManager) -> str:
    client = _get_client()
    if client is None:
        return ("The AI advisor isn't configured yet — add your GROQ_API_KEY "
                "to the .env file in the project root and restart the server.")

    context  = _build_context(user_id, db)
    sys_msg  = _SYSTEM.format(context=context)

    messages = [{"role": "system", "content": sys_msg}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    try:
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            max_tokens=512,
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Advisor LLM call failed: {e}")
        detail = str(e)
        if "decommissioned" in detail or "model_not_found" in detail:
            return ("The configured AI model is no longer available on Groq. "
                    "Set GROQ_MODEL in .env to a model Groq still serves "
                    "(e.g. openai/gpt-oss-120b) and restart the server. "
                    "The current list is at console.groq.com/docs/models.")
        return "Sorry, I couldn't reach the AI service right now. Please try again in a moment."


# ── One-shot portfolio advisory (Portfolio page panel) ───────────────────────

_ADVISORY_PROMPT = """\
Write a structured portfolio advisory for this user based ONLY on the live \
financial data in the system prompt. Use exactly these five markdown \
sections, each starting with "### ":

### Health Summary
2-3 sentences on the overall state of their finances and investments.

### Key Observations
3-4 bullet points on savings rate, spending, allocation, and diversification.

### Allocation & Rebalancing
Comment on the latest recommendation (or the lack of one) and what to \
adjust. Reference the actual percentages.

### Risk Factors & Market Outlook
2-3 bullets grounded in the Live Market Snapshot figures.

### Actionable Insight
One concrete next step with a rupee amount where possible.

Keep the whole advisory under 350 words. Format currency Indian-style with ₹.\
"""


def _advisory_fallback(user_id: str, db: DatabaseManager) -> str:
    """Data-driven advisory used when Groq is unreachable — every figure
    comes from the DB / market caches, nothing is invented."""
    svc = PortfolioService(db)
    profile = svc.get_profile(user_id)
    rec = svc.get_latest_recommendation(user_id) if profile else None

    lines = ["### Health Summary"]
    if profile:
        lines.append(
            f"You invest with a **{profile['risk_appetite']}** risk appetite over a "
            f"**{profile['investment_horizon_years']}-year** horizon, saving about "
            f"**₹{profile['monthly_savings']:,.0f}** a month with "
            f"**₹{profile['available_balance']:,.0f}** available to deploy.")
    else:
        lines.append("No investment profile yet — save one to get a "
                     "personalised allocation.")

    if rec:
        lines.append("")
        lines.append("### Allocation & Rebalancing")
        for key, label in ASSET_LABELS.items():
            pct = rec.get(f"{key}_pct") or 0
            if pct > 0:
                lines.append(f"- {label}: **{pct}%**")
        lines.append(f"- Expected return **{rec['expected_return']}%** at "
                     f"**{rec['expected_risk']}%** volatility "
                     f"(Sharpe {rec['sharpe_ratio']}).")

    lines.append("")
    lines.append("### Actionable Insight")
    if profile and not rec:
        lines.append("Generate a recommendation to see your optimal asset mix.")
    elif rec:
        lines.append("Review the Smart Investment Plan below to convert these "
                     "percentages into exact units, and rebalance anything "
                     "drifted more than 5% from target.")
    else:
        lines.append("Fill in the Investment Profile form above to get started.")

    return "\n".join(lines)


def portfolio_advisory(user_id: str, db: DatabaseManager) -> dict:
    """One-shot structured advisory for the Portfolio page.
    Returns {"advisory": markdown, "is_fallback": bool}."""
    client = _get_client()
    if client is not None:
        context = _build_context(user_id, db)
        sys_msg = _SYSTEM.format(context=context)
        try:
            resp = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": _ADVISORY_PROMPT},
                ],
                max_tokens=900,
                temperature=0.3,
            )
            return {"advisory": resp.choices[0].message.content.strip(),
                    "is_fallback": False}
        except Exception as e:
            logger.error(f"Portfolio advisory LLM call failed: {e}")

    return {"advisory": _advisory_fallback(user_id, db), "is_fallback": True}
