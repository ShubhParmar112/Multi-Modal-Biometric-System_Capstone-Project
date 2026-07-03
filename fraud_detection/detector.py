"""
Fraud Detector - Loads the model selected by fraud_detection/train.py
(whichever of Isolation Forest / Local Outlier Factor / XGBoost scored
best on F1) and scores live transactions with it. Falls back to a simple
rule-based score if no trained model is available yet.
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

import joblib

import config
from utils.logger import logger
from database.db_manager import DatabaseManager
from fraud_detection.features import build_feature_vector


class FraudDetector:
    """Scores transactions for fraud risk using the trained model on disk."""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()
        self.model = None
        self.meta = None
        self._load_model()

    def _load_model(self):
        if not (os.path.exists(config.FRAUD_MODEL_PATH) and
                os.path.exists(config.FRAUD_MODEL_META_PATH)):
            logger.warning(
                "No trained fraud model found. Run "
                "'python main.py --train-fraud-model' to train one. "
                "Falling back to rule-based scoring."
            )
            return

        try:
            self.model = joblib.load(config.FRAUD_MODEL_PATH)
            with open(config.FRAUD_MODEL_META_PATH, encoding="utf-8") as f:
                self.meta = json.load(f)
            logger.success(
                f"Fraud model loaded: {self.meta['model_name']} "
                f"(F1={self.meta.get('f1')})"
            )
        except Exception as e:
            logger.error(f"Failed to load fraud model: {e}")
            self.model = None
            self.meta = None

    def _account_context(self, account_id: str) -> Tuple[int, float]:
        """Compute txn_count_last_hour and avg_historical_amount for an account."""
        history = self.db.get_transactions(account_id, limit=500)
        if not history:
            return 0, 0.0

        avg_amount = sum(t["amount"] for t in history) / len(history)

        cutoff = datetime.now() - timedelta(hours=1)
        recent_count = 0
        for t in history:
            try:
                ts = datetime.strptime(t["timestamp"], "%Y-%m-%d %H:%M:%S")
                if ts >= cutoff:
                    recent_count += 1
            except (ValueError, TypeError):
                continue

        return recent_count, avg_amount

    def score_transaction(self, account_id: str, txn_type: str, amount: float,
                          channel: str = "atm") -> Tuple[float, str, str]:
        """Returns (risk_score 0-1, risk_category, model_used)."""
        txn_count_last_hour, avg_historical_amount = self._account_context(account_id)

        if self.model is None:
            return self._rule_based_score(amount, txn_count_last_hour,
                                          avg_historical_amount)

        features = [build_feature_vector(
            amount, txn_type, channel, datetime.now().hour,
            txn_count_last_hour, avg_historical_amount
        )]

        model_name = self.meta["model_name"]
        try:
            if model_name == "xgboost":
                risk_score = float(self.model.predict_proba(features)[0][1])
            else:
                if hasattr(self.model, "decision_function"):
                    raw_score = -self.model.decision_function(features)[0]
                else:
                    raw_score = -self.model.score_samples(features)[0]
                score_min = self.meta["score_min"]
                score_max = self.meta["score_max"]
                span = score_max - score_min
                risk_score = (raw_score - score_min) / span if span > 0 else 0.0
                risk_score = max(0.0, min(1.0, risk_score))
        except Exception as e:
            logger.error(f"Fraud scoring failed, falling back to rules: {e}")
            return self._rule_based_score(amount, txn_count_last_hour,
                                          avg_historical_amount)

        risk_score = round(risk_score, 4)
        return risk_score, self._categorize(risk_score), model_name

    def _rule_based_score(self, amount: float, txn_count_last_hour: int,
                          avg_historical_amount: float) -> Tuple[float, str, str]:
        score = 0.0
        if amount > config.FRAUD_LARGE_AMOUNT_THRESHOLD:
            score += 0.5
        if txn_count_last_hour >= config.FRAUD_FREQUENCY_THRESHOLD:
            score += 0.4
        if avg_historical_amount > 0 and amount > 3 * avg_historical_amount:
            score += 0.3
        score = round(min(score, 1.0), 4)
        return score, self._categorize(score), "rule_based"

    @staticmethod
    def _categorize(score: float) -> str:
        if score >= config.FRAUD_HIGH_RISK_THRESHOLD:
            return "high"
        if score >= config.FRAUD_MEDIUM_RISK_THRESHOLD:
            return "medium"
        return "low"
