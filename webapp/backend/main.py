"""
NoryvX Web App API - FastAPI backend.
Everything except biometric authentication (which lives in the Tkinter
ATM app) — accounts, transactions, analytics, fraud visibility, and
portfolio optimization.

Run from the project root:
    uvicorn webapp.backend.main:app --reload
"""

import os
import sys

# Ensure the project root (three levels up: backend -> webapp -> project root)
# is on sys.path so `import config`, `import database...` etc. resolve,
# regardless of the working directory uvicorn is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from utils.logger import logger
from webapp.backend import auth
from webapp.backend.routers import (
    accounts, transactions, analytics, fraud, portfolio, advisor, settings
)

app = FastAPI(title="NoryvX API")


@app.on_event("startup")
def check_jwt_secret():
    """Warn when the session-signing key was generated rather than supplied.

    This lives here, not in config.py, because the CLI and the Tkinter ATM
    import config too and never issue a JWT — they must not be nagged about
    a secret they do not use."""
    if config.JWT_SECRET_IS_GENERATED:
        logger.warning(
            f"JWT_SECRET is not set — using the generated key cached in "
            f"{os.path.basename(config.JWT_SECRET_FILE)}. Sessions survive "
            f"restarts, but the key differs per machine and is not suitable "
            f"for deployment. Set JWT_SECRET in .env (see .env.example)."
        )


@app.on_event("startup")
def warm_market_caches():
    """Fetch market data in the background so the first Portfolio page
    visit doesn't pay the yfinance download cost."""
    def _warm():
        try:
            from portfolio import market_data, specific_picks
            market_data.get_asset_statistics()
            specific_picks.get_equity_picks()
            specific_picks.get_gold_picks()
            specific_picks.get_mutual_fund_picks()
            specific_picks.get_debt_picks()
            specific_picks.get_fd_picks()
        except Exception as e:
            logger.warning(f"Market cache warm-up failed (will retry on demand): {e}")

    threading.Thread(target=_warm, daemon=True, name="cache-warmup").start()


@app.on_event("startup")
def warm_face_models():
    """Load the InsightFace models in the background so the first
    Face ID login doesn't wait several seconds for model init."""
    threading.Thread(target=auth.warm_face_recognizer,
                     daemon=True, name="face-warmup").start()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Always answer with JSON instead of a dropped connection — the frontend
    can then show a real error message."""
    logger.error(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error. Check the server logs."})

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.WEBAPP_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(fraud.router)
app.include_router(portfolio.router)
app.include_router(advisor.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
