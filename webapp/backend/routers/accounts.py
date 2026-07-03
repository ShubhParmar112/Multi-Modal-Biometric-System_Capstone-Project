"""Account endpoints - thin wrapper over DatabaseManager."""

from fastapi import APIRouter, Depends, HTTPException

from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/me", response_model=AccountResponse)
def get_my_account(user=Depends(get_current_user),
                   db: DatabaseManager = Depends(get_db)):
    accounts = db.get_accounts_by_user(user["user_id"])
    if not accounts:
        raise HTTPException(status_code=404, detail="No account found for this user")
    return accounts[0]
