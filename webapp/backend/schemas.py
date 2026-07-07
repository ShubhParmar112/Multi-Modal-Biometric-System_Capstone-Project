"""Pydantic request/response models for the SmartBank API."""

from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str
    pin: str


class FaceLoginRequest(BaseModel):
    image: str  # data-URL or bare base64 JPEG/PNG captured from the webcam


class ChangePinRequest(BaseModel):
    old_pin: str
    new_pin: str


class UpdateEmailRequest(BaseModel):
    email: str


class BeneficiaryRequest(BaseModel):
    name: str
    account_number: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str


class AccountResponse(BaseModel):
    account_id: str
    account_number: str
    account_type: str
    balance: float
    currency: str
    status: str


class DepositRequest(BaseModel):
    amount: float


class WithdrawRequest(BaseModel):
    amount: float
    category: str = "Other"


class TransferRequest(BaseModel):
    to_account_number: str
    amount: float
    category: str = "Other"


class TransactionActionResponse(BaseModel):
    success: bool
    message: str
    balance: Optional[float] = None


class CategoryRequest(BaseModel):
    name: str


class FraudToggleRequest(BaseModel):
    enabled: bool


class InvestmentProfileRequest(BaseModel):
    risk_appetite: str
    investment_horizon_years: int
    monthly_savings: float
    available_balance: float
