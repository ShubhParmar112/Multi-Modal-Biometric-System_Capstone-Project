"""
Configuration file for Multi-Modal Biometric Authentication System.
All system-wide constants and settings are defined here.
"""

import os
import secrets

from dotenv import load_dotenv

# Load .env (if present) before anything else reads os.environ
load_dotenv()

# Force OpenCV to bypass buggy MSMF driver that causes black screens
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"

# ============================================================
# PATH CONFIGURATION
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
ENCODINGS_DIR = os.path.join(BASE_DIR, "encodings")
ENCODINGS_FILE = os.path.join(ENCODINGS_DIR, "face_encodings.pkl")
DATABASE_PATH = os.path.join(BASE_DIR, "database", "users.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ============================================================
# BRANDING
# ============================================================
# One brand across the ATM, banker console, web app and alert e-mails.
BRAND_NAME = "NoryvX"
BRAND_COLOR = "#FC7C02"               # Logo orange
BRANDING_DIR = os.path.join(BASE_DIR, "assets", "branding")
LOGO_MARK_PATH = os.path.join(BRANDING_DIR, "noryvx_mark.png")      # transparent "N" mark
LOGO_MARK_SMALL_PATH = os.path.join(BRANDING_DIR, "noryvx_mark_256.png")
LOGO_ICO_PATH = os.path.join(BRANDING_DIR, "noryvx.ico")            # window icon

# ============================================================
# FACE RECOGNITION SETTINGS
# ============================================================
# InsightFace (ArcFace) uses cosine distance on L2-normalised 512-d embeddings.
# Same-person pairs typically land below 0.40; different people above 0.65.
FACE_RECOGNITION_TOLERANCE = 0.40    # Cosine distance threshold (lower = stricter)
MIN_FACE_CONFIDENCE = 0.6            # Minimum InsightFace det_score to accept
CAMERA_INDEX = 0                     # Webcam index (0 = default)
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
FACE_FRAME_SKIP = 2                  # Process every Nth frame for performance
# Detector input resolution. 640x640 is overkill for a user sitting at an
# ATM — 320x320 runs ~4x faster on CPU with no practical accuracy loss at
# webcam distance. Must be a multiple of 32.
FACE_DET_SIZE = 320

# ============================================================
# LIVENESS DETECTION SETTINGS
# ============================================================
LIVENESS_ENABLED = True
EYE_AR_THRESH = 0.25                  # Eye aspect ratio threshold for blink
EYE_AR_CONSEC_FRAMES = 2             # Consecutive frames for blink detection (lowered to catch fast blinks)
LIVENESS_BLINK_REQUIRED = 1          # Number of blinks required (lowered from 3 to 1 for convenience)
LIVENESS_TIMEOUT = 15                 # Seconds to wait for liveness check (increased slightly just in case)

# ── Web face step-up (/api/auth/face-verify) ─────────────────
# The browser sends a short burst instead of one frame, and the server
# requires a real blink across it before it will even attempt recognition.
#
# The interval matters more than the count. EYE_AR_CONSEC_FRAMES (2) means a
# blink has to span at least two captured frames, and a human blink lasts
# 100-400ms — so at 200ms/frame a fast blink falls between frames and is
# missed. 120ms keeps a 300ms blink spanning ~2.5 frames.
LIVENESS_WEB_FRAMES = 20              # frames the browser captures per attempt
LIVENESS_WEB_FRAME_INTERVAL_MS = 120  # ~2.4s of capture, ~8 fps
# Blink count is shared with the ATM (LIVENESS_BLINK_REQUIRED) so both
# surfaces demand the same proof.

# ============================================================
# FINGERPRINT / SERIAL SETTINGS
# ============================================================
SERIAL_PORT = "COM7"                  # Set your ESP32 port: Windows=COM7, macOS=/dev/cu.usbserial-*, Linux=/dev/ttyUSB0
SERIAL_BAUD_RATE = 115200
SERIAL_TIMEOUT = 2                    # Seconds
FINGERPRINT_TIMEOUT = 15              # Seconds to wait for fingerprint scan

# ============================================================
# SOFTWARE FINGERPRINT MATCHING (when R307S hardware is unavailable)
# Uses OpenCV ORB feature matching on fingerprint images.
# Set SOFTWARE_FINGERPRINT = True to use image-based matching
# instead of the ESP32 + R307S hardware.
# ============================================================
SOFTWARE_FINGERPRINT = False           # True = image-based, False = R307S hardware
FINGERPRINT_DATASET_DIR = os.path.join(BASE_DIR, "fingerprint_dataset")
FINGERPRINT_INBOX_DIR = os.path.join(BASE_DIR, "fingerprint_inbox")
FINGERPRINT_TEMPLATES_FILE = os.path.join(ENCODINGS_DIR, "fingerprint_templates.pkl")
FINGERPRINT_MATCH_THRESHOLD = 35     # Minimum good SIFT matches for positive ID (was 25)
FINGERPRINT_ORB_FEATURES = 3000      # Number of SIFT features to extract (was 1500)

# ============================================================
# AUTHENTICATION SETTINGS
# ============================================================
MAX_PIN_ATTEMPTS = 3
# Look-back for the web-login lockout. The counter is a rolling window over
# auth_logs, so a locked account frees itself this many minutes after its last
# failed attempt — no unlock endpoint and no extra state to store. Matches
# RISK_FAILED_ATTEMPTS_WINDOW_MIN so the risk engine and the lockout reason
# about the same stretch of time.
#
# Note the interaction: RISK_FAILED_ATTEMPTS_TRIGGER (2) is below
# MAX_PIN_ATTEMPTS (3), so failure 2 arms the risk engine's step-up and
# failure 3 locks the account. Lowering MAX_PIN_ATTEMPTS to 2 or less would
# make that step-up unreachable.
LOGIN_LOCKOUT_WINDOW_MIN = 15
PIN_LENGTH = 4
SESSION_TIMEOUT = 30                  # Seconds before session expires
CARD_ENTRY_TIMEOUT = 60                # Seconds to wait for card number entry
AUTH_LOG_ENABLED = True

# ============================================================
# FRAUD DETECTION SETTINGS
# ============================================================
FRAUD_DATASET_DIR = os.path.join(BASE_DIR, "fraud_detection", "data")
FRAUD_DATASET_PATH = os.path.join(FRAUD_DATASET_DIR, "transactions_dataset.csv")
FRAUD_MODEL_DIR = os.path.join(BASE_DIR, "fraud_detection", "models")
FRAUD_MODEL_PATH = os.path.join(FRAUD_MODEL_DIR, "best_model.joblib")
FRAUD_MODEL_META_PATH = os.path.join(FRAUD_MODEL_DIR, "best_model_meta.json")
FRAUD_LARGE_AMOUNT_THRESHOLD = 50000   # used only by the no-model rule-based fallback
FRAUD_FREQUENCY_THRESHOLD = 5          # transactions/hour on one account
FRAUD_MEDIUM_RISK_THRESHOLD = 0.4
FRAUD_HIGH_RISK_THRESHOLD = 0.7
FRAUD_BLOCK_HIGH_RISK = False           # default toggle state — logging only by default

# ============================================================
# ADAPTIVE (RISK-BASED) AUTHENTICATION SETTINGS
# ============================================================
# The "bouncer": a login-time risk score decides how many factors to demand,
# instead of a static per-user 2FA toggle. Low risk -> PIN only; medium ->
# PIN + Face; high -> PIN + Face at a stricter match threshold. Each signal
# below contributes a weight to a 0-1 score; bands map the score to factors.
#
# Transparent, explainable rules (not ML) are deliberate here — a bouncer
# that must *tell the user why* needs a score it can attribute to a reason.
ADAPTIVE_AUTH_ENABLED = True

# Score band cut-offs (score >= threshold selects the band).
RISK_MEDIUM_BAND = 0.30              # >= this -> require Face as a 2nd factor
RISK_HIGH_BAND = 0.60               # >= this -> Face at a stricter threshold

# Per-signal weights (summed, then clamped to 1.0).
RISK_W_NEW_DEVICE = 0.35            # login from a device we've never trusted
RISK_W_NEW_LOCATION = 0.30         # login from an unseen IP subnet / network
RISK_W_FAILED_ATTEMPTS = 0.30      # recent failed PIN logins for this user
RISK_W_ODD_HOUR = 0.15             # login during the quiet overnight window
RISK_W_DORMANT = 0.15              # account unused for a long stretch
RISK_W_FIRST_LOGIN = 0.20          # no prior successful login on record

# Signal parameters.
RISK_FAILED_ATTEMPTS_WINDOW_MIN = 15   # look-back window for failed logins
RISK_FAILED_ATTEMPTS_TRIGGER = 2       # this many failures fires the signal
RISK_ODD_HOUR_START = 1                # 01:00 inclusive
RISK_ODD_HOUR_END = 5                  # 05:00 exclusive (quiet overnight window)
RISK_DORMANT_DAYS = 30                 # no login for this long counts as dormant
RISK_DEVICE_TRUST_AFTER = 1            # successful logins before a device is "known"

# High-risk sessions must clear a higher face-match confidence than the
# routine floor (MIN_FACE_CONFIDENCE) — the "stricter ID check" for the 3 a.m.
# stranger. Full webcam blink-liveness is the phase-2 upgrade for this band.
RISK_HIGH_FACE_MIN_CONFIDENCE = 0.75

# ============================================================
# ANALYTICS SETTINGS
# ============================================================
ANALYTICS_OUTPUT_DIR = os.path.join(BASE_DIR, "analytics", "output")

# ============================================================
# EMAIL NOTIFICATIONS (transaction alerts)
# ============================================================
# Real mail needs SMTP credentials — set these in .env:
#   SMTP_USER=you@gmail.com
#   SMTP_PASSWORD=<16-char Gmail App Password>   (myaccount.google.com/apppasswords)
# When credentials are missing, emails are skipped and logged instead.
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "true").lower() == "true"
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM_NAME = f"{BRAND_NAME} Alerts"

# ============================================================
# WEB APP SETTINGS
# ============================================================
# JWT signing key. Set JWT_SECRET in .env (see .env.example) for a stable,
# deployable key. When it is unset we generate a random one and cache it in a
# gitignored file, so sessions survive restarts and --reload cycles.
#
# There is deliberately NO constant fallback here. A default committed to the
# repository is identical on every machine that runs this code, which lets
# anyone who has seen the source forge a token for any user_id.
JWT_SECRET_FILE = os.path.join(BASE_DIR, ".jwt_secret")


def _generated_jwt_secret() -> str:
    """Read the cached dev secret, creating it on first use."""
    try:
        if os.path.exists(JWT_SECRET_FILE):
            with open(JWT_SECRET_FILE, encoding="utf-8") as fh:
                cached = fh.read().strip()
            if cached:
                return cached
        generated = secrets.token_urlsafe(32)
        with open(JWT_SECRET_FILE, "w", encoding="utf-8") as fh:
            fh.write(generated)
        return generated
    except OSError:
        # Read-only filesystem, or no permission. Stay ephemeral rather than
        # fall back to a shared constant: tokens then die with the process,
        # which costs a re-login but is never forgeable.
        return secrets.token_urlsafe(32)


_jwt_secret_env = os.environ.get("JWT_SECRET")
# True when no JWT_SECRET was supplied, i.e. we are running on a generated
# key. The web app warns about this at startup; nothing else should care.
JWT_SECRET_IS_GENERATED = not _jwt_secret_env
JWT_SECRET = _jwt_secret_env or _generated_jwt_secret()

# ============================================================
# AI ADVISOR (Groq)
# ============================================================
# NOTE: Groq retires models on its own schedule. llama-3.1-70b-versatile went
# first, then llama-3.3-70b-versatile (confirmed absent from the account's model
# list on 2026-08-29, which surfaced as a "model no longer available" reply in
# the advisor). Keep this default on a model Groq currently serves and override
# it with GROQ_MODEL in .env when it lapses again.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_TIMEOUT = 30                     # Seconds before an advisor LLM call is abandoned
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60
WEBAPP_CORS_ORIGINS = ["http://localhost:5173"]

# ============================================================
# PORTFOLIO OPTIMIZATION SETTINGS (Markowitz / MPT)
# ============================================================
# FD/Cash aren't market-traded — fixed assumed rates, near-zero volatility.
PORTFOLIO_TICKERS = {
    "equity": "^NSEI", "debt": "BND", "gold": "GLD", "mutual_funds": "VBINX"
}
PORTFOLIO_FD_RATE = 0.065
PORTFOLIO_FD_VOLATILITY = 0.005
PORTFOLIO_CASH_RATE = 0.035
PORTFOLIO_CASH_VOLATILITY = 0.001
PORTFOLIO_RISK_FREE_RATE = 0.04
PORTFOLIO_VOLATILITY_CAPS = {"low": 0.06, "medium": 0.12, "high": 0.20}
# Max weight any single asset may get from the optimizers (enforced as an
# optimization bound, so the result is always diversified — never 100% in
# one asset). Applies to both the asset-class and holdings optimizers.
PORTFOLIO_MAX_WEIGHT = 0.40
PORTFOLIO_HISTORY_PERIOD = "5y"
PORTFOLIO_CACHE_HOURS = 24
# Persisted market-data cache so restarts don't refetch 5y of history.
PORTFOLIO_CACHE_FILE = os.path.join(BASE_DIR, "portfolio", "market_cache.json")
# Hard deadlines on outbound market-data calls. Without these, a slow or
# unreachable Yahoo Finance endpoint pins FastAPI worker threads forever
# and eventually hangs every endpoint in the app. Fetches run in a
# subprocess (see portfolio/yf_worker.py), so the deadline also covers
# interpreter startup (~4-6 s on Windows).
PORTFOLIO_FETCH_TIMEOUT = 45          # Seconds for the bulk 5y statistics download
PORTFOLIO_PICKS_TIMEOUT = 30          # Seconds for the live ticker quote batch

# ============================================================
# UI SETTINGS
# ============================================================
WINDOW_TITLE = f"{BRAND_NAME} - Biometric Authentication"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
THEME_MODE = "dark"                   # "dark" or "light"
PRIMARY_COLOR = "#00D4AA"             # Teal accent
SECONDARY_COLOR = "#1A1A2E"           # Dark background
ACCENT_COLOR = "#E94560"              # Red for errors/denied
SUCCESS_COLOR = "#00D4AA"             # Green for success
WARNING_COLOR = "#F5A623"             # Orange for warnings
TEXT_COLOR = "#EAEAEA"
CARD_COLOR = "#16213E"
FONT_FAMILY = "Segoe UI"

# ============================================================
# SIMULATION MODE (when hardware is not connected)
# ============================================================
SIMULATION_MODE = False               # Set True to simulate ESP32/fingerprint
SIMULATED_FINGERPRINT_DELAY = 2       # Seconds to simulate scan time

# ============================================================
# Create directories if they don't exist
# ============================================================
for directory in [DATASET_DIR, ENCODINGS_DIR, LOG_DIR,
                  FRAUD_DATASET_DIR, FRAUD_MODEL_DIR, ANALYTICS_OUTPUT_DIR,
                  os.path.dirname(DATABASE_PATH),
                  FINGERPRINT_DATASET_DIR]:
    os.makedirs(directory, exist_ok=True)
