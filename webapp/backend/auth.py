"""
Web app authentication.
Two login paths, both issuing the same JWT:
  - user_id + PIN (reuses DatabaseManager.verify_pin)
  - Face ID: a webcam frame is matched against the enrolled face
    encodings with the same InsightFace pipeline the ATM uses.
"""

import base64
import threading
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

import config
from database.db_manager import DatabaseManager
from utils.logger import logger
from webapp.backend.schemas import FaceLoginRequest, LoginRequest, TokenResponse

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
        db.log_auth_event(req.user_id or "UNKNOWN", "web_login", "failure",
                          "Invalid user ID or PIN")
        raise HTTPException(status_code=401, detail="Invalid user ID or PIN")

    db.log_auth_event(req.user_id, "web_login", "success", "PIN login")
    db.update_last_login(req.user_id)
    token = create_access_token(req.user_id)
    return TokenResponse(access_token=token, user_id=req.user_id, name=user["name"])


@router.post("/face-login", response_model=TokenResponse)
def face_login(req: FaceLoginRequest, db: DatabaseManager = Depends(get_db)):
    """Identify the user from a single webcam frame and issue a JWT."""
    import cv2
    import numpy as np

    # Accept both "data:image/jpeg;base64,xxxx" and bare base64.
    payload = req.image.split(",", 1)[-1]
    try:
        buf = np.frombuffer(base64.b64decode(payload), dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        frame = None
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
