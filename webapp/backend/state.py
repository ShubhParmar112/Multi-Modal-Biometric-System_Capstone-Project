"""
Small shared process-wide state for the web app — currently just the
fraud-blocking toggle, mirroring the single-instance toggle the Tkinter
app used in Phase 4 (one setting for the whole running app, not per-user).
"""

import config

app_state = {"block_high_risk": config.FRAUD_BLOCK_HIGH_RISK}
