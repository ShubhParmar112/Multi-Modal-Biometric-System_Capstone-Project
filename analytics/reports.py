"""
Personal Finance Analytics - monthly reports, spending/savings trends, and
cash flow, computed from an account's transaction history. Pure Python
aggregation (no pandas) since transaction volumes in this system are small.
"""

from datetime import datetime
from typing import Dict, List, Optional

from database.db_manager import DatabaseManager

INCOME_TYPES = {"deposit", "transfer_in"}
EXPENSE_TYPES = {"withdraw", "transfer_out"}


def _shift_month(year: int, month: int, delta: int) -> tuple:
    """Shift (year, month) by delta months (negative = go back)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _last_n_months(n: int) -> List[tuple]:
    """Return the last n (year, month) tuples, oldest first, including the current month."""
    now = datetime.now()
    return [_shift_month(now.year, now.month, -i) for i in range(n - 1, -1, -1)]


class FinanceAnalytics:
    """Computes spending/savings analytics for a user's primary account."""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def _primary_account(self, user_id: str) -> Optional[dict]:
        accounts = self.db.get_accounts_by_user(user_id)
        return accounts[0] if accounts else None

    def _transactions(self, user_id: str) -> List[dict]:
        account = self._primary_account(user_id)
        if not account:
            return []
        txns = self.db.get_transactions(account["account_id"], limit=1000)
        return [t for t in txns if t["status"] != "blocked"]

    @staticmethod
    def _month_key(timestamp: str) -> str:
        return timestamp[:7]  # "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM"

    def monthly_report(self, user_id: str, year: int = None,
                       month: int = None) -> Dict:
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        target = f"{year:04d}-{month:02d}"

        total_income = 0.0
        total_expense = 0.0
        category_breakdown: Dict[str, float] = {}

        for txn in self._transactions(user_id):
            if self._month_key(txn["timestamp"]) != target:
                continue
            if txn["txn_type"] in INCOME_TYPES:
                total_income += txn["amount"]
            elif txn["txn_type"] in EXPENSE_TYPES:
                total_expense += txn["amount"]
                category = txn.get("category") or "Other"
                category_breakdown[category] = (
                    category_breakdown.get(category, 0.0) + txn["amount"]
                )

        return {
            "month": target,
            "total_income": round(total_income, 2),
            "total_expense": round(total_expense, 2),
            "net_savings": round(total_income - total_expense, 2),
            "category_breakdown": {k: round(v, 2) for k, v in category_breakdown.items()},
        }

    def spending_trend(self, user_id: str, months: int = 6) -> List[Dict]:
        month_keys = [f"{y:04d}-{m:02d}" for y, m in _last_n_months(months)]
        totals = {k: 0.0 for k in month_keys}

        for txn in self._transactions(user_id):
            key = self._month_key(txn["timestamp"])
            if key in totals and txn["txn_type"] in EXPENSE_TYPES:
                totals[key] += txn["amount"]

        return [{"month": k, "total_spend": round(totals[k], 2)} for k in month_keys]

    def savings_trend(self, user_id: str, months: int = 6) -> List[Dict]:
        month_keys = [f"{y:04d}-{m:02d}" for y, m in _last_n_months(months)]
        income = {k: 0.0 for k in month_keys}
        expense = {k: 0.0 for k in month_keys}

        for txn in self._transactions(user_id):
            key = self._month_key(txn["timestamp"])
            if key not in income:
                continue
            if txn["txn_type"] in INCOME_TYPES:
                income[key] += txn["amount"]
            elif txn["txn_type"] in EXPENSE_TYPES:
                expense[key] += txn["amount"]

        return [
            {
                "month": k,
                "income": round(income[k], 2),
                "expense": round(expense[k], 2),
                "net_savings": round(income[k] - expense[k], 2),
            }
            for k in month_keys
        ]

    def cash_flow(self, user_id: str, months: int = 6) -> List[Dict]:
        month_keys = [f"{y:04d}-{m:02d}" for y, m in _last_n_months(months)]
        inflow = {k: 0.0 for k in month_keys}
        outflow = {k: 0.0 for k in month_keys}

        for txn in self._transactions(user_id):
            key = self._month_key(txn["timestamp"])
            if key not in inflow:
                continue
            if txn["txn_type"] in INCOME_TYPES:
                inflow[key] += txn["amount"]
            elif txn["txn_type"] in EXPENSE_TYPES:
                outflow[key] += txn["amount"]

        return [
            {"month": k, "inflow": round(inflow[k], 2), "outflow": round(outflow[k], 2)}
            for k in month_keys
        ]
