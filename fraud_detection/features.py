"""
Shared feature engineering for fraud detection — used identically by
training (fraud_detection/train.py) and live scoring (fraud_detection/detector.py)
so the model always sees the same feature layout it was trained on.
"""

CHANNEL_CODE = {"atm": 0, "online": 1, "branch": 2}
WITHDRAWAL_LIKE = {"withdraw", "transfer_out"}

FEATURE_NAMES = [
    "amount", "hour", "is_withdrawal", "channel_code",
    "txn_count_last_hour", "amount_ratio"
]


def build_feature_vector(amount: float, txn_type: str, channel: str, hour: int,
                         txn_count_last_hour: int,
                         avg_historical_amount: float) -> list:
    """Build the numeric feature vector for one transaction."""
    is_withdrawal = 1.0 if txn_type in WITHDRAWAL_LIKE else 0.0
    channel_code = CHANNEL_CODE.get(channel, 0)
    amount_ratio = (
        amount / avg_historical_amount
        if avg_historical_amount and avg_historical_amount > 0
        else 1.0
    )
    return [amount, hour, is_withdrawal, channel_code,
            txn_count_last_hour, amount_ratio]
