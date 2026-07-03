"""Portfolio optimization endpoints - thin wrapper over PortfolioService."""

from fastapi import APIRouter, Depends, HTTPException

from database.db_manager import DatabaseManager
from portfolio import market_data, optimizer, specific_picks
from portfolio.service import PortfolioService
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import InvestmentProfileRequest

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def get_portfolio_service(db: DatabaseManager = Depends(get_db)) -> PortfolioService:
    return PortfolioService(db)


@router.get("/profile")
def get_profile(user=Depends(get_current_user),
                service: PortfolioService = Depends(get_portfolio_service)):
    profile = service.get_profile(user["user_id"])
    if not profile:
        raise HTTPException(status_code=404, detail="No investment profile found")
    return profile


@router.post("/profile")
def save_profile(req: InvestmentProfileRequest, user=Depends(get_current_user),
                 service: PortfolioService = Depends(get_portfolio_service)):
    success = service.save_profile(
        user["user_id"], req.risk_appetite, req.investment_horizon_years,
        req.monthly_savings, req.available_balance
    )
    return {"success": success}


@router.post("/recommendation")
def generate_recommendation(user=Depends(get_current_user),
                            service: PortfolioService = Depends(get_portfolio_service)):
    result = service.generate_recommendation(user["user_id"])
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Save an investment profile before generating a recommendation"
        )
    return result


@router.get("/recommendation")
def get_recommendation(user=Depends(get_current_user),
                       service: PortfolioService = Depends(get_portfolio_service)):
    result = service.get_latest_recommendation(user["user_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="No recommendation found")
    return result


@router.get("/efficient-frontier")
def get_efficient_frontier(n_points: int = 20, user=Depends(get_current_user)):
    return optimizer.efficient_frontier(n_points)


@router.get("/asset-stats")
def get_asset_stats(user=Depends(get_current_user)):
    return market_data.get_asset_statistics()


@router.get("/picks")
def get_picks(risk_appetite: str = "medium", user=Depends(get_current_user)):
    return specific_picks.get_all_picks(risk_appetite)
