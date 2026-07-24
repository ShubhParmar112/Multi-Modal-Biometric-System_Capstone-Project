"""
Risk Engine - Adaptive ("risk-based") authentication for the web login.

The "bouncer": instead of asking every session for the same factors, this
scores the *situation* of a login attempt and decides how much proof of
identity to demand. Low risk waves the regular through on a PIN; higher risk
demands a Face second factor, and the highest risk demands a face match that
clears a stricter confidence bar.

Design notes
------------
- Scoring is transparent weighted rules, not ML, on purpose: a bouncer that
  must *tell the user why* needs a score it can attribute to named reasons.
  Each firing signal adds a configured weight and a human-readable reason.
- Signals available differ by surface. A browser login gives device, network
  and timing; a fixed ATM does not. This engine targets the web login.
- "Location" is derived from the client IP's subnet (offline-friendly).
  True city/country geolocation + impossible-travel is a phase-2 drop-in:
  replace `location_key()` with a GeoIP lookup and the rest is unchanged.

Mirrors the shape of fraud_detection/detector.py (weighted signals ->
0..1 score -> band) so the two risk surfaces read consistently.
"""

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import config
from database.db_manager import DatabaseManager


# Factor identifiers the login flow understands.
FACTOR_PIN = "pin"
FACTOR_FACE = "face"


@dataclass
class RiskAssessment:
    """The bouncer's verdict for one login attempt."""
    score: float
    band: str                                   # "low" | "medium" | "high"
    required_factors: List[str]
    reasons: List[str] = field(default_factory=list)
    location_key: Optional[str] = None
    min_face_confidence: float = config.MIN_FACE_CONFIDENCE

    @property
    def requires_face(self) -> bool:
        return FACTOR_FACE in self.required_factors

    def reasons_text(self) -> str:
        return "; ".join(self.reasons)


def location_key(ip_address: Optional[str]) -> Optional[str]:
    """
    Collapse an IP into a coarse, stable location token.

    - Loopback / private / link-local addresses -> "local-network" (a home
      router or the dev machine — treated as one familiar place).
    - Public IPv4 -> the /24 subnet ("203.0.113.0/24"), so a user's ISP-
      assigned address changing in its last octet still reads as the same
      place.
    - Public IPv6 -> the /48 prefix.

    Returns None when the address can't be parsed, which the caller treats as
    "unknown" — we don't penalise a signal we couldn't measure.
    """
    if not ip_address:
        return None
    try:
        ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return None
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return "local-network"
    if ip.version == 4:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    return str(ipaddress.ip_network(f"{ip}/48", strict=False))


class RiskEngine:
    """Scores a login attempt and picks the factors it must satisfy."""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def assess_session(self, user: dict, device_hash: Optional[str],
                       ip_address: Optional[str],
                       now: Optional[datetime] = None) -> RiskAssessment:
        """
        Evaluate one login attempt.

        Args:
            user: the DB user record (already PIN-authenticated).
            device_hash: stable per-browser id, or None if not supplied.
            ip_address: client IP as seen by the server.
            now: injectable clock for testing.

        Returns:
            RiskAssessment with score, band, required factors and reasons.
        """
        now = now or datetime.now()
        user_id = user["user_id"]
        loc_key = location_key(ip_address)

        score = 0.0
        reasons: List[str] = []

        # --- Signal: unrecognised device ---------------------------------
        device = self.db.get_known_device(user_id, device_hash) if device_hash else None
        if not device or device["trust_count"] < config.RISK_DEVICE_TRUST_AFTER:
            score += config.RISK_W_NEW_DEVICE
            reasons.append("New device")

        # --- Signal: unseen network / location ---------------------------
        if loc_key is not None and not self.db.has_seen_location(user_id, loc_key):
            score += config.RISK_W_NEW_LOCATION
            reasons.append("Login from a new network")

        # --- Signal: recent failed PIN attempts --------------------------
        failed = self.db.count_recent_failed_logins(
            user_id, config.RISK_FAILED_ATTEMPTS_WINDOW_MIN)
        if failed >= config.RISK_FAILED_ATTEMPTS_TRIGGER:
            score += config.RISK_W_FAILED_ATTEMPTS
            reasons.append(f"{failed} recent failed attempts")

        # --- Signal: odd hour (quiet overnight window) -------------------
        if config.RISK_ODD_HOUR_START <= now.hour < config.RISK_ODD_HOUR_END:
            score += config.RISK_W_ODD_HOUR
            reasons.append("Unusual sign-in hour")

        # --- Signal: first login / dormant account -----------------------
        last_login = self._parse_ts(user.get("last_login"))
        if last_login is None:
            score += config.RISK_W_FIRST_LOGIN
            reasons.append("First sign-in on record")
        elif (now - last_login).days >= config.RISK_DORMANT_DAYS:
            score += config.RISK_W_DORMANT
            reasons.append("Account inactive for a long time")

        # --- Operator / user override: explicit 2FA opt-in is a floor ----
        forced_face = bool(user.get("two_factor_enabled"))
        if forced_face and "Two-factor is on for this account" not in reasons:
            reasons.append("Two-factor is on for this account")

        score = round(min(score, 1.0), 4)
        band = self._band(score)
        if forced_face and band == "low":
            band = "medium"  # honour the opt-in even when the situation is calm

        return self._build(score, band, reasons, loc_key)

    @staticmethod
    def _band(score: float) -> str:
        if score >= config.RISK_HIGH_BAND:
            return "high"
        if score >= config.RISK_MEDIUM_BAND:
            return "medium"
        return "low"

    @staticmethod
    def _build(score: float, band: str, reasons: List[str],
               loc_key: Optional[str]) -> RiskAssessment:
        if band == "high":
            factors = [FACTOR_PIN, FACTOR_FACE]
            min_conf = config.RISK_HIGH_FACE_MIN_CONFIDENCE
        elif band == "medium":
            factors = [FACTOR_PIN, FACTOR_FACE]
            min_conf = config.MIN_FACE_CONFIDENCE
        else:
            factors = [FACTOR_PIN]
            min_conf = config.MIN_FACE_CONFIDENCE
        return RiskAssessment(
            score=score, band=band, required_factors=factors,
            reasons=reasons, location_key=loc_key, min_face_confidence=min_conf,
        )

    @staticmethod
    def _parse_ts(value) -> Optional[datetime]:
        """Parse a stored last_login timestamp (SQLite text) into datetime."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(str(value), fmt)
            except (ValueError, TypeError):
                continue
        return None
