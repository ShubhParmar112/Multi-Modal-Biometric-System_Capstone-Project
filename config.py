"""
Configuration file for Multi-Modal Biometric Authentication System.
All system-wide constants and settings are defined here.
"""

import os
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
EMAIL_FROM_NAME = "SmartBank Alerts"

# ============================================================
# WEB APP SETTINGS
# ============================================================
# Dev-only default secret — override via the JWT_SECRET env var in production.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")

# ============================================================
# AI ADVISOR (Groq — Llama 3.3 70B)
# ============================================================
# NOTE: llama-3.1-70b-versatile was decommissioned by Groq; 3.3 is the
# current versatile model. Override via the GROQ_MODEL env var if needed.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
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
WINDOW_TITLE = "SecureATM - Biometric Authentication"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 750
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
