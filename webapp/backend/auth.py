"""
Web app authentication.
Two login paths, both issuing the same JWT:
  - user_id + PIN (reuses DatabaseManager.verify_pin)
  - Face ID: a webcam frame is matched against the enrolled face
    encodings with the same InsightFace pipeline the ATM uses.

Optional 2FA (per-user toggle, Settings → Security): when enabled, the PIN
login returns a short-lived challenge token instead of a session JWT, and
the user must pass a Face ID verification (/face-verify) to get the real
token. Face ID login stays single-step — it is already a biometric factor.
"""

import base64
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

import config
from database.db_manager import DatabaseManager
from utils.logger import logger
from webapp.backend.schemas import (
    FaceLoginRequest, FaceVerifyRequest, LoginRequest, TokenResponse,
)

# Lifetime of the intermediate 2FA challenge token.
TWO_FA_CHALLENGE_MINUTES = 5

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# One recognizer for the whole server — the InsightFace model costs several
# hundred MB and seconds to load, so it must not be per-request. Calls are
# serialized with a lock (onnxruntime sessions aren't guaranteed thread-safe).
_face_recognizer = None
_face_lock = threading.Lock()


def get_face_recognizer():
    """Lazily build + load the shared FaceRecognizer (thread-safe)."""
    global _face_recognizer
    with _face_lock:
        if _face_recognizer is None:
            from face_recognition_module.face_recognizer import FaceRecognizer
            recognizer = FaceRecognizer()
            if not recognizer.load_encodings():
                raise RuntimeError("No face encodings found — enroll a user first")
            _face_recognizer = recognizer
        return _face_recognizer


def warm_face_recognizer():
    """Preload encodings + ONNX models so the first Face ID login is fast.
    Called from a background thread at server startup."""
    try:
        import numpy as np
        recognizer = get_face_recognizer()
        with _face_lock:
            # A tiny dummy frame forces the detector models to load now.
            recognizer.recognize_from_frame(
                np.zeros((64, 64, 3), dtype=np.uint8))
        logger.success("Face ID login ready (models warmed)")
    except Exception as e:
        logger.warning(f"Face ID warm-up skipped: {e}")


def get_db() -> DatabaseManager:
    return DatabaseManager()


def create_access_token(user_id: str, scope: str = None,
                        minutes: int = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=minutes or config.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    if scope:
        payload["scope"] = scope
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
        # Intermediate tokens (e.g. the 2FA challenge) never grant API access.
        if payload.get("scope"):
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.get_user(user_id)
    if not user:
        raise credentials_exception
    return user


def get_effective_user(x_view_as: Optional[str] = Header(None, alias="X-View-As"),
                       user: dict = Depends(get_current_user),
                       db: DatabaseManager = Depends(get_db)) -> dict:
    """
    The user whose data a READ endpoint should serve. Normally the caller;
    with an `X-View-As: <user_id>` header it resolves to that user instead,
    but only if that user has granted the caller access
    (account_access_grants, managed in Settings → Beneficiaries).
    Write endpoints must keep using get_current_user.
    """
    if not x_view_as or x_view_as == user["user_id"]:
        return user
    if not db.has_access_grant(x_view_as, user["user_id"]):
        raise HTTPException(status_code=403,
                            detail="No access to this account")
    target = db.get_user(x_view_as)
    if not target:
        raise HTTPException(status_code=403,
                            detail="No access to this account")
    return target


def _decode_frame(image: str):
    """Decode a data-URL or bare-base64 webcam frame into a BGR ndarray."""
    import cv2
    import numpy as np

    # Accept both "data:image/jpeg;base64,xxxx" and bare base64.
    payload = image.split(",", 1)[-1]
    try:
        buf = np.frombuffer(base64.b64decode(payload), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


@router.post("/login")
def login(req: LoginRequest, db: DatabaseManager = Depends(get_db)):
    user = db.get_user(req.user_id)
    if not user or not db.verify_pin(req.user_id, req.pin):
        db.log_auth_event(req.user_id or "UNKNOWN", "web_login", "failure",
                          "Invalid user ID or PIN")
        raise HTTPException(status_code=401, detail="Invalid user ID or PIN")

    # With 2FA on, the PIN alone only earns a short-lived challenge token;
    # the session JWT is issued by /face-verify after the biometric check.
    if user.get("two_factor_enabled"):
        db.log_auth_event(req.user_id, "web_login", "success",
                          "PIN accepted — awaiting 2FA face verification")
        challenge = create_access_token(req.user_id, scope="2fa_pending",
                                        minutes=TWO_FA_CHALLENGE_MINUTES)
        return {"requires_2fa": True, "challenge_token": challenge,
                "user_id": req.user_id, "name": user["name"]}

    db.log_auth_event(req.user_id, "web_login", "success", "PIN login")
    db.update_last_login(req.user_id)
    token = create_access_token(req.user_id)
    return TokenResponse(access_token=token, user_id=req.user_id, name=user["name"])


@router.post("/face-verify", response_model=TokenResponse)
def face_verify(req: FaceVerifyRequest, db: DatabaseManager = Depends(get_db)):
    """Second factor for 2FA logins: verify that the webcam frame matches
    the user who just passed the PIN check, then issue the session JWT."""
    try:
        payload = jwt.decode(req.challenge_token, config.JWT_SECRET,
                             algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401,
                            detail="2FA challenge expired — sign in again")
    if payload.get("scope") != "2fa_pending" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid 2FA challenge")
    expected_user_id = payload["sub"]

    frame = _decode_frame(req.image)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode the image")

    try:
        recognizer = get_face_recognizer()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    with _face_lock:
        user_id, confidence, face_loc = recognizer.recognize_from_frame(frame)

    if face_loc is None:
        raise HTTPException(status_code=401,
                            detail="No face detected — center your face and try again")
    if user_id != expected_user_id:
        db.log_auth_event(expected_user_id, "web_2fa_face", "failure",
                          f"matched={user_id or 'nobody'} confidence={confidence:.3f}")
        raise HTTPException(status_code=401,
                            detail="Face does not match this account")

    user = db.get_user(expected_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Face does not match this account")

    db.log_auth_event(expected_user_id, "web_2fa_face", "success",
                      f"confidence={confidence:.3f}")
    db.update_last_login(expected_user_id)
    token = create_access_token(expected_user_id)
    return TokenResponse(access_token=token, user_id=expected_user_id,
                         name=user["name"])


@router.post("/face-login", response_model=TokenResponse)
def face_login(req: FaceLoginRequest, db: DatabaseManager = Depends(get_db)):
    """Identify the user from a single webcam frame and issue a JWT."""
    frame = _decode_frame(req.image)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode the image")

    try:
        recognizer = get_face_recognizer()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    with _face_lock:
        user_id, confidence, face_loc = recognizer.recognize_from_frame(frame)

    if face_loc is None:
        raise HTTPException(status_code=401,
                            detail="No face detected — center your face and try again")
    if not user_id:
        db.log_auth_event("UNKNOWN", "web_face_login", "failure",
                          f"confidence={confidence:.3f}")
        raise HTTPException(status_code=401, detail="Face not recognized")

    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Face not recognized")

    db.log_auth_event(user_id, "web_face_login", "success",
                      f"confidence={confidence:.3f}")
    db.update_last_login(user_id)
    token = create_access_token(user_id)
    return TokenResponse(access_token=token, user_id=user_id, name=user["name"])
