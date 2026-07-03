"""
Web app authentication - separate from the Tkinter app's biometric pipeline.
Simple user_id + PIN login (reuses DatabaseManager.verify_pin), issuing a
JWT for subsequent requests.
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

import config
from database.db_manager import DatabaseManager
from webapp.backend.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def get_db() -> DatabaseManager:
    return DatabaseManager()


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme),
                     db: DatabaseManager = Depends(get_db)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.get_user(user_id)
    if not user:
        raise credentials_exception
    return user


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: DatabaseManager = Depends(get_db)):
    user = db.get_user(req.user_id)
    if not user or not db.verify_pin(req.user_id, req.pin):
        raise HTTPException(status_code=401, detail="Invalid user ID or PIN")

    token = create_access_token(req.user_id)
    return TokenResponse(access_token=token, user_id=req.user_id, name=user["name"])
