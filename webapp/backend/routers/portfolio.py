"""Portfolio optimization endpoints - thin wrapper over PortfolioService,
HoldingsService, and the risk/planner/holdings-analytics modules."""

from fastapi import APIRouter, Depends, HTTPException

from advisor import nlp_engine
from database.db_manager import DatabaseManager
from portfolio import (
    holdings_engine, holdings_optimizer, market_data, optimizer, planner,
    risk, specific_picks,
)
from portfolio.holdings_service import HoldingsService, search_tickers
from portfolio.service import PortfolioService
from webapp.backend.auth import get_current_user, get_db, get_effective_user
from webapp.backend.schemas import (
    HoldingRequest, HoldingUpdateRequest, InvestmentProfileRequest, TradeRequest,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def get_portfolio_service(db: DatabaseManager = Depends(get_db)) -> PortfolioService:
    return PortfolioService(db)


def get_holdings_service(db: DatabaseManager = Depends(get_db)) -> HoldingsService:
    return HoldingsService(db)


def _profile_and_recommendation(service: PortfolioService, user_id: str):
    profile = service.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=400,
                            detail="Save an investment profile first")
    rec = service.get_latest_recommendation(user_id)
    if not rec:
        raise HTTPException(status_code=400,
                            detail="Generate a recommendation first")
    return profile, rec


@router.get("/profile")
def get_profile(user=Depends(get_effective_user),
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
def get_recommendation(user=Depends(get_effective_user),
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


# ── Risk, plan & advisory (on the recommended allocation) ────────────────────

@router.get("/var")
def get_var(user=Depends(get_effective_user),
            service: PortfolioService = Depends(get_portfolio_service)):
    profile, rec = _profile_and_recommendation(service, user["user_id"])
    amount = profile.get("available_balance") or 0.0
    return risk.monte_carlo_var(rec, amount)


@router.get("/investment-plan")
def get_investment_plan(user=Depends(get_effective_user),
                        service: PortfolioService = Depends(get_portfolio_service)):
    profile, rec = _profile_and_recommendation(service, user["user_id"])
    amount = profile.get("available_balance") or 0.0
    if amount <= 0:
        raise HTTPException(status_code=400,
                            detail="Set an available balance in your profile first")
    return planner.build_plan(rec, amount, profile["risk_appetite"])


@router.get("/advisory")
def get_advisory(user=Depends(get_effective_user),
                 db: DatabaseManager = Depends(get_db)):
    return nlp_engine.portfolio_advisory(user["user_id"], db)


# ── Holdings, trades & their analytics ───────────────────────────────────────

@router.get("/ticker-search")
def ticker_search(q: str, user=Depends(get_current_user)):
    return search_tickers(q)


@router.get("/holdings")
def list_holdings(user=Depends(get_effective_user),
                  service: HoldingsService = Depends(get_holdings_service)):
    return service.list_holdings(user["user_id"])


@router.post("/holdings")
def add_holding(req: HoldingRequest, user=Depends(get_current_user),
                service: HoldingsService = Depends(get_holdings_service)):
    try:
        return service.upsert_holding(user["user_id"], req.ticker,
                                      req.quantity, req.avg_buy_price, req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/holdings/{ticker}")
def update_holding(ticker: str, req: HoldingUpdateRequest,
                   user=Depends(get_current_user),
                   service: HoldingsService = Depends(get_holdings_service)):
    try:
        holding = service.update_holding(user["user_id"], ticker,
                                         req.quantity, req.avg_buy_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    return holding


@router.delete("/holdings/{ticker}")
def delete_holding(ticker: str, user=Depends(get_current_user),
                   service: HoldingsService = Depends(get_holdings_service)):
    if not service.delete_holding(user["user_id"], ticker):
        raise HTTPException(status_code=404, detail="Holding not found")
    return {"success": True}


@router.get("/trades")
def list_trades(limit: int = 100, user=Depends(get_effective_user),
                service: HoldingsService = Depends(get_holdings_service)):
    return service.list_trades(user["user_id"], limit)


@router.post("/trades")
def record_trade(req: TradeRequest, user=Depends(get_current_user),
                 service: HoldingsService = Depends(get_holdings_service)):
    try:
        return service.record_trade(user["user_id"], req.ticker, req.action,
                                    req.price, req.quantity, req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/holdings/prices/refresh")
def refresh_holding_prices(user=Depends(get_current_user),
                           service: HoldingsService = Depends(get_holdings_service)):
    return service.refresh_prices(user["user_id"])


@router.get("/holdings/prices/{ticker}")
def holding_price_history(ticker: str, days: int = None,
                          user=Depends(get_current_user),
                          db: DatabaseManager = Depends(get_db)):
    return db.get_price_history(ticker.upper(), days)


@router.get("/holdings/analytics")
def holdings_analytics(user=Depends(get_effective_user),
                       db: DatabaseManager = Depends(get_db)):
    return holdings_engine.run_holdings_analytics(user["user_id"], db)


# ── Holdings-based optimization (real portfolio, stored prices) ──────────────

@router.get("/holdings/optimizer")
def holdings_optimizer_view(user=Depends(get_effective_user),
                            db: DatabaseManager = Depends(get_db)):
    return holdings_optimizer.optimize_holdings(user["user_id"], db)


@router.get("/holdings/plan")
def holdings_plan(amount: float, user=Depends(get_effective_user),
                  db: DatabaseManager = Depends(get_db)):
    if amount <= 0:
        raise HTTPException(status_code=400,
                            detail="Amount must be greater than zero")
    return holdings_optimizer.build_plan(user["user_id"], db, amount)
