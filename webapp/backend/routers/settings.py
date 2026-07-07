"""
Settings endpoints — backing for the web app's Settings section:
security (PIN + email), account activity analysis, and beneficiaries.
Theme switching is purely client-side and needs no backend.
"""

import re

from fastapi import APIRouter, Depends, HTTPException

from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import (
    BeneficiaryRequest, ChangePinRequest, UpdateEmailRequest
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


@router.get("/profile")
def get_profile(user=Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user.get("email"),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
    }


# ── Security ─────────────────────────────────────────────────


@router.post("/change-pin")
def change_pin(req: ChangePinRequest, user=Depends(get_current_user),
               db: DatabaseManager = Depends(get_db)):
    if not db.verify_pin(user["user_id"], req.old_pin):
        db.log_auth_event(user["user_id"], "pin_change", "failure",
                          "Wrong current PIN")
        raise HTTPException(status_code=400, detail="Current PIN is incorrect")
    if len(req.new_pin) != 4 or not req.new_pin.isdigit():
        raise HTTPException(status_code=400, detail="New PIN must be exactly 4 digits")
    if req.new_pin == req.old_pin:
        raise HTTPException(status_code=400,
                            detail="New PIN must differ from the current one")

    if not db.update_pin(user["user_id"], req.new_pin):
        raise HTTPException(status_code=500, detail="Could not update PIN")
    db.log_auth_event(user["user_id"], "pin_change", "success", "Via web settings")
    return {"success": True, "message": "PIN changed successfully"}


@router.post("/email")
def update_email(req: UpdateEmailRequest, user=Depends(get_current_user),
                 db: DatabaseManager = Depends(get_db)):
    email = req.email.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if not db.update_user_email(user["user_id"], email):
        raise HTTPException(status_code=500, detail="Could not update email")
    return {"success": True, "message": f"Transaction alerts will go to {email}"}


# ── Analysis (login & security activity) ─────────────────────


@router.get("/activity")
def get_activity(limit: int = 25, user=Depends(get_current_user),
                 db: DatabaseManager = Depends(get_db)):
    logs = db.get_auth_logs(user["user_id"], limit)
    total = len(logs)
    failures = sum(1 for l in logs if l["result"] != "success")
    face_logins = sum(1 for l in logs if l["event_type"] == "web_face_login"
                      and l["result"] == "success")
    return {
        "summary": {
            "events": total,
            "failures": failures,
            "face_logins": face_logins,
            "last_login": user.get("last_login"),
        },
        "logs": logs,
    }


# ── Beneficiaries ────────────────────────────────────────────


@router.get("/beneficiaries")
def list_beneficiaries(user=Depends(get_current_user),
                       db: DatabaseManager = Depends(get_db)):
    return db.get_beneficiaries(user["user_id"])


@router.post("/beneficiaries")
def add_beneficiary(req: BeneficiaryRequest, user=Depends(get_current_user),
                    db: DatabaseManager = Depends(get_db)):
    name = req.name.strip()
    account_number = req.account_number.strip()
    if not name or not account_number.isdigit():
        raise HTTPException(status_code=400,
                            detail="A name and a numeric account number are required")

    account = db.get_account_by_number(account_number)
    if not account:
        raise HTTPException(status_code=404,
                            detail="No SmartBank account with that number")
    if account["user_id"] == user["user_id"]:
        raise HTTPException(status_code=400,
                            detail="You cannot add your own account as a beneficiary")

    if not db.add_beneficiary(user["user_id"], name, account_number):
        raise HTTPException(status_code=409, detail="Beneficiary already saved")
    return {"success": True, "message": f"{name} added as beneficiary"}


@router.delete("/beneficiaries/{beneficiary_id}")
def delete_beneficiary(beneficiary_id: int, user=Depends(get_current_user),
                       db: DatabaseManager = Depends(get_db)):
    if not db.delete_beneficiary(user["user_id"], beneficiary_id):
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return {"success": True}
