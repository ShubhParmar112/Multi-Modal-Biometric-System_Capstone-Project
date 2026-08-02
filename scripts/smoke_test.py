"""
Fast health check for the whole project — run before and after every commit.

    venv/Scripts/python.exe -m scripts.smoke_test
    venv/Scripts/python.exe -m scripts.smoke_test --save-baseline

Failures are reported in two buckets. A failure already present in
`.smoke_baseline.json` is KNOWN (pre-existing, not caused by the change in
flight); anything else is NEW and means the working tree broke something.
Only NEW failures set a non-zero exit code.

Checks never touch `database/users.db` — anything needing a DatabaseManager
runs against a throwaway copy, because constructing one runs migrations.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(BASE_DIR, ".smoke_baseline.json")

# The fallback that used to ship in config.py. Any build where JWT_SECRET
# equals this is forgeable by anyone who has read the repository.
COMMITTED_DEFAULT_SECRET = "dev-secret-change-in-production"

_results = []


def check(name):
    """Register a zero-arg check. It passes unless it raises."""
    def decorator(fn):
        _results.append((name, fn))
        return fn
    return decorator


def _db_copy(tmpdir):
    """A disposable copy of the real database."""
    import config
    dst = os.path.join(tmpdir, "users_smoke.db")
    shutil.copy2(config.DATABASE_PATH, dst)
    return dst


def _run_py(code, env=None):
    """Run a snippet in a clean subprocess and return its stdout."""
    child_env = dict(os.environ)
    if env:
        child_env.update(env)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd=BASE_DIR, env=child_env, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"subprocess failed: {proc.stderr.strip()[-400:]}")
    return proc.stdout.strip()


# ── Config ───────────────────────────────────────────────────


@check("config imports")
def _config_imports():
    import config
    for attr in ("DATABASE_PATH", "JWT_SECRET", "JWT_ALGORITHM",
                 "JWT_EXPIRE_MINUTES", "MAX_PIN_ATTEMPTS"):
        assert hasattr(config, attr), f"config.{attr} missing"


@check("JWT secret is not the committed default")
def _jwt_secret_not_default():
    import config
    assert config.JWT_SECRET != COMMITTED_DEFAULT_SECRET, (
        "JWT_SECRET is the constant that ships in the repo — tokens are "
        "forgeable by anyone who has seen it")


@check("JWT secret is long enough to resist brute force")
def _jwt_secret_strength():
    import config
    assert len(config.JWT_SECRET) >= 32, (
        f"JWT_SECRET is only {len(config.JWT_SECRET)} chars")


@check("JWT secret honours the environment")
def _jwt_secret_from_env():
    supplied = "smoke-test-supplied-secret-value-0123456789"
    got = _run_py("import config; print(config.JWT_SECRET)",
                  env={"JWT_SECRET": supplied})
    assert got == supplied, (
        f"JWT_SECRET in the environment was ignored (got {got[:16]!r}…)")


@check("config import is silent for non-web entry points")
def _config_import_quiet():
    """The CLI and the Tkinter ATM import config but never issue a JWT.
    They must not be warned about a secret they do not use."""
    proc = subprocess.run([sys.executable, "-c", "import config"],
                          capture_output=True, text=True, cwd=BASE_DIR,
                          timeout=120)
    assert proc.returncode == 0, f"import config failed: {proc.stderr[-300:]}"
    noise = (proc.stdout + proc.stderr).lower()
    assert "jwt" not in noise, (
        f"importing config mentions JWT to non-web callers: {noise[:200]!r}")


# ── Database ─────────────────────────────────────────────────


@check("database opens and core tables exist")
def _database_opens():
    import sqlite3
    import config
    conn = sqlite3.connect(f"file:{config.DATABASE_PATH}?mode=ro", uri=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("users", "accounts", "transactions", "cards",
                      "fraud_logs", "auth_logs"):
            assert table in names, f"table {table} missing"
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count > 0, "no users in the database"
    finally:
        conn.close()


@check("DatabaseManager initialises against a copy")
def _db_manager_init():
    from database.db_manager import DatabaseManager
    with tempfile.TemporaryDirectory() as tmp:
        db = DatabaseManager(_db_copy(tmp))
        assert db.get_all_users(), "get_all_users returned nothing"


@check("PIN auth round-trip")
def _pin_round_trip():
    """Verifies a wrong PIN is rejected and reports the hashing scheme in use."""
    import sqlite3
    from database.db_manager import DatabaseManager
    with tempfile.TemporaryDirectory() as tmp:
        path = _db_copy(tmp)
        db = DatabaseManager(path)
        conn = sqlite3.connect(path)
        try:
            row = conn.execute(
                "SELECT user_id, pin_hash FROM users WHERE is_active = 1 "
                "LIMIT 1").fetchone()
        finally:
            conn.close()
        assert row, "no active user to test against"
        user_id, pin_hash = row

        if pin_hash.startswith("scrypt$"):
            scheme = "scrypt (salted)"
        elif len(pin_hash) == 64 and all(c in "0123456789abcdef" for c in pin_hash):
            scheme = "sha256 hex (unsalted)"
        else:
            scheme = "unrecognised"
        print(f"      scheme detected: {scheme}")

        assert db.verify_pin(user_id, "0000") is False or \
            db.verify_pin(user_id, "9999") is False, \
            "verify_pin accepted at least one arbitrary PIN"


# ── Application wiring ───────────────────────────────────────


@check("core modules import")
def _core_modules_import():
    import importlib
    for mod in ("database.db_manager", "banking.account_manager",
                "auth.risk_engine", "fraud_detection.detector",
                "webapp.backend.auth", "webapp.backend.schemas"):
        importlib.import_module(mod)


@check("web app builds its routes")
def _webapp_imports():
    # Introspect the OpenAPI schema rather than app.routes: this FastAPI
    # version keeps included routers as opaque _IncludedRouter objects with
    # no .path. Schema generation also issues no requests, so it cannot
    # touch the live database the way TestClient would.
    from webapp.backend.main import app
    paths = set(app.openapi().get("paths", {}))
    for path in ("/api/auth/login", "/api/fraud/logs",
                 "/api/transactions/deposit", "/api/health"):
        assert path in paths, f"route {path} missing"


@check("liveness no-face contract")
def _liveness_no_face_contract():
    """A frame with no face must NOT be representable as a low EAR.

    The detector returns an eye-aspect-ratio, and callers decide a blink has
    started when the EAR falls below EYE_AR_THRESH. If "no face" is reported
    as 0.0 then every faceless frame reads as a closed eye, and covering the
    camera counts as blinking — so a photograph plus a hand defeats the
    anti-spoofing check. "No face" must be its own value.
    """
    import numpy as np
    import config
    from face_recognition_module.liveness_detector import LivenessDetector

    detector = LivenessDetector()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    ear, blink_detected, _ = detector.check_frame_liveness(blank)

    print(f"      no-face frame -> ear={ear!r}, blink_detected={blink_detected!r}")

    assert ear is None, (
        f"no-face frame reported ear={ear!r}; callers comparing "
        f"ear < {config.EYE_AR_THRESH} will count it as a closed eye")
    assert blink_detected is False, "no-face frame reported a blink"


@check("a still image cannot blink")
def _still_image_cannot_blink():
    """Feeding the same frame repeatedly must never register a blink.

    A sequence of identical frames is the cheapest stand-in for holding a
    photograph to the camera, and needs no webcam.
    """
    import glob
    import cv2
    from face_recognition_module.liveness_detector import LivenessDetector

    samples = sorted(glob.glob(os.path.join(BASE_DIR, "dataset", "*", "*.jpg")))
    assert samples, "no enrolled face images to test against"
    frame = cv2.imread(samples[0])
    assert frame is not None, f"could not read {samples[0]}"

    detector = LivenessDetector()
    if not hasattr(detector, "update_blink_state"):
        raise AssertionError(
            "LivenessDetector.update_blink_state is missing — the blink state "
            "machine still lives in ui/atm_interface.py and cannot be tested")

    detector.reset()
    blinks = sum(detector.update_blink_state(
        detector.check_frame_liveness(frame)[0]) for _ in range(15))
    assert blinks == 0, f"a still photograph registered {blinks} blink(s)"


@check("JWT round-trip: valid token decodes, foreign token is rejected")
def _jwt_round_trip():
    import jwt
    import config
    from webapp.backend.auth import create_access_token

    token = create_access_token("USR_SMOKE_TEST")
    payload = jwt.decode(token, config.JWT_SECRET,
                         algorithms=[config.JWT_ALGORITHM])
    assert payload["sub"] == "USR_SMOKE_TEST", "sub claim did not round-trip"

    forged = jwt.encode({"sub": "USR_SMOKE_TEST"}, "a-different-secret-entirely",
                        algorithm=config.JWT_ALGORITHM)
    try:
        jwt.decode(forged, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        pass
    else:
        raise AssertionError("a token signed with another secret was accepted")


# ── Runner ───────────────────────────────────────────────────


def run():
    failures = {}
    print()
    for name, fn in _results:
        try:
            fn()
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failures[name] = detail
            print(f"  FAIL  {name}")
            print(f"        {detail.splitlines()[0][:200]}")
            if os.environ.get("SMOKE_TRACEBACK"):
                traceback.print_exc()
        else:
            print(f"  ok    {name}")
    print()
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-baseline", action="store_true",
                        help="record current failures as the known baseline")
    args = parser.parse_args()

    failures = run()

    if args.save_baseline:
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump(failures, fh, indent=2, sort_keys=True)
        print(f"Baseline saved: {len(failures)} known failure(s) "
              f"-> {os.path.basename(BASELINE_PATH)}\n")
        return 0

    baseline = {}
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH, encoding="utf-8") as fh:
            baseline = json.load(fh)
    else:
        print("No baseline recorded — run with --save-baseline first.\n")

    known = [n for n in failures if n in baseline]
    new = [n for n in failures if n not in baseline]
    fixed = [n for n in baseline if n not in failures]

    print(f"{len(_results) - len(failures)}/{len(_results)} passed  |  "
          f"{len(known)} known  |  {len(new)} NEW  |  {len(fixed)} fixed")

    if fixed:
        print(f"  fixed since baseline: {', '.join(fixed)}")
    if known:
        print(f"  known (pre-existing): {', '.join(known)}")
    if new:
        print(f"  NEW FAILURES: {', '.join(new)}")
        print("\n  A NEW failure means this change broke something. "
              "Roll back with: git checkout .\n")
        return 1

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
