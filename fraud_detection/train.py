"""
Trains Isolation Forest, Local Outlier Factor, and XGBoost on the labeled
fraud dataset, evaluates each on a held-out split, and saves whichever
model scores best on F1 for use by fraud_detection/detector.py at runtime.
"""

import csv
import json
import os
import time

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, precision_score, recall_score
from xgboost import XGBClassifier

import config
from utils.logger import logger
from fraud_detection import dataset
from fraud_detection.features import build_feature_vector

MODEL_PATH = config.FRAUD_MODEL_PATH
META_PATH = config.FRAUD_MODEL_META_PATH


def load_dataset(path: str = None):
    """Load the labeled CSV into (X, y) arrays, generating it if missing."""
    path = path or config.FRAUD_DATASET_PATH
    if not os.path.exists(path):
        logger.info(f"No fraud dataset found at {path}, generating synthetic one")
        dataset.generate_synthetic_dataset(path)

    X, y = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            X.append(build_feature_vector(
                amount=float(row["amount"]),
                txn_type=row["txn_type"],
                channel=row["channel"],
                hour=int(row["hour"]),
                txn_count_last_hour=int(row["txn_count_last_hour"]),
                avg_historical_amount=float(row["avg_historical_amount"]),
            ))
            y.append(int(row["is_fraud"]))

    return np.array(X), np.array(y)


def _anomaly_scores(model, X):
    """Higher = more anomalous, for both IsolationForest and LOF (novelty=True)."""
    if hasattr(model, "decision_function"):
        return -model.decision_function(X)
    return -model.score_samples(X)


def train_and_select_best(dataset_path: str = None):
    X, y = load_dataset(dataset_path)
    contamination = max(0.01, min(0.5, y.mean()))

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )

    candidates = {}

    iso = IsolationForest(n_estimators=100, contamination=contamination,
                          random_state=42)
    iso.fit(X_train)
    iso_preds = (iso.predict(X_test) == -1).astype(int)
    candidates["isolation_forest"] = (iso, iso_preds)

    n_neighbors = max(1, min(20, len(X_train) - 1))
    lof = LocalOutlierFactor(n_neighbors=n_neighbors, novelty=True,
                             contamination=contamination)
    lof.fit(X_train)
    lof_preds = (lof.predict(X_test) == -1).astype(int)
    candidates["local_outlier_factor"] = (lof, lof_preds)

    xgb = XGBClassifier(n_estimators=100, max_depth=4, eval_metric="logloss",
                        random_state=42)
    xgb.fit(X_train, y_train)
    xgb_preds = xgb.predict(X_test)
    candidates["xgboost"] = (xgb, xgb_preds)

    results = {}
    for name, (model, preds) in candidates.items():
        results[name] = {
            "f1": round(float(f1_score(y_test, preds, zero_division=0)), 4),
            "precision": round(float(precision_score(y_test, preds, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, preds, zero_division=0)), 4),
        }

    best_name = max(results, key=lambda n: results[n]["f1"])
    best_model = candidates[best_name][0]

    meta = {
        "model_name": best_name,
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_samples": len(X),
        "results": results,
        **results[best_name],
    }

    if best_name in ("isolation_forest", "local_outlier_factor"):
        scores = _anomaly_scores(best_model, X)
        meta["score_min"] = float(scores.min())
        meta["score_max"] = float(scores.max())

    os.makedirs(config.FRAUD_MODEL_DIR, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    logger.success(
        f"Fraud model trained: {best_name} won with F1={results[best_name]['f1']} "
        f"-> saved to {MODEL_PATH}"
    )
    return results, best_name
