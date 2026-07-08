"""
Settings endpoints — backing for the web app's Settings section:
security (PIN + email + 2FA), per-user theme, account activity analysis,
beneficiaries and beneficiary data-access grants.
"""

import re

from fastapi import APIRouter, Depends, HTTPException

from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import (
    AccessGrantRequest, BeneficiaryRequest, ChangePinRequest, ThemeRequest,
    TwoFactorRequest, UpdateEmailRequest,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
VALID_THEMES = {"dark", "light", "system"}


@router.get("/profile")
def get_profile(user=Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user.get("email"),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
        "theme": user.get("theme"),
        "two_factor_enabled": bool(user.get("two_factor_enabled")),
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


@router.post("/two-factor")
def set_two_factor(req: TwoFactorRequest, user=Depends(get_current_user),
                   db: DatabaseManager = Depends(get_db)):
    """Toggle the Face ID second factor for PIN logins."""
    if req.enabled and user.get("face_encoding") is None:
        raise HTTPException(
            status_code=400,
            detail="2FA uses Face ID — enroll your face at the ATM first")
    if not db.set_two_factor(user["user_id"], req.enabled):
        raise HTTPException(status_code=500, detail="Could not update 2FA")
    db.log_auth_event(user["user_id"], "2fa_toggle", "success",
                      "enabled" if req.enabled else "disabled")
    return {"success": True, "two_factor_enabled": req.enabled,
            "message": ("Face ID verification is now required at login"
                        if req.enabled else "2FA turned off — PIN alone signs you in")}


# ── Theme (per-user preference) ──────────────────────────────


@router.post("/theme")
def set_theme(req: ThemeRequest, user=Depends(get_current_user),
              db: DatabaseManager = Depends(get_db)):
    theme = req.theme.strip().lower()
    if theme not in VALID_THEMES:
        raise HTTPException(status_code=400,
                            detail=f"Theme must be one of {sorted(VALID_THEMES)}")
    if not db.update_user_theme(user["user_id"], theme):
        raise HTTPException(status_code=500, detail="Could not save theme")
    return {"success": True, "theme": theme}


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


# ── Beneficiary data access (read-only view grants) ──────────


@router.get("/access-grants")
def list_access_grants(user=Depends(get_current_user),
                       db: DatabaseManager = Depends(get_db)):
    """Grants this user has given (who may view my data)."""
    return db.get_access_grants(user["user_id"])


@router.get("/access-grants/shared-with-me")
def shared_with_me(user=Depends(get_current_user),
                   db: DatabaseManager = Depends(get_db)):
    """Accounts this user may view (for the account switcher)."""
    return db.get_accounts_shared_with(user["user_id"])


@router.post("/access-grants")
def add_access_grant(req: AccessGrantRequest, user=Depends(get_current_user),
                     db: DatabaseManager = Depends(get_db)):
    """Give the holder of a SmartBank account read access to my data
    (holdings, transactions, analytics, portfolio)."""
    account_number = req.account_number.strip()
    if not account_number.isdigit():
        raise HTTPException(status_code=400,
                            detail="A numeric account number is required")
    account = db.get_account_by_number(account_number)
    if not account:
        raise HTTPException(status_code=404,
                            detail="No SmartBank account with that number")
    grantee_id = account["user_id"]
    if grantee_id == user["user_id"]:
        raise HTTPException(status_code=400,
                            detail="You already have access to your own data")
    grantee = db.get_user(grantee_id)
    if not grantee:
        raise HTTPException(status_code=404, detail="That account has no active user")

    if not db.add_access_grant(user["user_id"], grantee_id):
        raise HTTPException(status_code=409, detail="Access already granted")
    db.log_auth_event(user["user_id"], "access_grant", "success",
                      f"read access granted to {grantee_id}")
    return {"success": True,
            "message": f"{grantee['name']} can now view your account data"}


@router.delete("/access-grants/{grant_id}")
def delete_access_grant(grant_id: int, user=Depends(get_current_user),
                        db: DatabaseManager = Depends(get_db)):
    if not db.delete_access_grant(user["user_id"], grant_id):
        raise HTTPException(status_code=404, detail="Grant not found")
    db.log_auth_event(user["user_id"], "access_grant", "success",
                      f"grant {grant_id} revoked")
    return {"success": True}
