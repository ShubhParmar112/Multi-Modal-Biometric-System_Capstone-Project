"""
Main Entry Point - Multi-Modal Biometric Authentication System.
Provides CLI for system management and launches the ATM interface.

Usage:
    python main.py                  → Launch ATM interface
    python main.py --enroll         → Enroll a new user
    python main.py --encode         → Re-encode face dataset
    python main.py --list-users     → List all registered users
    python main.py --list-ports     → List available serial ports
    python main.py --simulate       → Run in simulation mode (no hardware)
    python main.py --test           → Run system self-test
    python main.py --bank USR001    → Open banking menu for a user
    python main.py --train-fraud-model → Train/select the fraud detection model
    python main.py --fraud-logs     → Show recent fraud log entries
    python main.py --analytics USR001 → Show monthly report + save charts
"""

import sys
import os
import argparse
import random
from datetime import datetime, timedelta

# Force UTF-8 encoding for standard output to support emojis/box-drawing characters on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from utils.logger import logger
from database.db_manager import DatabaseManager
from face_recognition_module.dataset_collector import DatasetCollector
from face_recognition_module.face_encoder import FaceEncoder
from face_recognition_module.face_recognizer import FaceRecognizer
from fingerprint_module.serial_handler import SerialHandler
from banking.account_manager import BankingService
from fraud_detection import train as fraud_train
from analytics.reports import FinanceAnalytics
from analytics import charts as analytics_charts


def enroll_user():
    """Interactive user enrollment workflow."""
    logger.system_event("Enrollment", "Starting new user enrollment")

    db = DatabaseManager()

    # Get user details
    print("\n" + "=" * 50)
    print("   NEW USER ENROLLMENT")
    print("=" * 50)

    user_id = input("\n  User ID (e.g., USR001): ").strip().upper()
    if not user_id:
        logger.error("User ID cannot be empty")
        return

    # Check if user already exists
    if db.get_user(user_id):
        logger.error(f"User {user_id} already exists!")
        return

    name = input("  Full Name: ").strip()
    if not name:
        logger.error("Name cannot be empty")
        return

    # Email address for transaction alerts (debit/credit mails)
    import re
    email = input("  Email (for transaction alerts): ").strip()
    while email and not re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", email):
        logger.warning("That doesn't look like a valid email address")
        email = input("  Email (leave blank to skip): ").strip()
    email = email or None

    pin = input("  4-digit PIN: ").strip()
    if len(pin) != config.PIN_LENGTH or not pin.isdigit():
        logger.error(f"PIN must be exactly {config.PIN_LENGTH} digits")
        return

    pin_confirm = input("  Confirm PIN: ").strip()
    if pin != pin_confirm:
        logger.error("PINs do not match")
        return

    # ── Step 1: Collect face images ──────────────────────
    print(f"\n{'─' * 50}")
    print("  STEP 1: Face Image Collection")
    print(f"{'─' * 50}")
    print("  We will capture 20 face images from your webcam.")
    print("  Follow the on-screen instructions.\n")

    mode = input("  Capture mode - [M]anual or [A]uto? (M/A): ").strip().upper()

    collector = DatasetCollector()
    if mode == "A":
        user_dir = collector.collect_auto(user_id, name, num_images=20)
    else:
        user_dir = collector.collect_faces(user_id, name, num_images=20)

    if not user_dir:
        logger.error("Face collection failed. Enrollment aborted.")
        return

    # ── Step 2: Generate face encodings ──────────────────
    print(f"\n{'─' * 50}")
    print("  STEP 2: Generating Face Encodings")
    print(f"{'─' * 50}\n")

    encoder = FaceEncoder()
    if not encoder.encode_dataset():
        logger.error("Face encoding failed. Enrollment aborted.")
        return

    avg_encoding = encoder.get_average_encoding(user_id)

    # ── Step 3: Fingerprint enrollment ───────────────────
    print(f"\n{'─' * 50}")
    print("  STEP 3: Fingerprint Enrollment")
    print(f"{'─' * 50}\n")

    if config.SOFTWARE_FINGERPRINT:
        # ── Software-based fingerprint enrollment ────────────────
        print("  📷 Software Fingerprint Mode")
        print("  Provide path(s) to fingerprint image(s) from the SOCOFing dataset.")
        print("  Supported formats: JPG, PNG, BMP, TIF")
        print("  Separate multiple paths with commas.\n")

        paths_input = input("  Image path(s): ").strip()
        if not paths_input:
            logger.error("No image paths provided")
            return

        image_paths = [p.strip().strip('"').strip("'")
                       for p in paths_input.split(",")]

        valid_paths = []
        for p in image_paths:
            if os.path.exists(p):
                valid_paths.append(p)
            else:
                logger.warning(f"File not found: {p}")

        if not valid_paths:
            logger.error("No valid fingerprint images found")
            return

        # Copy images to fingerprint dataset directory
        import shutil
        fp_dataset_dir = os.path.join(config.FINGERPRINT_DATASET_DIR, user_id)
        os.makedirs(fp_dataset_dir, exist_ok=True)

        saved_paths = []
        for i, src in enumerate(valid_paths):
            ext = os.path.splitext(src)[1]
            dst = os.path.join(fp_dataset_dir, f"fingerprint_{i:03d}{ext}")
            shutil.copy2(src, dst)
            saved_paths.append(dst)
            logger.info(f"Saved: {os.path.basename(src)} → {dst}")

        # Enroll via ORB image matcher
        from fingerprint_module.image_matcher import FingerprintImageMatcher
        matcher = FingerprintImageMatcher()
        matcher.load_templates()  # Load existing templates
        fingerprint_id = matcher.enroll(user_id, saved_paths)

        if fingerprint_id is None:
            logger.error("Fingerprint enrollment failed — no features extracted")
            return

        print(f"\n  ✓ Fingerprint enrolled as ID {fingerprint_id}")
        print(f"  ✓ {len(saved_paths)} image(s) processed")

    else:
        # ── Hardware-based enrollment (R307S via ESP32) ──────────
        fingerprint_id = input("  Fingerprint ID (1-127): ").strip()
        try:
            fingerprint_id = int(fingerprint_id)
            if not (1 <= fingerprint_id <= 127):
                raise ValueError
        except ValueError:
            logger.error("Fingerprint ID must be between 1 and 127")
            return

        if not config.SIMULATION_MODE:
            serial_handler = SerialHandler()
            if serial_handler.connect():
                print("\n  Place your finger on the R307S sensor...")
                print("  You will need to place it twice for enrollment.\n")

                if not serial_handler.request_enrollment(fingerprint_id):
                    logger.error("Fingerprint enrollment failed")
                    serial_handler.disconnect()
                    return
                serial_handler.disconnect()
            else:
                logger.warning("ESP32 not connected. Skipping hardware enrollment.")
                print("  ⚠ Fingerprint ID will be saved but not enrolled on sensor.")
                print("  ⚠ Enroll on sensor separately using Arduino Serial Monitor.")
        else:
            logger.info(f"SIMULATION: Fingerprint ID {fingerprint_id} registered")

    # ── Step 4: Save to database ─────────────────────────
    print(f"\n{'─' * 50}")
    print("  STEP 4: Saving to Database")
    print(f"{'─' * 50}\n")

    success = db.add_user(
        user_id=user_id,
        name=name,
        fingerprint_id=fingerprint_id,
        pin=pin,
        face_encoding=avg_encoding,
        email=email
    )

    if success:
        account_id = db.create_account(user_id)
        expiry = (datetime.now() + timedelta(days=5 * 365)).strftime("%m/%y")
        cvv = f"{random.randint(0, 999):03d}"
        card_number = db.create_card(account_id, user_id, expiry, cvv)

        print("\n" + "=" * 50)
        print("   ✅ ENROLLMENT SUCCESSFUL!")
        print("=" * 50)
        print(f"   User ID      : {user_id}")
        print(f"   Name          : {name}")
        print(f"   Email         : {email or '(not set)'}")
        print(f"   Fingerprint   : ID {fingerprint_id}")
        print(f"   Face Images   : {user_dir}")
        print(f"   PIN           : {'*' * config.PIN_LENGTH}")
        print(f"   Account ID    : {account_id}")
        print(f"   Card Number   : {card_number}")
        print(f"   CVV           : {cvv}")
        print("=" * 50 + "\n")
    else:
        logger.error("Failed to save user to database")


def encode_faces():
    """Re-encode all face images in the dataset directory."""
    logger.system_event("Encoder", "Re-encoding face dataset")
    encoder = FaceEncoder()
    if encoder.encode_dataset():
        logger.success("Face encoding complete")

        # Optionally update database encodings
        db = DatabaseManager()
        for user_id in encoder.known_encodings:
            avg = encoder.get_average_encoding(user_id)
            if avg is not None:
                db.update_face_encoding(user_id, avg)
                logger.info(f"Updated DB encoding for {user_id}")
    else:
        logger.error("Face encoding failed")


def list_users():
    """Display all registered users."""
    db = DatabaseManager()
    users = db.get_all_users()

    if not users:
        print("\n  No users registered.\n")
        return

    print("\n" + "=" * 60)
    print("  REGISTERED USERS")
    print("=" * 60)
    print(f"  {'ID':<10} {'Name':<20} {'FP ID':<8} {'Created':<20}")
    print("  " + "─" * 56)
    for user in users:
        print(f"  {user['user_id']:<10} {user['name']:<20} "
              f"{user['fingerprint_id']:<8} {user['created_at']:<20}")
    print("=" * 60)
    print(f"  Total: {len(users)} user(s)\n")


def _choose_category(db: DatabaseManager) -> str:
    """Print the available categories and let the user pick one, or add a new one."""
    categories = db.get_categories()
    print("\n  Categories:")
    for i, name in enumerate(categories, start=1):
        print(f"    {i}) {name}")
    print(f"    {len(categories) + 1}) Add new category")

    choice = input("  Choose a category: ").strip()
    try:
        idx = int(choice)
    except ValueError:
        return "Other"

    if 1 <= idx <= len(categories):
        return categories[idx - 1]
    if idx == len(categories) + 1:
        new_name = input("  New category name: ").strip()
        if new_name:
            db.add_category(new_name)
            return new_name

    return "Other"


def bank_menu(user_id: str):
    """Interactive CLI banking menu for an enrolled user (PIN-gated)."""
    db = DatabaseManager()
    user = db.get_user(user_id)
    if not user:
        logger.error(f"No such user: {user_id}")
        return

    pin = input(f"  Enter PIN for {user_id}: ").strip()
    if not db.verify_pin(user_id, pin):
        logger.error("Incorrect PIN")
        return

    banking = BankingService(db)

    while True:
        print("\n" + "=" * 40)
        print(f"  BANKING MENU — {user['name']}")
        print("=" * 40)
        print("  1) Balance Inquiry")
        print("  2) Deposit")
        print("  3) Withdraw")
        print("  4) Transfer")
        print("  5) Mini Statement")
        print("  6) Exit")
        print(f"  7) Toggle Fraud Blocking (currently "
              f"{'ON' if banking.block_high_risk else 'OFF'})")
        print("  8) Personal Finance Analytics")
        choice = input("  Choose an option: ").strip()

        if choice == "1":
            balance = banking.get_balance(user_id)
            print(f"\n  Balance: {balance}")

        elif choice == "2":
            amount = float(input("  Amount to deposit: ").strip())
            success, message, balance = banking.deposit(user_id, amount)
            print(f"\n  {message} (Balance: {balance})" if success else f"\n  {message}")

        elif choice == "3":
            amount = float(input("  Amount to withdraw: ").strip())
            category = _choose_category(db)
            success, message, balance = banking.withdraw(user_id, amount, category=category)
            print(f"\n  {message} (Balance: {balance})" if success else f"\n  {message}")

        elif choice == "4":
            to_account = input("  Destination account number: ").strip()
            amount = float(input("  Amount to transfer: ").strip())
            category = _choose_category(db)
            success, message, balance = banking.transfer(user_id, to_account, amount, category=category)
            print(f"\n  {message} (Balance: {balance})" if success else f"\n  {message}")

        elif choice == "5":
            statement = banking.get_mini_statement(user_id)
            if not statement:
                print("\n  No transactions found.")
            else:
                print(f"\n  {'Type':<14} {'Category':<14} {'Amount':<12} "
                      f"{'Balance':<12} {'Timestamp':<20}")
                print("  " + "─" * 72)
                for txn in statement:
                    print(f"  {txn['txn_type']:<14} {txn['category']:<14} "
                          f"{txn['amount']:<12} {txn['balance_after']:<12} "
                          f"{txn['timestamp']:<20}")

        elif choice == "6":
            print("\n  Logged out.\n")
            break

        elif choice == "7":
            banking.set_fraud_blocking(not banking.block_high_risk)
            print(f"\n  Fraud blocking is now "
                  f"{'ON' if banking.block_high_risk else 'OFF'}.")

        elif choice == "8":
            show_analytics(user_id)

        else:
            print("\n  Invalid option.")


def train_fraud_model():
    """Train Isolation Forest, LOF, and XGBoost; keep whichever wins on F1."""
    print("\n" + "=" * 50)
    print("   FRAUD MODEL TRAINING")
    print("=" * 50 + "\n")

    results, best_name = fraud_train.train_and_select_best()

    print(f"  {'Model':<22} {'F1':<8} {'Precision':<12} {'Recall':<8}")
    print("  " + "─" * 50)
    for name, metrics in results.items():
        marker = " *" if name == best_name else ""
        print(f"  {name:<22} {metrics['f1']:<8} "
              f"{metrics['precision']:<12} {metrics['recall']:<8}{marker}")
    print(f"\n  Winner: {best_name}\n")


def fraud_logs_report():
    """Display recent fraud log entries."""
    db = DatabaseManager()
    logs = db.get_fraud_logs(limit=20)

    if not logs:
        print("\n  No fraud log entries found.\n")
        return

    print("\n" + "=" * 70)
    print("  RECENT FRAUD LOGS")
    print("=" * 70)
    print(f"  {'Txn ID':<8} {'Score':<8} {'Category':<10} "
          f"{'Model':<22} {'Flagged At':<20}")
    print("  " + "─" * 66)
    for log in logs:
        print(f"  {log['transaction_id']:<8} {log['risk_score']:<8} "
              f"{log['risk_category']:<10} {log['model_used']:<22} "
              f"{log['flagged_at']:<20}")
    print("=" * 70)
    print(f"  Total: {len(logs)} entr{'y' if len(logs) == 1 else 'ies'}\n")


def show_analytics(user_id: str):
    """Print the current month's finance report and save visualization charts."""
    db = DatabaseManager()
    if not db.get_user(user_id):
        logger.error(f"No such user: {user_id}")
        return

    analytics = FinanceAnalytics(db)
    report = analytics.monthly_report(user_id)

    print("\n" + "=" * 50)
    print(f"   PERSONAL FINANCE REPORT — {report['month']}")
    print("=" * 50)
    print(f"   Total Income   : {report['total_income']}")
    print(f"   Total Expense  : {report['total_expense']}")
    print(f"   Net Savings    : {report['net_savings']}")
    print("-" * 50)
    print("   Category Breakdown:")
    if not report["category_breakdown"]:
        print("     (no expenses this month)")
    else:
        for category, total in report["category_breakdown"].items():
            print(f"     {category:<16} {total}")
    print("=" * 50)

    output_dir = os.path.join(config.ANALYTICS_OUTPUT_DIR, user_id)
    paths = analytics_charts.save_all_charts(user_id, analytics, output_dir)
    print("\n   Charts saved:")
    for path in paths:
        print(f"     {path}")
    print()


def list_ports():
    """List available serial ports."""
    handler = SerialHandler()
    ports = handler.list_available_ports()
    if not ports:
        print("\n  No serial ports found.\n")
    else:
        print("\n  Available Serial Ports:")
        print("  " + "─" * 45)
        for p in ports:
            print(f"  {p['device']:<10} │ {p['description']}")
        print()


def run_self_test():
    """Run a system self-test to verify all components."""
    print("\n" + "=" * 50)
    print("   SYSTEM SELF-TEST")
    print("=" * 50 + "\n")

    results = {}

    # Test 1: Database
    print("  [1/5] Database...", end=" ")
    try:
        db = DatabaseManager()
        db.get_all_users()
        print("✅ OK")
        results["Database"] = True
    except Exception as e:
        print(f"❌ FAIL: {e}")
        results["Database"] = False

    # Test 2: Face encodings
    print("  [2/5] Face Encodings...", end=" ")
    if os.path.exists(config.ENCODINGS_FILE):
        try:
            recognizer = FaceRecognizer()
            recognizer.load_encodings()
            print(f"✅ OK ({len(recognizer.known_ids)} encodings)")
            results["Face Encodings"] = True
        except Exception as e:
            print(f"❌ FAIL: {e}")
            results["Face Encodings"] = False
    else:
        print("⚠️  NOT FOUND (run --encode first)")
        results["Face Encodings"] = False

    # Test 3: Webcam
    print("  [3/5] Webcam...", end=" ")
    try:
        import cv2
        cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret:
                print(f"✅ OK ({frame.shape[1]}x{frame.shape[0]})")
                results["Webcam"] = True
            else:
                print("❌ FAIL: Cannot read frame")
                results["Webcam"] = False
        else:
            print("❌ FAIL: Cannot open camera")
            results["Webcam"] = False
    except Exception as e:
        print(f"❌ FAIL: {e}")
        results["Webcam"] = False

    # Test 4: Fingerprint subsystem
    if config.SOFTWARE_FINGERPRINT:
        print("  [4/5] Fingerprint Templates...", end=" ")
        if os.path.exists(config.FINGERPRINT_TEMPLATES_FILE):
            try:
                from fingerprint_module.image_matcher import FingerprintImageMatcher
                matcher = FingerprintImageMatcher()
                if matcher.load_templates():
                    print(f"✅ OK ({len(matcher.templates)} templates)")
                    results["Fingerprint"] = True
                else:
                    print("❌ FAIL: Cannot load templates")
                    results["Fingerprint"] = False
            except Exception as e:
                print(f"❌ FAIL: {e}")
                results["Fingerprint"] = False
        else:
            print("⚠️  NOT FOUND (run --enroll first)")
            results["Fingerprint"] = False
    elif config.SIMULATION_MODE:
        print("  [4/5] Serial Port...", end=" ")
        print("⚠️  SIMULATION MODE (skipped)")
        results["Serial Port"] = None
    else:
        print("  [4/5] Serial Port...", end=" ")
        try:
            handler = SerialHandler()
            if handler.connect():
                print(f"✅ OK ({config.SERIAL_PORT})")
                handler.disconnect()
                results["Serial Port"] = True
            else:
                print(f"❌ FAIL: Cannot connect to {config.SERIAL_PORT}")
                results["Serial Port"] = False
        except Exception as e:
            print(f"❌ FAIL: {e}")
            results["Serial Port"] = False

    # Test 5: Dataset directory
    print("  [5/5] Dataset...", end=" ")
    if os.path.exists(config.DATASET_DIR):
        users = [d for d in os.listdir(config.DATASET_DIR)
                 if os.path.isdir(os.path.join(config.DATASET_DIR, d))]
        total_images = sum(
            len([f for f in os.listdir(os.path.join(config.DATASET_DIR, u))
                 if f.endswith(('.jpg', '.png'))])
            for u in users
        )
        print(f"✅ OK ({len(users)} users, {total_images} images)")
        results["Dataset"] = True
    else:
        print("⚠️  EMPTY (run --enroll first)")
        results["Dataset"] = False

    # Summary
    passed = sum(1 for v in results.values() if v is True)
    total = sum(1 for v in results.values() if v is not None)
    print(f"\n  Result: {passed}/{total} checks passed")
    print("=" * 50 + "\n")


def main():
    """Main entry point with CLI argument handling."""
    parser = argparse.ArgumentParser(
        description="Multi-Modal Biometric Authentication System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  Launch ATM interface
  python main.py --simulate       Launch in simulation mode
  python main.py --enroll         Enroll a new user
  python main.py --encode         Re-encode face dataset
  python main.py --list-users     Show registered users
  python main.py --list-ports     Show serial ports
  python main.py --test           Run system self-test
  python main.py --bank USR001    Open banking menu for a user
  python main.py --train-fraud-model  Train/select the fraud model
  python main.py --fraud-logs     Show recent fraud log entries
  python main.py --analytics USR001  Show monthly report + save charts
        """
    )

    parser.add_argument("--enroll", action="store_true",
                        help="Enroll a new user")
    parser.add_argument("--encode", action="store_true",
                        help="Re-encode face dataset")
    parser.add_argument("--list-users", action="store_true",
                        help="List all registered users")
    parser.add_argument("--list-ports", action="store_true",
                        help="List available serial ports")
    parser.add_argument("--simulate", action="store_true",
                        help="Run in simulation mode (no hardware)")
    parser.add_argument("--test", action="store_true",
                        help="Run system self-test")
    parser.add_argument("--port", type=str,
                        help="Override serial port (e.g., COM4)")
    parser.add_argument("--bank", type=str, metavar="USER_ID",
                        help="Open the PIN-gated CLI banking menu for a user")
    parser.add_argument("--train-fraud-model", action="store_true",
                        help="Train Isolation Forest/LOF/XGBoost and keep the best by F1")
    parser.add_argument("--fraud-logs", action="store_true",
                        help="Show recent fraud log entries")
    parser.add_argument("--analytics", type=str, metavar="USER_ID",
                        help="Show a user's monthly finance report and save charts")

    args = parser.parse_args()

    # Apply overrides
    if args.simulate:
        config.SIMULATION_MODE = True
        logger.info("🔧 SIMULATION MODE enabled")

    if args.port:
        config.SERIAL_PORT = args.port
        logger.info(f"Serial port overridden to: {args.port}")

    # ── Banner ────────────────────────────────────────────
    print("\n" + "═" * 56)
    print("  🏦 Multi-Modal Biometric Authentication System")
    print("     Face Recognition + Fingerprint + PIN Fusion")
    print("═" * 56)

    # ── Dispatch ──────────────────────────────────────────
    if args.enroll:
        enroll_user()
    elif args.encode:
        encode_faces()
    elif args.list_users:
        list_users()
    elif args.list_ports:
        list_ports()
    elif args.test:
        run_self_test()
    elif args.bank:
        bank_menu(args.bank)
    elif args.train_fraud_model:
        train_fraud_model()
    elif args.fraud_logs:
        fraud_logs_report()
    elif args.analytics:
        show_analytics(args.analytics)
    else:
        # Launch ATM interface
        logger.system_event("Main", "Launching ATM Interface")
        from ui.atm_interface import ATMInterface
        app = ATMInterface()
        app.run()


if __name__ == "__main__":
    main()
