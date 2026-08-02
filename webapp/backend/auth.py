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
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

import config
from auth.risk_engine import RiskEngine, location_key
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
                        minutes: int = None, extra: dict = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=minutes or config.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    if scope:
        payload["scope"] = scope
    if extra:
        payload.update(extra)
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def _client_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort client IP: honour X-Forwarded-For (first hop) behind a
    proxy, else the direct socket peer."""
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _device_hash(device_id: Optional[str], ip: Optional[str],
                 user_agent: Optional[str]) -> Optional[str]:
    """Derive the stable device fingerprint the risk engine keys on.

    A client-supplied device_id (localStorage UUID) is authoritative. When
    it's missing we fall back to a hash of IP + User-Agent — weaker, but it
    still separates obviously different clients. Returns None only when there
    is nothing at all to fingerprint."""
    basis = device_id or ((ip or "") + "|" + (user_agent or ""))
    basis = basis.strip()
    if not basis or basis == "|":
        return None
    return hashlib.sha256(basis.encode()).hexdigest()[:32]


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


def _count_blinks(frames):
    """Count blinks across a burst and pick the best frame for recognition.

    Returns (blink_count, best_frame). "Best" is the frame with the highest
    eye-aspect-ratio — eyes widest open — because a mid-blink frame is a poor
    input to face matching. Falls back to the first frame if no face was found
    in any of them; the caller's own no-face check then handles it.

    A fresh LivenessDetector per call, deliberately: MediaPipe holds per-
    instance state, and one detector per request costs ~36ms warm while
    removing any need to serialise this behind _face_lock. Only the single
    InsightFace call needs that lock.
    """
    from face_recognition_module.liveness_detector import LivenessDetector

    detector = LivenessDetector()
    detector.reset()

    best_frame, best_ear = frames[0], None
    for frame in frames:
        ear, _closed, _display = detector.check_frame_liveness(frame)
        detector.update_blink_state(ear)
        if ear is not None and (best_ear is None or ear > best_ear):
            best_ear, best_frame = ear, frame

    return detector.blink_count, best_frame


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
def login(req: LoginRequest, request: Request,
          db: DatabaseManager = Depends(get_db)):
    # Lockout FIRST, before the PIN is even checked. A locked account must be
    # refused even when the PIN is correct — otherwise an attacker who walks
    # the 4-digit keyspace is let straight in on the guess that happens to be
    # right, and the limit protects nothing. Reuses the same rolling-window
    # counter the risk engine reads, so there is one definition of "recent
    # failed login" in the system.
    if req.user_id:
        recent_failures = db.count_recent_failed_logins(
            req.user_id, config.LOGIN_LOCKOUT_WINDOW_MIN)
        if recent_failures >= config.MAX_PIN_ATTEMPTS:
            db.log_auth_event(req.user_id, "web_login", "lockout",
                              f"{recent_failures} failures in "
                              f"{config.LOGIN_LOCKOUT_WINDOW_MIN} min")
            raise HTTPException(
                status_code=429,
                detail=(f"Too many failed attempts. Try again in about "
                        f"{config.LOGIN_LOCKOUT_WINDOW_MIN} minutes."),
                headers={"Retry-After": str(config.LOGIN_LOCKOUT_WINDOW_MIN * 60)},
            )

    user = db.get_user(req.user_id)
    if not user or not db.verify_pin(req.user_id, req.pin):
        db.log_auth_event(req.user_id or "UNKNOWN", "web_login", "failure",
                          "Invalid user ID or PIN")
        raise HTTPException(status_code=401, detail="Invalid user ID or PIN")

    # PIN is correct. Now the "bouncer": score the situation and decide how
    # much more proof to demand. (If adaptive auth is off, fall back to the
    # static per-user 2FA toggle.)
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    device_hash = _device_hash(req.device_id, ip, user_agent)

    if config.ADAPTIVE_AUTH_ENABLED:
        assessment = RiskEngine(db).assess_session(user, device_hash, ip)
    else:
        assessment = _legacy_assessment(user)

    if assessment.requires_face:
        # Face is required: the PIN only earns a short-lived challenge token.
        # The session JWT is issued by /face-verify after the biometric check.
        # Carry the risk context in the challenge so face-verify can apply the
        # right strictness and record the device on success.
        db.log_auth_event(
            req.user_id, "web_login", "success",
            f"PIN ok — risk={assessment.band} ({assessment.score}); "
            f"stepping up to Face [{assessment.reasons_text()}]")
        challenge = create_access_token(
            req.user_id, scope="2fa_pending", minutes=TWO_FA_CHALLENGE_MINUTES,
            extra={
                "band": assessment.band,
                "dev": device_hash,
                "loc": assessment.location_key,
                "mfc": assessment.min_face_confidence,
                "rsn": assessment.reasons_text(),
            })
        return {"requires_2fa": True, "challenge_token": challenge,
                "user_id": req.user_id, "name": user["name"],
                "risk_band": assessment.band,
                "reasons": assessment.reasons}

    # Low risk: wave the regular through on the PIN alone. This is a full
    # successful login, so it's the moment we trust the device + record the
    # login context that future "new device / new location" checks read from.
    db.log_auth_event(
        req.user_id, "web_login", "success",
        f"PIN login — risk={assessment.band} ({assessment.score})")
    db.record_login_context(req.user_id, device_hash, ip,
                            assessment.location_key, assessment.score,
                            assessment.band, assessment.reasons_text())
    db.record_device_seen(req.user_id, device_hash)
    db.update_last_login(req.user_id)
    token = create_access_token(req.user_id)
    return TokenResponse(access_token=token, user_id=req.user_id, name=user["name"])


def _legacy_assessment(user: dict):
    """Fallback when ADAPTIVE_AUTH_ENABLED is off: reproduce the old static
    behaviour (Face required iff the user opted into 2FA)."""
    from auth.risk_engine import FACTOR_FACE, FACTOR_PIN, RiskAssessment
    if user.get("two_factor_enabled"):
        return RiskAssessment(score=0.0, band="medium",
                              required_factors=[FACTOR_PIN, FACTOR_FACE],
                              reasons=["Two-factor is on for this account"])
    return RiskAssessment(score=0.0, band="low",
                          required_factors=[FACTOR_PIN])


@router.post("/face-verify", response_model=TokenResponse)
def face_verify(req: FaceVerifyRequest, request: Request,
                db: DatabaseManager = Depends(get_db)):
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

    # Risk context carried from /login. High-risk sessions must clear a
    # stricter face-match confidence than the routine floor.
    band = payload.get("band", "medium")
    device_hash = payload.get("dev")
    loc_key = payload.get("loc")
    min_face_confidence = payload.get("mfc", config.MIN_FACE_CONFIDENCE)
    reasons = payload.get("rsn", "")

    frames = [f for f in (_decode_frame(img) for img in req.images)
              if f is not None]
    if not frames:
        raise HTTPException(status_code=400, detail="Could not decode the images")

    # Liveness BEFORE recognition. A still photograph produces a perfectly
    # constant eye-aspect-ratio and can never blink, so this is what stops a
    # printed or on-screen photo satisfying the step-up. Recognition is also
    # the expensive step — no reason to run it on frames we already know came
    # from a photo.
    blinks, best_frame = _count_blinks(frames)
    if blinks < config.LIVENESS_BLINK_REQUIRED:
        db.log_auth_event(expected_user_id, "web_2fa_face", "failure",
                          f"liveness failed — {blinks} blink(s) across "
                          f"{len(frames)} frames")
        raise HTTPException(
            status_code=401,
            detail="We couldn't tell that was a live person. Look at the "
                   "camera and blink once while it captures.")

    try:
        recognizer = get_face_recognizer()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Only the single best frame goes through recognition, so the lock is held
    # for one inference — exactly as long as before the burst.
    with _face_lock:
        user_id, confidence, face_loc = recognizer.recognize_from_frame(best_frame)

    if face_loc is None:
        raise HTTPException(status_code=401,
                            detail="No face detected — center your face and try again")
    if user_id != expected_user_id:
        db.log_auth_event(expected_user_id, "web_2fa_face", "failure",
                          f"matched={user_id or 'nobody'} confidence={confidence:.3f}")
        raise HTTPException(status_code=401,
                            detail="Face does not match this account")

    # Stricter bar for high-risk sessions: a match that would pass routinely
    # is not enough for the 3 a.m. stranger.
    if confidence < min_face_confidence:
        db.log_auth_event(
            expected_user_id, "web_2fa_face", "failure",
            f"confidence={confidence:.3f} below {band}-risk floor "
            f"{min_face_confidence:.2f}")
        raise HTTPException(
            status_code=401,
            detail="This looks like a higher-risk sign-in, so we need a "
                   "clearer face match. Face the camera in good light and "
                   "try again.")

    user = db.get_user(expected_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Face does not match this account")

    # Full success: record the login context + trust this device now.
    db.log_auth_event(expected_user_id, "web_2fa_face", "success",
                      f"confidence={confidence:.3f} risk={band}")
    db.record_login_context(expected_user_id, device_hash, _client_ip(request),
                            loc_key, None, band, reasons)
    db.record_device_seen(expected_user_id, device_hash)
    db.update_last_login(expected_user_id)
    token = create_access_token(expected_user_id)
    return TokenResponse(access_token=token, user_id=expected_user_id,
                         name=user["name"])


@router.post("/face-login", response_model=TokenResponse)
def face_login(req: FaceLoginRequest, db: DatabaseManager = Depends(get_db)):
    """Identify the user from a burst of webcam frames and issue a JWT.

    This is the only path that hands out a session on a biometric alone — no
    PIN, no challenge — so it applies the same liveness bar as the PIN-gated
    step-up, plus the routine face-confidence floor.
    """
    frames = [f for f in (_decode_frame(img) for img in req.images)
              if f is not None]
    if not frames:
        raise HTTPException(status_code=400, detail="Could not decode the images")

    # Liveness before recognition: a still photograph holds a constant
    # eye-aspect-ratio and can never blink.
    blinks, best_frame = _count_blinks(frames)
    if blinks < config.LIVENESS_BLINK_REQUIRED:
        # user_id None, not "UNKNOWN": auth_logs.user_id has a foreign key to
        # users and foreign_keys is ON, so a literal "UNKNOWN" fails the
        # constraint and log_auth_event swallows the error — the attempt would
        # never be recorded. NULL is permitted by the FK and stores fine, so a
        # spoof attempt against this endpoint is actually auditable.
        db.log_auth_event(None, "web_face_login", "failure",
                          f"liveness failed — {blinks} blink(s) across "
                          f"{len(frames)} frames")
        raise HTTPException(
            status_code=401,
            detail="We couldn't tell that was a live person. Look at the "
                   "camera and blink once while it captures.")

    try:
        recognizer = get_face_recognizer()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    with _face_lock:
        user_id, confidence, face_loc = recognizer.recognize_from_frame(best_frame)

    if face_loc is None:
        raise HTTPException(status_code=401,
                            detail="No face detected — center your face and try again")
    if not user_id:
        db.log_auth_event(None, "web_face_login", "failure",
                          f"unrecognised face, confidence={confidence:.3f}")
        raise HTTPException(status_code=401, detail="Face not recognized")

    # Confidence floor. face-verify has always enforced one; this endpoint
    # never did, even though it grants a session on the face alone — so a
    # marginal match was enough to log in as somebody.
    if confidence < config.MIN_FACE_CONFIDENCE:
        db.log_auth_event(user_id, "web_face_login", "failure",
                          f"confidence={confidence:.3f} below floor "
                          f"{config.MIN_FACE_CONFIDENCE:.2f}")
        raise HTTPException(
            status_code=401,
            detail="Face match wasn't clear enough. Face the camera in good "
                   "light and try again.")

    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Face not recognized")

    db.log_auth_event(user_id, "web_face_login", "success",
                      f"confidence={confidence:.3f}")
    db.update_last_login(user_id)
    token = create_access_token(user_id)
    return TokenResponse(access_token=token, user_id=user_id, name=user["name"])
