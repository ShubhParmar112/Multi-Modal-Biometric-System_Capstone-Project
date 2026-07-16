"""Account endpoints - thin wrapper over DatabaseManager."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database.db_manager import DatabaseManager
from webapp.backend.auth import get_db, get_effective_user
from webapp.backend.schemas import AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _mask(number: str) -> str:
    number = str(number or "")
    if len(number) < 8:
        return "•••• •••• •••• ••••"
    return f"{number[:4]} •••• •••• {number[-4:]}"


def _next_due_date() -> str:
    """Credit card bill due: the 5th of next month."""
    now = datetime.now()
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(year, month, 5).strftime("%d %b")


@router.get("/me", response_model=AccountResponse)
def get_my_account(user=Depends(get_effective_user),
                   db: DatabaseManager = Depends(get_db)):
    accounts = db.get_accounts_by_user(user["user_id"])
    if not accounts:
        raise HTTPException(status_code=404, detail="No account found for this user")
    account = dict(accounts[0])

    cards = []
    for card in db.get_cards_by_account(account["account_id"]):
        is_credit = card.get("card_type") == "credit"
        cards.append({
            "card_type": card.get("card_type") or "debit",
            "number_masked": _mask(card.get("card_number")),
            "expiry": card.get("expiry_date"),
            "status": card.get("card_status"),
            "credit_limit": card.get("credit_limit") if is_credit else None,
            "outstanding": card.get("outstanding") if is_credit else None,
            "due_date": _next_due_date() if is_credit else None,
        })
    # Stable order for the UI: debit, credit.
    cards.sort(key=lambda c: c["card_type"])
    account["cards"] = cards
    return account
