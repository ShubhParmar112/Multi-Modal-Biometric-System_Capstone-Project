"""
Portfolio Service - investment profile CRUD + recommendation generation,
built on top of DatabaseManager's CRUD (database/db_manager.py) and the
Markowitz optimizer (portfolio/optimizer.py).
"""

from typing import Optional

from database.db_manager import DatabaseManager
from portfolio import optimizer


class PortfolioService:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def get_profile(self, user_id: str) -> Optional[dict]:
        return self.db.get_investment_profile(user_id)

    def save_profile(self, user_id: str, risk_appetite: str,
                     investment_horizon_years: int, monthly_savings: float,
                     available_balance: float) -> bool:
        return self.db.upsert_investment_profile(
            user_id, risk_appetite, investment_horizon_years,
            monthly_savings, available_balance
        )

    def generate_recommendation(self, user_id: str) -> Optional[dict]:
        profile = self.get_profile(user_id)
        if not profile:
            return None

        allocation = optimizer.optimize_portfolio(profile["risk_appetite"])
        self.db.save_portfolio_recommendation(
            profile["profile_id"],
            equity_pct=allocation["equity_pct"],
            debt_pct=allocation["debt_pct"],
            gold_pct=allocation["gold_pct"],
            fd_pct=allocation["fd_pct"],
            cash_pct=allocation["cash_pct"],
            mutual_funds_pct=allocation["mutual_funds_pct"],
            expected_return=allocation["expected_return"],
            expected_risk=allocation["expected_risk"],
            sharpe_ratio=allocation["sharpe_ratio"],
        )
        return allocation

    def get_latest_recommendation(self, user_id: str) -> Optional[dict]:
        profile = self.get_profile(user_id)
        if not profile:
            return None
        return self.db.get_latest_portfolio_recommendation(profile["profile_id"])
