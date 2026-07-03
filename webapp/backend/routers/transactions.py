"""Transaction endpoints - thin wrapper over BankingService (banking/account_manager.py)."""

from fastapi import APIRouter, Depends

from banking.account_manager import BankingService
from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db
from webapp.backend.schemas import (
    DepositRequest, WithdrawRequest, TransferRequest, TransactionActionResponse
)
from webapp.backend.state import app_state

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def get_banking_service(db: DatabaseManager = Depends(get_db)) -> BankingService:
    banking = BankingService(db)
    banking.set_fraud_blocking(app_state["block_high_risk"])
    return banking


@router.post("/deposit", response_model=TransactionActionResponse)
def deposit(req: DepositRequest, user=Depends(get_current_user),
           banking: BankingService = Depends(get_banking_service)):
    success, message, balance = banking.deposit(user["user_id"], req.amount)
    return TransactionActionResponse(success=success, message=message, balance=balance)


@router.post("/withdraw", response_model=TransactionActionResponse)
def withdraw(req: WithdrawRequest, user=Depends(get_current_user),
            banking: BankingService = Depends(get_banking_service)):
    success, message, balance = banking.withdraw(
        user["user_id"], req.amount, category=req.category
    )
    return TransactionActionResponse(success=success, message=message, balance=balance)


@router.post("/transfer", response_model=TransactionActionResponse)
def transfer(req: TransferRequest, user=Depends(get_current_user),
            banking: BankingService = Depends(get_banking_service)):
    success, message, balance = banking.transfer(
        user["user_id"], req.to_account_number, req.amount, category=req.category
    )
    return TransactionActionResponse(success=success, message=message, balance=balance)


@router.get("/mini-statement")
def mini_statement(limit: int = 10, user=Depends(get_current_user),
                   banking: BankingService = Depends(get_banking_service)):
    return banking.get_mini_statement(user["user_id"], limit)
