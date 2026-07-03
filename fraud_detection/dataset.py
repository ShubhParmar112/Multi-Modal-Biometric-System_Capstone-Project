"""
Synthetic fraud-detection training data (temporary).

Generates a labeled CSV at config.FRAUD_DATASET_PATH with columns:

    amount, txn_type, channel, hour, txn_count_last_hour,
    avg_historical_amount, is_fraud

This is a stand-in until a real labeled dataset is available — drop a
replacement CSV with the same columns at the same path and re-run
`python main.py --train-fraud-model`; no code changes are needed.
"""

import csv
import os
import random

import config

TXN_TYPES = ["deposit", "withdraw", "transfer_out", "transfer_in"]
CHANNELS = ["atm", "online", "branch"]

COLUMNS = [
    "amount", "txn_type", "channel", "hour",
    "txn_count_last_hour", "avg_historical_amount", "is_fraud"
]


def _normal_row(rng: random.Random) -> dict:
    avg_historical_amount = round(rng.uniform(500, 5000), 2)
    amount = round(max(10.0, rng.gauss(avg_historical_amount, avg_historical_amount * 0.25)), 2)
    return {
        "amount": amount,
        "txn_type": rng.choice(["deposit", "withdraw", "transfer_out", "transfer_in"]),
        "channel": rng.choices(CHANNELS, weights=[0.7, 0.2, 0.1])[0],
        "hour": rng.choice(range(7, 22)),
        "txn_count_last_hour": rng.choice([0, 0, 1, 1, 2]),
        "avg_historical_amount": avg_historical_amount,
        "is_fraud": 0,
    }


def _fraud_row(rng: random.Random) -> dict:
    avg_historical_amount = round(rng.uniform(500, 3000), 2)
    amount = round(rng.uniform(40000, 200000), 2)
    return {
        "amount": amount,
        "txn_type": rng.choices(
            ["withdraw", "transfer_out", "deposit"], weights=[0.5, 0.4, 0.1]
        )[0],
        "channel": rng.choices(CHANNELS, weights=[0.4, 0.5, 0.1])[0],
        "hour": rng.choice(list(range(0, 5)) + list(range(22, 24))),
        "txn_count_last_hour": rng.randint(5, 15),
        "avg_historical_amount": avg_historical_amount,
        "is_fraud": 1,
    }


def generate_synthetic_dataset(path: str = None, n_rows: int = 100,
                               fraud_ratio: float = 0.15, seed: int = 42) -> str:
    """Generate a synthetic labeled transaction dataset CSV."""
    path = path or config.FRAUD_DATASET_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)

    rng = random.Random(seed)
    n_fraud = max(1, round(n_rows * fraud_ratio))
    n_normal = n_rows - n_fraud

    rows = [_normal_row(rng) for _ in range(n_normal)] + \
           [_fraud_row(rng) for _ in range(n_fraud)]
    rng.shuffle(rows)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return path
