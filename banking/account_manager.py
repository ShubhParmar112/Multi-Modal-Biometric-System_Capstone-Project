"""
Banking Core - Account-level business logic (deposit, withdraw, transfer,
balance inquiry, mini statement) built on top of DatabaseManager's CRUD.
"""

from typing import List, Optional, Tuple

import config
from database.db_manager import DatabaseManager
from fraud_detection.detector import FraudDetector
from utils.logger import logger


class BankingService:
    """
    Validates and executes banking operations against a user's primary
    account. One account per user is assumed for now.
    """

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()
        self.fraud_detector = FraudDetector(self.db)
        self.block_high_risk = config.FRAUD_BLOCK_HIGH_RISK

    def set_fraud_blocking(self, enabled: bool):
        """Runtime toggle for whether high-risk transactions are blocked."""
        self.block_high_risk = enabled

    def _primary_account(self, user_id: str) -> Optional[dict]:
        accounts = self.db.get_accounts_by_user(user_id)
        return accounts[0] if accounts else None

    def _score_transaction(self, account_id: str, txn_type: str,
                           amount: float, channel: str = "atm"):
        return self.fraud_detector.score_transaction(account_id, txn_type, amount, channel)

    def _block_transaction(self, account: dict, txn_type: str, amount: float,
                           risk_score: float, risk_category: str,
                           model_used: str) -> Tuple[bool, str, Optional[float]]:
        txn_id = self.db.record_transaction(
            account["account_id"], txn_type, amount, account["balance"],
            status="blocked"
        )
        self.db.log_fraud(txn_id, risk_score, risk_category, model_used,
                          notes="Blocked by fraud engine")
        logger.warning(
            f"Transaction blocked: {txn_type} {amount} on "
            f"{account['account_id']} (risk={risk_category})"
        )
        return (False, f"Transaction blocked — high fraud risk ({risk_score:.2f}).",
                account["balance"])

    def get_balance(self, user_id: str) -> Optional[float]:
        account = self._primary_account(user_id)
        return account["balance"] if account else None

    def deposit(self, user_id: str, amount: float) -> Tuple[bool, str, Optional[float]]:
        if amount <= 0:
            return False, "Deposit amount must be greater than zero.", None

        account = self._primary_account(user_id)
        if not account:
            return False, "No account found for this user.", None

        risk_score, risk_category, model_used = self._score_transaction(
            account["account_id"], "deposit", amount
        )
        if self.block_high_risk and risk_category == "high":
            return self._block_transaction(account, "deposit", amount,
                                           risk_score, risk_category, model_used)

        new_balance = round(account["balance"] + amount, 2)
        self.db.update_account_balance(account["account_id"], new_balance)
        txn_id = self.db.record_transaction(
            account["account_id"], "deposit", amount, new_balance,
            category="Income"
        )
        self.db.log_fraud(txn_id, risk_score, risk_category, model_used)
        logger.success(f"Deposit of {amount} for {user_id}: new balance {new_balance}")
        return True, f"Deposit successful. [Risk: {risk_category}]", new_balance

    def withdraw(self, user_id: str, amount: float,
                category: str = "Other") -> Tuple[bool, str, Optional[float]]:
        if amount <= 0:
            return False, "Withdrawal amount must be greater than zero.", None

        account = self._primary_account(user_id)
        if not account:
            return False, "No account found for this user.", None

        if amount > account["balance"]:
            return False, "Insufficient balance.", account["balance"]

        risk_score, risk_category, model_used = self._score_transaction(
            account["account_id"], "withdraw", amount
        )
        if self.block_high_risk and risk_category == "high":
            return self._block_transaction(account, "withdraw", amount,
                                           risk_score, risk_category, model_used)

        new_balance = round(account["balance"] - amount, 2)
        self.db.update_account_balance(account["account_id"], new_balance)
        txn_id = self.db.record_transaction(
            account["account_id"], "withdraw", amount, new_balance,
            category=category
        )
        self.db.log_fraud(txn_id, risk_score, risk_category, model_used)
        logger.success(f"Withdrawal of {amount} for {user_id}: new balance {new_balance}")
        return True, f"Withdrawal successful. [Risk: {risk_category}]", new_balance

    def transfer(self, user_id: str, to_account_number: str, amount: float,
                category: str = "Other") -> Tuple[bool, str, Optional[float]]:
        if amount <= 0:
            return False, "Transfer amount must be greater than zero.", None

        source = self._primary_account(user_id)
        if not source:
            return False, "No account found for this user.", None

        destination = self.db.get_account_by_number(to_account_number)
        if not destination:
            return False, "Destination account not found.", source["balance"]

        if destination["account_id"] == source["account_id"]:
            return False, "Cannot transfer to your own account.", source["balance"]

        if amount > source["balance"]:
            return False, "Insufficient balance.", source["balance"]

        risk_score, risk_category, model_used = self._score_transaction(
            source["account_id"], "transfer_out", amount
        )
        if self.block_high_risk and risk_category == "high":
            return self._block_transaction(source, "transfer_out", amount,
                                           risk_score, risk_category, model_used)

        # Note: each DatabaseManager call is its own connection/transaction,
        # so this debit+credit pair is not atomic across a crash between them.
        source_new_balance = round(source["balance"] - amount, 2)
        self.db.update_account_balance(source["account_id"], source_new_balance)
        out_txn_id = self.db.record_transaction(
            source["account_id"], "transfer_out", amount, source_new_balance,
            counterparty_account=to_account_number, category=category
        )
        self.db.log_fraud(out_txn_id, risk_score, risk_category, model_used)

        dest_new_balance = round(destination["balance"] + amount, 2)
        self.db.update_account_balance(destination["account_id"], dest_new_balance)
        in_txn_id = self.db.record_transaction(
            destination["account_id"], "transfer_in", amount, dest_new_balance,
            counterparty_account=source["account_number"], category="Income"
        )
        in_risk_score, in_risk_category, in_model_used = self._score_transaction(
            destination["account_id"], "transfer_in", amount
        )
        self.db.log_fraud(in_txn_id, in_risk_score, in_risk_category, in_model_used)

        logger.success(
            f"Transfer of {amount} from {user_id} to {to_account_number} complete"
        )
        return (True, f"Transfer successful. [Risk: {risk_category}]",
                source_new_balance)

    def get_mini_statement(self, user_id: str, limit: int = 10) -> List[dict]:
        account = self._primary_account(user_id)
        if not account:
            return []
        return self.db.get_transactions(account["account_id"], limit)
