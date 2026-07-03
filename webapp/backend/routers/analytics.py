"""Analytics endpoints - thin wrapper over FinanceAnalytics (analytics/reports.py)."""

from typing import Optional
from fastapi import APIRouter, Depends

from analytics.reports import FinanceAnalytics
from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import CategoryRequest

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def get_analytics(db: DatabaseManager = Depends(get_db)) -> FinanceAnalytics:
    return FinanceAnalytics(db)


@router.get("/monthly-report")
def monthly_report(year: Optional[int] = None, month: Optional[int] = None,
                   user=Depends(get_current_user),
                   analytics: FinanceAnalytics = Depends(get_analytics)):
    return analytics.monthly_report(user["user_id"], year, month)


@router.get("/spending-trend")
def spending_trend(months: int = 6, user=Depends(get_current_user),
                   analytics: FinanceAnalytics = Depends(get_analytics)):
    return analytics.spending_trend(user["user_id"], months)


@router.get("/savings-trend")
def savings_trend(months: int = 6, user=Depends(get_current_user),
                  analytics: FinanceAnalytics = Depends(get_analytics)):
    return analytics.savings_trend(user["user_id"], months)


@router.get("/cash-flow")
def cash_flow(months: int = 6, user=Depends(get_current_user),
             analytics: FinanceAnalytics = Depends(get_analytics)):
    return analytics.cash_flow(user["user_id"], months)


@router.get("/categories")
def get_categories(user=Depends(get_current_user), db: DatabaseManager = Depends(get_db)):
    return db.get_categories()


@router.post("/categories")
def add_category(req: CategoryRequest, user=Depends(get_current_user),
                 db: DatabaseManager = Depends(get_db)):
    return {"success": db.add_category(req.name)}
