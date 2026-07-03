"""
SmartBank Web App API - FastAPI backend.
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from webapp.backend import auth
from webapp.backend.routers import accounts, transactions, analytics, fraud, portfolio, advisor

app = FastAPI(title="SmartBank API")

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


@app.get("/api/health")
def health():
    return {"status": "ok"}
