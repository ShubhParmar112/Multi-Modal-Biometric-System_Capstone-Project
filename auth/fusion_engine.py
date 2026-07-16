"""
Fusion Engine - Multi-modal biometric authentication orchestrator.
Coordinates Face Recognition → Fingerprint → PIN verification pipeline.
Implements decision fusion with confidence scoring and audit logging.
"""

from enum import Enum

import config
from utils.logger import logger
from database.db_manager import DatabaseManager
from fingerprint_module.serial_handler import SerialHandler


class AuthStage(Enum):
    """Authentication pipeline stages."""
    IDLE = "idle"
    CARD_INSERTED = "card_inserted"
    FACE_SCAN = "face_scan"
    LIVENESS_CHECK = "liveness_check"
    FINGERPRINT_SCAN = "fingerprint_scan"
    IDENTITY_FUSION = "identity_fusion"
    CARD_VERIFICATION = "card_verification"
    PIN_ENTRY = "pin_entry"
    GRANTED = "access_granted"
    DENIED = "access_denied"
    ERROR = "error"


class FusionEngine:
    """
    Owns the shared authentication subsystems (database, fingerprint
    matcher / ESP32 serial link) used by the ATM UI's auth pipeline.
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.serial_handler = SerialHandler()
        self.fingerprint_matcher = None  # Initialized if SOFTWARE_FINGERPRINT

    def initialize(self) -> bool:
        """
        Initialize all subsystems.

        Returns:
            True if all components initialized successfully
        """
        logger.system_event("Fusion Engine", "Initializing subsystems...")
        success = True

        # Initialize fingerprint subsystem
        if config.SOFTWARE_FINGERPRINT:
            from fingerprint_module.image_matcher import FingerprintImageMatcher
            self.fingerprint_matcher = FingerprintImageMatcher()
            if self.fingerprint_matcher.load_templates():
                logger.success("Software fingerprint matcher ready")
            else:
                logger.warning(
                    "No fingerprint templates loaded. "
                    "Run enrollment first."
                )
        elif not config.SIMULATION_MODE:
            if not self.serial_handler.connect():
                logger.warning(
                    "ESP32 not connected. Fingerprint auth unavailable."
                )
                success = False
        else:
            self.serial_handler.connect()
            logger.info("Running in SIMULATION MODE")

        logger.system_event("Fusion Engine", "Initialization complete")
        return success

    def shutdown(self):
        """Cleanly shut down all subsystems."""
        logger.system_event("Fusion Engine", "Shutting down...")
        self.serial_handler.disconnect()
        logger.system_event("Fusion Engine", "Shutdown complete")
