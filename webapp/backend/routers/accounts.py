"""Account endpoints - thin wrapper over DatabaseManager."""

from fastapi import APIRouter, Depends, HTTPException

from database.db_manager import DatabaseManager
from webapp.backend.auth import get_db, get_effective_user
from webapp.backend.schemas import AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/me", response_model=AccountResponse)
def get_my_account(user=Depends(get_effective_user),
                   db: DatabaseManager = Depends(get_db)):
    accounts = db.get_accounts_by_user(user["user_id"])
    if not accounts:
        raise HTTPException(status_code=404, detail="No account found for this user")
    account = dict(accounts[0])

    cards = db.get_cards_by_account(account["account_id"])
    if cards:
        card = cards[0]
        number = str(card.get("card_number") or "")
        if len(number) >= 8:
            account["card_number_masked"] = (
                f"{number[:4]} •••• •••• {number[-4:]}"
            )
        account["card_expiry"] = card.get("expiry_date")
        account["card_status"] = card.get("card_status")
    return account
