"""Pydantic request/response models for the NoryvX API."""

from typing import List, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str
    pin: str
    # Stable per-browser id (localStorage UUID) used by adaptive auth to tell
    # a returning device from a brand-new one. Optional — absent means the
    # session is treated as coming from an unknown device.
    device_id: Optional[str] = None


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


class FaceVerifyRequest(BaseModel):
    challenge_token: str
    # A burst of consecutive webcam frames (data-URL or bare base64), not one
    # snapshot: the server needs to see a blink across them before it will
    # trust the face. A single frame can never contain a blink, so the old
    # one-image shape is deliberately not accepted — it could only ever fail.
    images: List[str]


class TwoFactorRequest(BaseModel):
    enabled: bool


class ThemeRequest(BaseModel):
    theme: str  # "dark" | "light" | "system"


class AccessGrantRequest(BaseModel):
    account_number: str  # the beneficiary's NoryvX account number


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str


class CardSummary(BaseModel):
    card_type: str  # "debit" | "credit"
    number_masked: str  # masked server-side: first 4 + last 4 digits only
    expiry: Optional[str] = None
    status: Optional[str] = None
    credit_limit: Optional[float] = None  # credit cards only
    outstanding: Optional[float] = None
    due_date: Optional[str] = None  # e.g. "05 Aug"


class AccountResponse(BaseModel):
    account_id: str
    account_number: str
    account_type: str
    balance: float
    currency: str
    status: str
    cards: List[CardSummary] = []


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


class HoldingRequest(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    name: Optional[str] = None


class HoldingUpdateRequest(BaseModel):
    quantity: Optional[float] = None
    avg_buy_price: Optional[float] = None


class TradeRequest(BaseModel):
    ticker: str
    action: str  # BUY | SELL
    price: float
    quantity: float
    name: Optional[str] = None
