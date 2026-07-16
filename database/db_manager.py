"""
Database Manager for the Biometric Authentication System.
Handles all CRUD operations for user records using SQLite.
"""

import sqlite3
import hashlib
import os
import pickle
import random
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any

import config
from utils.logger import logger


class DatabaseManager:
    """
    SQLite database manager for storing user credentials.
    Each user record contains: user_id, name, face_encoding,
    fingerprint_id, and hashed PIN.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DATABASE_PATH
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _conn(self, commit: bool = False):
        conn = self._get_connection()
        try:
            yield conn
            if commit:
                conn.commit()
        finally:
            conn.close()

    def _initialize_db(self):
        """Create the users table if it doesn't exist."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id       TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    face_encoding BLOB,
                    fingerprint_id INTEGER UNIQUE,
                    pin_hash      TEXT NOT NULL,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login    TIMESTAMP,
                    is_active     INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       TEXT,
                    event_type    TEXT NOT NULL,
                    result        TEXT NOT NULL,
                    details       TEXT,
                    timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id      TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    account_number  TEXT UNIQUE NOT NULL,
                    account_type    TEXT NOT NULL DEFAULT 'savings',
                    balance         REAL NOT NULL DEFAULT 0.0,
                    currency        TEXT NOT NULL DEFAULT 'INR',
                    status          TEXT NOT NULL DEFAULT 'active',
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    card_number     TEXT PRIMARY KEY,
                    account_id      TEXT NOT NULL,
                    user_id         TEXT NOT NULL,
                    expiry_date     TEXT NOT NULL,
                    cvv_hash        TEXT NOT NULL,
                    card_status     TEXT NOT NULL DEFAULT 'active',
                    issued_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id           TEXT NOT NULL,
                    txn_type             TEXT NOT NULL,
                    amount               REAL NOT NULL,
                    balance_after        REAL NOT NULL,
                    counterparty_account TEXT,
                    channel              TEXT NOT NULL DEFAULT 'atm',
                    status               TEXT NOT NULL DEFAULT 'success',
                    timestamp            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS biometric_profiles (
                    profile_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id           TEXT NOT NULL,
                    modality          TEXT NOT NULL,
                    sample_count      INTEGER DEFAULT 0,
                    last_verified_at  TIMESTAMP,
                    last_confidence   REAL,
                    enrollment_notes  TEXT,
                    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fraud_logs (
                    fraud_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id  INTEGER NOT NULL,
                    risk_score      REAL NOT NULL,
                    risk_category   TEXT NOT NULL,
                    model_used      TEXT,
                    flagged_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed        INTEGER DEFAULT 0,
                    notes           TEXT,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS investment_profiles (
                    profile_id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id                   TEXT UNIQUE NOT NULL,
                    risk_appetite             TEXT NOT NULL,
                    investment_horizon_years  INTEGER,
                    monthly_savings           REAL,
                    available_balance         REAL,
                    updated_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_recommendations (
                    recommendation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id         INTEGER NOT NULL,
                    equity_pct         REAL,
                    debt_pct           REAL,
                    gold_pct           REAL,
                    fd_pct             REAL,
                    cash_pct           REAL,
                    mutual_funds_pct   REAL,
                    expected_return    REAL,
                    expected_risk      REAL,
                    sharpe_ratio       REAL,
                    generated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (profile_id) REFERENCES investment_profiles(profile_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_holdings (
                    holding_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         TEXT NOT NULL,
                    ticker          TEXT NOT NULL,
                    name            TEXT,
                    quantity        REAL NOT NULL,
                    avg_buy_price   REAL NOT NULL,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, ticker),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_trades (
                    trade_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL,
                    ticker      TEXT NOT NULL,
                    action      TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
                    price       REAL NOT NULL,
                    quantity    REAL NOT NULL,
                    traded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_prices (
                    ticker       TEXT NOT NULL,
                    price_date   TEXT NOT NULL,
                    close_price  REAL NOT NULL,
                    PRIMARY KEY (ticker, price_date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    name        TEXT PRIMARY KEY,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS beneficiaries (
                    beneficiary_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         TEXT NOT NULL,
                    name            TEXT NOT NULL,
                    account_number  TEXT NOT NULL,
                    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, account_number),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_access_grants (
                    grant_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    granter_user_id  TEXT NOT NULL,
                    grantee_user_id  TEXT NOT NULL,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (granter_user_id, grantee_user_id),
                    FOREIGN KEY (granter_user_id) REFERENCES users(user_id),
                    FOREIGN KEY (grantee_user_id) REFERENCES users(user_id)
                )
            """)

            # Migration: add `category` to transactions if it doesn't exist yet
            # (CREATE TABLE IF NOT EXISTS won't retroactively add columns).
            existing_cols = {row[1] for row in
                             conn.execute("PRAGMA table_info(transactions)").fetchall()}
            if "category" not in existing_cols:
                conn.execute(
                    "ALTER TABLE transactions ADD COLUMN category TEXT DEFAULT 'Other'"
                )

            # Migration: add `email` to users for transaction notifications.
            user_cols = {row[1] for row in
                         conn.execute("PRAGMA table_info(users)").fetchall()}
            if "email" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT")

            # Migration: per-user web theme preference ("dark"/"light"/"system").
            if "theme" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN theme TEXT")

            # Migration: per-user 2FA toggle for the web login (0 = off).
            if "two_factor_enabled" not in user_cols:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN two_factor_enabled INTEGER DEFAULT 0"
                )

            # Migration: add `volume` to daily_prices for market-movers ranking.
            price_cols = {row[1] for row in
                          conn.execute("PRAGMA table_info(daily_prices)").fetchall()}
            if "volume" not in price_cols:
                conn.execute("ALTER TABLE daily_prices ADD COLUMN volume REAL")

            # Migration: split cards into debit/credit. Cards issued before the
            # split become the account's credit card (with a default limit);
            # every account then gets a fresh debit card issued below.
            card_cols = {row[1] for row in
                         conn.execute("PRAGMA table_info(cards)").fetchall()}
            if "card_type" not in card_cols:
                conn.execute(
                    "ALTER TABLE cards ADD COLUMN card_type TEXT DEFAULT 'debit'"
                )
                conn.execute("UPDATE cards SET card_type = 'credit'")
            if "credit_limit" not in card_cols:
                conn.execute("ALTER TABLE cards ADD COLUMN credit_limit REAL")
                conn.execute(
                    "UPDATE cards SET credit_limit = 100000 "
                    "WHERE card_type = 'credit'"
                )
            if "outstanding" not in card_cols:
                conn.execute(
                    "ALTER TABLE cards ADD COLUMN outstanding REAL DEFAULT 0"
                )

            # Issue a debit card for any account that doesn't have one yet.
            missing_debit = conn.execute("""
                SELECT a.account_id, a.user_id FROM accounts a
                WHERE NOT EXISTS (
                    SELECT 1 FROM cards c
                    WHERE c.account_id = a.account_id
                      AND c.card_type = 'debit'
                )
            """).fetchall()
            if missing_debit:
                now = datetime.now()
                expiry = f"{now.month:02d}/{(now.year + 5) % 100:02d}"
                for acc in missing_debit:
                    conn.execute(
                        """INSERT INTO cards (card_number, account_id, user_id,
                           expiry_date, cvv_hash, card_type)
                           VALUES (?, ?, ?, ?, ?, 'debit')""",
                        (self._unique_card_number(conn), acc["account_id"],
                         acc["user_id"], expiry,
                         self._hash_pin(f"{random.randint(0, 999):03d}"))
                    )
                logger.info(f"Issued {len(missing_debit)} debit card(s)")

            # Seed default categories once.
            count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            if count == 0:
                default_categories = [
                    "Food", "Travel", "Shopping", "Bills", "Healthcare",
                    "Education", "Entertainment", "Investments", "Income", "Other"
                ]
                conn.executemany(
                    "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                    [(c,) for c in default_categories]
                )

            conn.commit()
            logger.system_event("Database initialized", self.db_path)
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
        finally:
            conn.close()

    @staticmethod
    def _hash_pin(pin: str) -> str:
        """Hash a PIN using SHA-256 for secure storage."""
        return hashlib.sha256(pin.encode()).hexdigest()

    def add_user(self, user_id: str, name: str, fingerprint_id: int,
                 pin: str, face_encoding=None, email: str = None) -> bool:
        """
        Add a new user to the database.

        Args:
            user_id: Unique identifier (e.g., "USR001")
            name: Full name of the user
            fingerprint_id: ID stored in the R307S sensor (1-127)
            pin: 4-digit PIN (will be hashed before storage)
            face_encoding: numpy array of face encoding (128-dim)
            email: Address for transaction notifications (optional)

        Returns:
            True if user was added successfully, False otherwise
        """
        try:
            encoding_blob = None
            if face_encoding is not None:
                encoding_blob = pickle.dumps(face_encoding)

            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO users (user_id, name, face_encoding,
                       fingerprint_id, pin_hash, email) VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, name, encoding_blob, fingerprint_id,
                     self._hash_pin(pin), email)
                )
            logger.success(f"User added: {user_id} ({name})")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"User already exists or duplicate fingerprint: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to add user: {e}")
            return False

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a user record by user_id."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ? AND is_active = 1",
                (user_id,)
            ).fetchone()
            if row:
                user = dict(row)
                if user["face_encoding"]:
                    user["face_encoding"] = pickle.loads(user["face_encoding"])
                return user
            return None

    def get_user_by_fingerprint(self, fingerprint_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a user record by fingerprint ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE fingerprint_id = ? AND is_active = 1",
                (fingerprint_id,)
            ).fetchone()
            if row:
                user = dict(row)
                if user["face_encoding"]:
                    user["face_encoding"] = pickle.loads(user["face_encoding"])
                return user
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Retrieve all active users."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, name, fingerprint_id, created_at FROM users WHERE is_active = 1"
            ).fetchall()
            return [dict(row) for row in rows]

    def verify_pin(self, user_id: str, pin: str) -> bool:
        """
        Verify a user's PIN against the stored hash.

        Returns:
            True if PIN matches, False otherwise
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT pin_hash FROM users WHERE user_id = ? AND is_active = 1",
                (user_id,)
            ).fetchone()
            if row and row["pin_hash"] == self._hash_pin(pin):
                return True
            return False

    def update_face_encoding(self, user_id: str, face_encoding) -> bool:
        """Update the face encoding for an existing user."""
        try:
            encoding_blob = pickle.dumps(face_encoding)
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE users SET face_encoding = ? WHERE user_id = ?",
                    (encoding_blob, user_id)
                )
            logger.info(f"Face encoding updated for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update face encoding: {e}")
            return False

    def update_user_email(self, user_id: str, email: str) -> bool:
        """Update the notification email address for a user."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE users SET email = ? WHERE user_id = ?",
                    (email, user_id)
                )
            logger.info(f"Email updated for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update email: {e}")
            return False

    def update_user_theme(self, user_id: str, theme: str) -> bool:
        """Persist the user's web theme preference (dark/light/system)."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE users SET theme = ? WHERE user_id = ?",
                    (theme, user_id)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update theme: {e}")
            return False

    def set_two_factor(self, user_id: str, enabled: bool) -> bool:
        """Turn the web-login 2FA step on or off for a user."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE users SET two_factor_enabled = ? WHERE user_id = ?",
                    (1 if enabled else 0, user_id)
                )
            logger.info(f"2FA {'enabled' if enabled else 'disabled'} for {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update 2FA setting: {e}")
            return False

    def update_pin(self, user_id: str, new_pin: str) -> bool:
        """Replace a user's PIN hash."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE users SET pin_hash = ? WHERE user_id = ?",
                    (self._hash_pin(new_pin), user_id)
                )
            logger.info(f"PIN changed for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update PIN: {e}")
            return False

    def update_last_login(self, user_id: str):
        """Update the last login timestamp for a user."""
        with self._conn(commit=True) as conn:
            conn.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )

    def log_auth_event(self, user_id: str, event_type: str,
                       result: str, details: str = ""):
        """
        Log an authentication event to the audit table.

        Args:
            user_id: User involved (can be "UNKNOWN")
            event_type: face_recognition, fingerprint, pin_entry, session
            result: success, failure, timeout, denied
            details: Additional context
        """
        if not config.AUTH_LOG_ENABLED:
            return
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO auth_logs (user_id, event_type, result, details)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, event_type, result, details)
                )
        except Exception as e:
            logger.error(f"Failed to log auth event: {e}")

    def get_auth_logs(self, user_id: str = None,
                      limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent authentication logs, optionally filtered by user."""
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    """SELECT * FROM auth_logs WHERE user_id = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM auth_logs ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]

    def delete_user(self, user_id: str) -> bool:
        """Soft-delete a user by marking them inactive."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE users SET is_active = 0 WHERE user_id = ?",
                    (user_id,)
                )
            logger.info(f"User deactivated: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

    # ── Accounts ──────────────────────────────────────────────

    def create_account(self, user_id: str, account_type: str = "savings",
                       currency: str = "INR") -> Optional[str]:
        """Create a new account for an existing user."""
        try:
            with self._conn(commit=True) as conn:
                count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
                account_id = f"ACC{count + 1:04d}"
                account_number = "".join(str(random.randint(0, 9)) for _ in range(12))
                conn.execute(
                    """INSERT INTO accounts (account_id, user_id, account_number,
                       account_type, currency) VALUES (?, ?, ?, ?, ?)""",
                    (account_id, user_id, account_number, account_type, currency)
                )
            logger.success(f"Account created: {account_id} for {user_id}")
            return account_id
        except Exception as e:
            logger.error(f"Failed to create account: {e}")
            return None

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an account record by account_id."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_accounts_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve all accounts belonging to a user."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ?", (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_account_by_number(self, account_number: str) -> Optional[Dict[str, Any]]:
        """Retrieve an account record by account_number."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE account_number = ?", (account_number,)
            ).fetchone()
            return dict(row) if row else None

    def update_account_balance(self, account_id: str, new_balance: float) -> bool:
        """Update the stored balance for an account."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "UPDATE accounts SET balance = ? WHERE account_id = ?",
                    (new_balance, account_id)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update account balance: {e}")
            return False

    # ── Cards ─────────────────────────────────────────────────

    @staticmethod
    def _unique_card_number(conn) -> str:
        """Generate a 16-digit Luhn-valid card number unique on `conn`."""
        while True:
            base = "".join(str(random.randint(0, 9)) for _ in range(15))
            digits = [int(d) for d in base] + [0]
            odd_sum = sum(digits[-1::-2])
            even_sum = sum(sum(divmod(d * 2, 10)) for d in digits[-2::-2])
            check_digit = (10 - (odd_sum + even_sum) % 10) % 10
            card_number = base + str(check_digit)

            exists = conn.execute(
                "SELECT 1 FROM cards WHERE card_number = ?", (card_number,)
            ).fetchone()
            if not exists:
                return card_number

    def generate_card_number(self) -> str:
        """Generate a unique 16-digit Luhn-valid card number."""
        with self._conn() as conn:
            return self._unique_card_number(conn)

    def create_card(self, account_id: str, user_id: str, expiry_date: str,
                    cvv: str) -> Optional[str]:
        """Issue a new card linked to an account."""
        card_number = self.generate_card_number()
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO cards (card_number, account_id, user_id,
                       expiry_date, cvv_hash) VALUES (?, ?, ?, ?, ?)""",
                    (card_number, account_id, user_id, expiry_date,
                     self._hash_pin(cvv))
                )
            logger.success(f"Card issued: {card_number} for account {account_id}")
            return card_number
        except Exception as e:
            logger.error(f"Failed to create card: {e}")
            return None

    def get_card(self, card_number: str) -> Optional[Dict[str, Any]]:
        """Retrieve a card record by card_number."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM cards WHERE card_number = ?", (card_number,)
            ).fetchone()
            return dict(row) if row else None

    def get_cards_by_account(self, account_id: str) -> List[Dict[str, Any]]:
        """Retrieve all cards linked to an account."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM cards WHERE account_id = ?", (account_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ── Transactions ──────────────────────────────────────────

    def record_transaction(self, account_id: str, txn_type: str, amount: float,
                           balance_after: float,
                           counterparty_account: str = None,
                           channel: str = "atm",
                           status: str = "success",
                           category: str = "Other") -> Optional[int]:
        """Record a transaction against an account."""
        try:
            with self._conn(commit=True) as conn:
                cursor = conn.execute(
                    """INSERT INTO transactions (account_id, txn_type, amount,
                       balance_after, counterparty_account, channel, status, category)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (account_id, txn_type, amount, balance_after,
                     counterparty_account, channel, status, category)
                )
                txn_id = cursor.lastrowid
            logger.info(f"Transaction recorded: {txn_type} {amount} on {account_id}")
            return txn_id
        except Exception as e:
            logger.error(f"Failed to record transaction: {e}")
            return None

    def get_transactions(self, account_id: str,
                         limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent transactions for an account."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM transactions WHERE account_id = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (account_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_categories(self) -> List[str]:
        """Retrieve all available transaction categories (predefined + custom)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name FROM categories ORDER BY created_at"
            ).fetchall()
            return [row["name"] for row in rows]

    def add_category(self, name: str) -> bool:
        """Add a custom transaction category."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,)
                )
            logger.success(f"Category added: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to add category: {e}")
            return False

    # ── Beneficiaries ─────────────────────────────────────────

    def add_beneficiary(self, user_id: str, name: str,
                        account_number: str) -> bool:
        """Save a beneficiary (transfer recipient) for a user."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO beneficiaries (user_id, name, account_number)
                       VALUES (?, ?, ?)""",
                    (user_id, name, account_number)
                )
            logger.success(f"Beneficiary added for {user_id}: {name}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Beneficiary already exists for {user_id}: {account_number}")
            return False
        except Exception as e:
            logger.error(f"Failed to add beneficiary: {e}")
            return False

    def get_beneficiaries(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve all beneficiaries saved by a user."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM beneficiaries WHERE user_id = ?
                   ORDER BY added_at DESC""",
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_beneficiary(self, user_id: str, beneficiary_id: int) -> bool:
        """Remove a beneficiary (scoped to the owning user)."""
        try:
            with self._conn(commit=True) as conn:
                cursor = conn.execute(
                    "DELETE FROM beneficiaries WHERE beneficiary_id = ? AND user_id = ?",
                    (beneficiary_id, user_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete beneficiary: {e}")
            return False

    # ── Account access grants (beneficiary read access) ──────

    def add_access_grant(self, granter_user_id: str,
                         grantee_user_id: str) -> bool:
        """Grant another user read access to the granter's data."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO account_access_grants
                       (granter_user_id, grantee_user_id) VALUES (?, ?)""",
                    (granter_user_id, grantee_user_id)
                )
            logger.success(
                f"Access grant: {granter_user_id} -> {grantee_user_id}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(
                f"Access grant already exists: {granter_user_id} -> {grantee_user_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to add access grant: {e}")
            return False

    def delete_access_grant(self, granter_user_id: str, grant_id: int) -> bool:
        """Revoke a grant (scoped to the granting user)."""
        try:
            with self._conn(commit=True) as conn:
                cursor = conn.execute(
                    """DELETE FROM account_access_grants
                       WHERE grant_id = ? AND granter_user_id = ?""",
                    (grant_id, granter_user_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete access grant: {e}")
            return False

    def get_access_grants(self, granter_user_id: str) -> List[Dict[str, Any]]:
        """All grants this user has given, with the grantee's name."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT g.grant_id, g.grantee_user_id, g.created_at, u.name
                   FROM account_access_grants g
                   JOIN users u ON u.user_id = g.grantee_user_id
                   WHERE g.granter_user_id = ? ORDER BY g.created_at DESC""",
                (granter_user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_accounts_shared_with(self, grantee_user_id: str) -> List[Dict[str, Any]]:
        """Accounts (granters) this user may view."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT g.granter_user_id AS user_id, u.name, g.created_at
                   FROM account_access_grants g
                   JOIN users u ON u.user_id = g.granter_user_id
                   WHERE g.grantee_user_id = ? AND u.is_active = 1
                   ORDER BY g.created_at DESC""",
                (grantee_user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def has_access_grant(self, granter_user_id: str,
                         grantee_user_id: str) -> bool:
        """True if grantee may view granter's data."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT 1 FROM account_access_grants
                   WHERE granter_user_id = ? AND grantee_user_id = ?""",
                (granter_user_id, grantee_user_id)
            ).fetchone()
            return row is not None

    # ── Fraud logs ────────────────────────────────────────────

    def log_fraud(self, transaction_id: int, risk_score: float,
                 risk_category: str, model_used: str,
                 notes: str = "") -> bool:
        """Log a fraud risk assessment for a transaction."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO fraud_logs (transaction_id, risk_score,
                       risk_category, model_used, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (transaction_id, risk_score, risk_category, model_used, notes)
                )
            logger.warning(
                f"Fraud logged for txn {transaction_id}: "
                f"{risk_category} ({risk_score})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log fraud: {e}")
            return False

    def get_fraud_logs(self, transaction_id: int = None,
                       limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve fraud log entries, optionally filtered by transaction."""
        with self._conn() as conn:
            if transaction_id:
                rows = conn.execute(
                    """SELECT * FROM fraud_logs WHERE transaction_id = ?
                       ORDER BY flagged_at DESC LIMIT ?""",
                    (transaction_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fraud_logs ORDER BY flagged_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]

    # ── Investment profiles & portfolio recommendations ──────

    def upsert_investment_profile(self, user_id: str, risk_appetite: str,
                                  investment_horizon_years: int,
                                  monthly_savings: float,
                                  available_balance: float) -> bool:
        """Create or update a user's investment profile."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO investment_profiles (user_id, risk_appetite,
                       investment_horizon_years, monthly_savings, available_balance)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           risk_appetite = excluded.risk_appetite,
                           investment_horizon_years = excluded.investment_horizon_years,
                           monthly_savings = excluded.monthly_savings,
                           available_balance = excluded.available_balance,
                           updated_at = CURRENT_TIMESTAMP""",
                    (user_id, risk_appetite, investment_horizon_years,
                     monthly_savings, available_balance)
                )
            logger.success(f"Investment profile saved for {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save investment profile: {e}")
            return False

    def get_investment_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a user's investment profile."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM investment_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def save_portfolio_recommendation(
            self, profile_id: int, equity_pct: float = 0.0,
            debt_pct: float = 0.0, gold_pct: float = 0.0,
            fd_pct: float = 0.0, cash_pct: float = 0.0,
            mutual_funds_pct: float = 0.0, expected_return: float = None,
            expected_risk: float = None,
            sharpe_ratio: float = None) -> Optional[int]:
        """Save a generated portfolio allocation for an investment profile."""
        try:
            with self._conn(commit=True) as conn:
                cursor = conn.execute(
                    """INSERT INTO portfolio_recommendations (profile_id,
                       equity_pct, debt_pct, gold_pct, fd_pct, cash_pct,
                       mutual_funds_pct, expected_return, expected_risk,
                       sharpe_ratio)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (profile_id, equity_pct, debt_pct, gold_pct, fd_pct,
                     cash_pct, mutual_funds_pct, expected_return,
                     expected_risk, sharpe_ratio)
                )
                rec_id = cursor.lastrowid
            logger.success(f"Portfolio recommendation saved for profile {profile_id}")
            return rec_id
        except Exception as e:
            logger.error(f"Failed to save portfolio recommendation: {e}")
            return None

    def get_latest_portfolio_recommendation(
            self, profile_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent portfolio recommendation for a profile."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM portfolio_recommendations
                   WHERE profile_id = ? ORDER BY generated_at DESC LIMIT 1""",
                (profile_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Portfolio holdings & trades ──────────────────────────────────────────

    def get_holdings(self, user_id: str) -> List[Dict[str, Any]]:
        """All of a user's holdings, largest cost basis first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM portfolio_holdings WHERE user_id = ?
                   ORDER BY quantity * avg_buy_price DESC""",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_holding(self, user_id: str, ticker: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM portfolio_holdings WHERE user_id = ? AND ticker = ?",
                (user_id, ticker)
            ).fetchone()
            return dict(row) if row else None

    def upsert_holding(self, user_id: str, ticker: str, name: str,
                       quantity: float, avg_buy_price: float) -> bool:
        """Create or overwrite a holding's quantity and average price."""
        try:
            with self._conn(commit=True) as conn:
                conn.execute(
                    """INSERT INTO portfolio_holdings
                       (user_id, ticker, name, quantity, avg_buy_price)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, ticker) DO UPDATE SET
                           name = excluded.name,
                           quantity = excluded.quantity,
                           avg_buy_price = excluded.avg_buy_price,
                           updated_at = CURRENT_TIMESTAMP""",
                    (user_id, ticker, name, quantity, avg_buy_price)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to save holding {ticker}: {e}")
            return False

    def delete_holding(self, user_id: str, ticker: str) -> bool:
        try:
            with self._conn(commit=True) as conn:
                cursor = conn.execute(
                    "DELETE FROM portfolio_holdings WHERE user_id = ? AND ticker = ?",
                    (user_id, ticker)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete holding {ticker}: {e}")
            return False

    def record_portfolio_trade(self, user_id: str, ticker: str, action: str,
                               price: float, quantity: float) -> Optional[int]:
        try:
            with self._conn(commit=True) as conn:
                cursor = conn.execute(
                    """INSERT INTO portfolio_trades
                       (user_id, ticker, action, price, quantity)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, ticker, action, price, quantity)
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to record trade {action} {ticker}: {e}")
            return None

    def get_portfolio_trades(self, user_id: str,
                             limit: int = 100) -> List[Dict[str, Any]]:
        """A user's trade log, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM portfolio_trades WHERE user_id = ?
                   ORDER BY traded_at DESC, trade_id DESC LIMIT ?""",
                (user_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Daily prices ─────────────────────────────────────────────────────────

    def upsert_daily_prices(self, ticker: str, rows: List[tuple]) -> int:
        """Batch upsert of (price_date 'YYYY-MM-DD', close_price) or
        (price_date, close_price, volume) tuples. Volume defaults to NULL
        when a 2-tuple is passed."""
        try:
            with self._conn(commit=True) as conn:
                prepared = []
                for row in rows:
                    if len(row) == 3:
                        d, p, v = row
                    else:
                        (d, p), v = row, None
                    prepared.append((ticker, d, p, v))
                conn.executemany(
                    """INSERT OR REPLACE INTO daily_prices
                       (ticker, price_date, close_price, volume)
                       VALUES (?, ?, ?, ?)""",
                    prepared
                )
                return len(rows)
        except Exception as e:
            logger.error(f"Failed to store prices for {ticker}: {e}")
            return 0

    def get_price_history(self, ticker: str,
                          days: int = None) -> List[Dict[str, Any]]:
        """Stored closes for a ticker, oldest first."""
        with self._conn() as conn:
            sql = """SELECT price_date, close_price FROM daily_prices
                     WHERE ticker = ? ORDER BY price_date DESC"""
            params = [ticker]
            if days:
                sql += " LIMIT ?"
                params.append(days)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_latest_prices(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Newest stored close per ticker: {ticker: {price_date, close_price}}."""
        if not tickers:
            return {}
        with self._conn() as conn:
            placeholders = ",".join("?" for _ in tickers)
            rows = conn.execute(
                f"""SELECT ticker, price_date, close_price FROM (
                        SELECT *, ROW_NUMBER() OVER (
                            PARTITION BY ticker ORDER BY price_date DESC
                        ) AS rn FROM daily_prices WHERE ticker IN ({placeholders})
                    ) WHERE rn = 1""",
                tickers
            ).fetchall()
            return {r["ticker"]: {"price_date": r["price_date"],
                                  "close_price": r["close_price"]} for r in rows}

    # ── Market movers & trade leaders ────────────────────────────────────────

    def get_market_movers(self, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Top gainers/losers by 1-day % change and most-active by latest
        volume, computed from the two most recent stored closes per ticker
        (same ROW_NUMBER window as get_latest_prices). The '^NSEI' index is
        excluded. Each row is {ticker, close_price, change_pct, volume}."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ticker, close_price, volume, rn FROM (
                        SELECT *, ROW_NUMBER() OVER (
                            PARTITION BY ticker ORDER BY price_date DESC
                        ) AS rn FROM daily_prices WHERE ticker != '^NSEI'
                    ) WHERE rn <= 2"""
            ).fetchall()

        latest, previous = {}, {}
        for r in rows:
            (latest if r["rn"] == 1 else previous)[r["ticker"]] = r

        movers = []
        for ticker, cur in latest.items():
            prev = previous.get(ticker)
            # ponytail: a ticker needs two stored closes to have a change_pct
            # (and to appear in most_active) — single-close tickers are skipped.
            if not prev or not prev["close_price"]:
                continue
            change_pct = round(
                (cur["close_price"] - prev["close_price"])
                / prev["close_price"] * 100, 2)
            movers.append({
                "ticker": ticker,
                "close_price": cur["close_price"],
                "change_pct": change_pct,
                "volume": cur["volume"] or 0,
            })

        gainers = sorted(movers, key=lambda m: m["change_pct"], reverse=True)
        losers = sorted(movers, key=lambda m: m["change_pct"])
        most_active = sorted(movers, key=lambda m: m["volume"], reverse=True)
        return {
            "gainers": gainers[:limit],
            "losers": losers[:limit],
            "most_active": most_active[:limit],
        }

    def get_trade_leaders(self, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Most-bought / most-sold tickers across all users' portfolio_trades,
        each side ranked by total traded quantity. Rows are
        {ticker, total_quantity, trade_count}."""
        with self._conn() as conn:
            def leaders(action: str) -> List[Dict[str, Any]]:
                rows = conn.execute(
                    """SELECT ticker, SUM(quantity) AS total_quantity,
                              COUNT(*) AS trade_count
                       FROM portfolio_trades WHERE action = ?
                       GROUP BY ticker
                       ORDER BY total_quantity DESC LIMIT ?""",
                    (action, limit)
                ).fetchall()
                return [{"ticker": r["ticker"],
                         "total_quantity": r["total_quantity"],
                         "trade_count": r["trade_count"]} for r in rows]

            return {"most_bought": leaders("BUY"),
                    "most_sold": leaders("SELL")}
