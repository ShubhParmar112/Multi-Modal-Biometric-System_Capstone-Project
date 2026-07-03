"""Fraud log visibility + the blocking toggle (Phase 4 feature, web app side)."""

from fastapi import APIRouter, Depends

from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import FraudToggleRequest
from webapp.backend.state import app_state

router = APIRouter(prefix="/api/fraud", tags=["fraud"])


@router.get("/logs")
def get_fraud_logs(limit: int = 20, user=Depends(get_current_user),
                   db: DatabaseManager = Depends(get_db)):
    return db.get_fraud_logs(limit=limit)


@router.get("/blocking-status")
def get_blocking_status(user=Depends(get_current_user)):
    return {"enabled": app_state["block_high_risk"]}


@router.post("/toggle-blocking")
def toggle_blocking(req: FraudToggleRequest, user=Depends(get_current_user)):
    app_state["block_high_risk"] = req.enabled
    return {"enabled": req.enabled}
