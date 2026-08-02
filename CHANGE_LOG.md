# Change Log

Security and infrastructure changes, newest first. Each entry records what
changed, how it was verified, and what was left undone.

---

## 2026-08-02 — Liveness and a confidence floor on passwordless face login

**Problem.** `/api/auth/face-login` took one frame and issued a full session —
no PIN, no challenge, nothing but a face. An enrolled photo of USR001 returned
HTTP 200 and a session token. It was the weakest surface in the system:
anyone holding a picture of an enrolled user *was* that user.

It also had **no `MIN_FACE_CONFIDENCE` floor at all**, unlike `face-verify`,
so a marginal match was enough — on the one path with no second factor to
catch it.

**Decision.** Option B of the three offered: keep passwordless face login and
harden it, rather than removing the endpoint (Option A) or requiring a PIN to
complete it (Option C). The cost picture had changed since the options were
first framed — `_count_blinks()` and `captureBurst()` already existed from the
face-verify work, so B became roughly 45 lines of reuse, while A had become
the *larger* frontend diff (the tab and panel would have to come out).

**Change.** Burst capture plus a required blink, matching the step-up; the
missing confidence floor; and failed attempts now log with `user_id=None`
instead of `"UNKNOWN"`.

That last one is not cosmetic. `auth_logs.user_id` is a foreign key to `users`
with `foreign_keys` ON, so the literal `"UNKNOWN"` violated the constraint and
`log_auth_event` swallowed the error — **spoof attempts against this endpoint
were never recorded**. NULL is permitted by the FK and stores, so they now are.

**Commits.**

| Commit | Change |
|:--|:--|
| `e95dd09` | Failing check: a photograph completes passwordless face login |
| `bdcfd5d` | Blink requirement, confidence floor, auditable failures |

**Verified** against the real endpoint with real photos of a real enrolled
user:

| Burst | Result |
|:--|:--|
| still photo held steady ×20 | **401** |
| two photos alternating | **401** |
| single closed frame (too brief) | **401** |
| open, open, CLOSED, CLOSED, open, open | **200**, session issued for USR001 |
| audit rows for the three rejections | **stored**, `user_id=NULL` |

Smoke test 16/16; `vite build` exit 0.

**Residual risk — larger here than on the step-up.** A video replay of the
account holder blinking still passes, and on this endpoint that is enough on
its own, because there is no second factor behind it. On `face-verify` the
same video is useless without the PIN. If you want that closed, Option C
(face identifies, PIN completes) is the answer, and it is now the only
material gap left on the web auth surface.

---

## 2026-08-02 — Require a blink on the face step-up

**Problem.** `/api/auth/face-verify` took a single frame and matched it, with
no liveness check. Demonstrated against the real endpoint before the fix:

    enrolled photo of USR001 -> HTTP 200, full session token

That made the face challenge worthless as a second factor. The PIN is checked
before the risk engine runs, so once the lockout is survived a correct PIN
yields a face challenge — and a photograph satisfied it. PIN guessing plus a
photo was a complete takeover. The lockout closed the guessing half; this
closes the rest.

**Change.** The endpoint takes a burst of frames and counts blinks across it
using `LivenessDetector.update_blink_state` — the same state machine the ATM
uses, extracted and tested in the earlier liveness fix. A still photograph
produces a perfectly constant EAR and can never blink.

Liveness runs **before** recognition, and only the single best frame (highest
EAR, eyes widest open) goes to InsightFace. Recognition is the expensive step
and there is no point running it on frames already known to be a photo; it
also means `_face_lock` is still held for exactly one inference, so the burst
does not lengthen the serialised section. MediaPipe runs on a per-request
detector (~36 ms warm), so it needs no lock at all. Total ≈ 20 × 14 ms +
294 ms, under 600 ms against a 45 s client timeout.

`FaceVerifyRequest.image` became `.images` — a **breaking API change**. The
old single-frame shape is deliberately rejected: one frame cannot contain a
blink, so accepting it could only produce confusing failures.

**Commits.**

| Commit | Change |
|:--|:--|
| `7e2b5e4` | Failing check: a photograph completes face 2FA today |
| `8d8660c` | Require a blink before matching (server) |
| `a436af9` | Burst capture and the blink prompt (frontend) |
| `b84cf20` | Tests for the burst aggregation |

**Verified against the real endpoint**, using real photos of a real enrolled
user. `USR001_007.jpg` measures EAR 0.139 — genuinely closed eyes — which is
what made an honest blink sequence possible without a webcam:

| Burst | Result |
|:--|:--|
| still photo held steady ×20 | **401** |
| two photos alternating, no closed eyes | **401** |
| single closed frame (too brief) | **401** |
| open, open, CLOSED, CLOSED, open, open | **200**, session issued for USR001 |
| blink mid-way through an 18-frame burst | **200** |

Smoke test 15/15; `tests/test_liveness.py` 15/15; `vite build` succeeds; the
login page renders with no console errors.

**Frontend.** 20 frames at 120 ms (~2.4 s). The interval is the load-bearing
number: a blink lasts 100–400 ms and must span at least `EYE_AR_CONSEC_FRAMES`
(2) captured frames, so sampling much slower drops fast blinks and locks out
real people. The panel says to blink *before* capture starts, the button reads
"Blink to Verify", and per-frame progress stops the 2.4 s looking like a hang.

**What this does NOT do.** A blink check does not defeat a **video replay** —
someone playing a video of the account holder blinking passes it. It raises
the bar from "any photo in your camera roll" to "a video of the target
blinking", which is real but not strong. Genuine anti-spoofing needs depth, IR
or texture analysis this hardware does not have.

**Availability cost, stated plainly.** 2FA fires on new devices and networks,
so this sits on the path of someone already having an unusual login. In a dim
room, with strong backlight, or with glasses glare, MediaPipe may not see the
face — and then the user cannot complete 2FA at all. They can retry until the
5-minute challenge expires, then start again with their PIN. If this locks
real users out in practice, the thresholds are the thing to revisit.

**Not verified.** No real webcam, no real face, no real printed photo, no
video replay. Every result above comes from still images. Needs a human:

1. Sign in with a PIN from a new device so the risk engine demands the face
   step-up, then blink when prompted → must succeed.
2. Repeat holding a phone photo of the enrolled user to the camera, without
   blinking → must fail with the liveness message.
3. Repeat in a dim room and with glasses on → confirm real users still pass.
4. Let the capture run without blinking → must fail, and the retry must work.

**Still open.** `/api/auth/face-login` (passwordless) remains single-frame with
no liveness and no confidence floor, by your decision. It is a strictly weaker
surface than the one just fixed.

---

## 2026-08-02 — Lock the web login after repeated failures

**Problem.** `/api/auth/login` verified the PIN and returned 401 on failure
with no attempt limit. `config.MAX_PIN_ATTEMPTS = 3` existed but was enforced
only in the Tkinter dialog (`ui/atm_interface.py`). PINs are 4 digits and user
IDs are sequential (`USR001`…`USR021`), so the entire keyspace was walkable
over HTTP against a guessable target.

Demonstrated against the real endpoint before the fix:

    3 wrong PINs -> [401, 401, 401], then the correct PIN -> 200

**Why this was the highest-priority item.** The PIN is verified *before* the
risk engine runs, so wrong PINs return a bare 401 and never reach it. A fast
brute force does trip the failed-attempts signal, so the correct PIN yields a
2FA challenge demanding a face — but `/api/auth/face-verify` has no liveness
check, so a photograph satisfies it. Brute force → challenge → photo →
session. Neither half is a clean takeover alone; together they are.

**Change.** The lockout check runs **before** `verify_pin` and refuses a locked
account even when the PIN is correct. Checking afterwards would admit the
attacker on the one guess that matters.

It reuses `count_recent_failed_logins` — the same rolling-window counter the
risk engine reads — so there is a single definition of "recent failed login".
Because the window rolls, the lock frees itself 15 minutes after the last
failure: no unlock endpoint, no new column, no new state.

Lockout hits log `result='lockout'`, deliberately **not** `'failure'`. The
counter only counts `'failure'`, so a sustained attack cannot keep pushing the
window forward and hold an account locked indefinitely. Verified: five extra
hits against a locked account left the count at three.

Returns **429** with `Retry-After` rather than 401, so a client can distinguish
"wrong PIN" from "stop trying", and the message names neither the account nor
the PIN.

**Commits.**

| Commit | Change |
|:--|:--|
| `496d1d6` | Failing smoke check driving the real endpoint |
| `7c12cdd` | The lockout itself (`config.py`, `webapp/backend/auth.py`) |

**Verified** against a copy of the database, driving the real endpoint:

| Check | Result |
|:--|:--|
| 3 wrong PINs | 401, 401, 401 |
| then the **correct** PIN | **429**, `Retry-After: 900` |
| message leaks account state? | no |
| a second user, correct PIN | 200 — unaffected |
| 5 further hits on the locked account | counted failures still 3 |
| after the window elapses | 200 — self-healed |
| nonexistent user | 401, no crash |

Smoke test 14/14, `web login lockout` moved from known-bad to passing and was
removed from the baseline, so it now guards against regression.

**Known trade-off.** Anyone can lock any account by sending three bad PINs to
a guessable user ID. That is inherent to per-user lockout and the sequential
IDs make it easier; the self-healing 15-minute window is the compromise.
Keying on user+IP would soften the DoS but gut the defence it exists for.

**Still open.**

- **`/api/auth/face-verify` has no liveness check**, so the second half of the
  chain above is intact: a photograph still satisfies the face step-up. The
  lockout makes reaching that step much harder; it does not close it.
- `/api/settings/change-pin` is a second unlimited PIN oracle. Its failures
  log as `pin_change`, so this counter does not see them. It requires a valid
  session first, so severity is lower. Deliberately left out of scope.
- **Audit blind spot:** `auth_logs.user_id` has a foreign key to `users` and
  `PRAGMA foreign_keys = ON`, so a failed login against a *nonexistent* user
  ID cannot be written and `log_auth_event` swallows the error. User-ID
  enumeration attempts are therefore invisible in the audit trail.
- The ATM dialog still counts attempts in memory, per dialog, with no
  server-side lock.

---

## 2026-08-02 — Pin a reproducible environment (requirements.lock.txt)

**Problem.** Every constraint in `requirements.txt` was an unbounded `>=`, so
a clean resolve picked numpy 2.5.1, OpenCV 5.0, mediapipe 1.0 and insightface
1.0 — major versions across the whole CV stack that this project has never run
on. The declarations were correct; the environment they produced was not the
one that works.

**Change.** Added `requirements.lock.txt`: all 93 packages at exact versions,
generated from the working venv. `requirements.txt` remains the human-readable
statement of intent. Install instructions in the README now point at the lock.

`opencv-python` in `requirements.txt` became `opencv-contrib-python`, because
contrib is the build that actually loads here (`cv2.xfeatures2d` is present)
and therefore the one every test has exercised. The lock pins contrib only —
all three OpenCV variants ship the same `cv2` and overwrite each other, so
pinning all three would leave the resulting binary dependent on pip's install
order, which is reproducibility in name only.

**The lock must be installed with `--no-deps`.**

```bash
pip install --no-deps -r requirements.lock.txt
```

This was discovered by testing, not predicted. A plain `pip install -r` fails
with `ResolutionImpossible`: OpenCV 4.13 declares `numpy>=2` while this stack
pins numpy 1.26.4, since numpy 2.x breaks these compiled extensions. `pip
check` flags the same conflict on the existing venv — **the working
environment is not internally consistent by pip's metadata.** It runs fine;
the ABI is compatible in practice. Because the lock is the complete closure,
`--no-deps` is the correct install and succeeds.

**Verified by building a real clean venv** (not a dry run):

| Check | Result |
|:--|:--|
| `pip install --no-deps -r requirements.lock.txt` | exit 0, 93 packages |
| `python -m scripts.smoke_test` under that interpreter | **13/13, 0 NEW** |
| `import config`, `webapp.backend.main` | OK, 13 routes |
| `cv2` with contrib only | 4.13.0, `SIFT_create` present |
| `albumentations` / `insightface` import | OK |
| InsightFace on an enrolled image | **uid=USR001, confidence=0.992** |

**Known wrinkles.**

- The lock is Windows + CPython 3.12 specific and will refuse to install
  elsewhere. Deliberate: failing loudly beats silently substituting untested
  wheels. Other platforms should use `requirements.txt` and re-verify.
- Dropping `opencv-python-headless` leaves `albucore`/`albumentations` naming
  it in `pip check`. Verified harmless — contrib supplies the same `cv2`, and
  both import and run in the clean venv.
- Pinning freezes the security posture; regenerate deliberately with
  `pip freeze`, then drop the two non-contrib OpenCV lines.
- Nothing was installed, uninstalled or upgraded in the project venv at any
  point. The test venv was built outside the repo and deleted afterwards.

---

## 2026-08-02 — Declare five undeclared dependencies

**Problem.** Five packages were imported but absent from `requirements.txt`, so
a clean `pip install -r requirements.txt` produced a project that crashed on
import. `python-dotenv` was the worst: `config.py` imports it at module level,
and `config` is imported by `main.py`, the Tkinter ATM and the whole web
backend — a fresh install failed at the first import.

**Change.** Added, with floors at or below the installed version. Where an
existing dependency already requires the package, the floor matches that
requirement exactly so these lines can never contradict the resolver:

| Added | Used by | Floor rationale |
|:--|:--|:--|
| `python-dotenv>=1.0` | `config.py` | installed 1.2.2 |
| `requests>=2.31` | `specific_picks.py`, `yf_worker.py`, `build_universe.py` | CVE-2023-32681 fix |
| `joblib>=1.3.0` | `fraud_detection/{detector,train}.py` | = scikit-learn's floor |
| `pydantic>=2.9.0` | `schemas.py`, `routers/advisor.py` | = FastAPI's floor; v2 API |
| `pandas>=1.3.0` | `portfolio/market_data.py` | = yfinance's floor |

`pandas` is never imported — `market_data.py` calls `.shift()/.mean()/.corr()`
on values yfinance returns, so the code depends on the pandas API without an
import. Declared to document that coupling, at a floor that is a resolver no-op.

**Nothing was installed; no package version changed.** numpy 1.26.4,
scipy 1.17.1, pandas 3.0.4 before and after. Found by AST-walking every import
in the project and diffing against `requirements.txt`, not by grepping.

**Verified.** Smoke test 13/13 before and after. Every requirement line
satisfied by the current venv. `from webapp.backend.main import app` →
13 routes. Re-run audit: no imported-but-undeclared packages remain.

`pip install --dry-run --ignore-installed -r requirements.txt` exits 0 and
resolves 78 packages with no conflicts. A real fresh venv was NOT built.

**Open issue this surfaced — requirements.txt does not reproduce this
environment.** Every constraint is an unbounded `>=`, so the dry run shows a
clean install today would pick major versions this project has never run on:

| Package | Installed here | Fresh install picks |
|:--|:--|:--|
| numpy | 1.26.4 | **2.5.1** |
| opencv-python | 4.13.0.92 | **5.0.0.93** |
| mediapipe | 0.10.33 | **1.0.0** |
| insightface | 0.7.3 | **1.0.1** |
| onnxruntime | 1.18.0 | 1.28.0 |
| scikit-learn | 1.8.0 | 1.9.0 |

The numpy 1.x → 2.x jump alone breaks many compiled extensions. So the import
errors are fixed, but a clean install is still not trustworthy. Fixing that
means upper bounds or a pinned lockfile — a separate decision, not taken here.

**Also noted, deliberately not fixed** (would require uninstalling):
`opencv-python`, `opencv-contrib-python` and `opencv-python-headless` are all
installed at 4.13.0.92. Each ships its own `cv2` and they overwrite one
another. No contrib-only APIs are used (`SIFT_create` moved into the main
module in OpenCV 4.4), so `opencv-python` remains the correct declaration.

---

## 2026-08-02 — Liveness: stop counting "no face" as "eyes closed"

**Problem.** `LivenessDetector._get_ear_from_frame` returned an eye-aspect
ratio of `0.0` when MediaPipe found no face. Callers decide a blink has begun
with `ear < EYE_AR_THRESH` (0.25), and `0.0 < 0.25`, so any frame without a
face counted as a closed eye. Hold a photograph to the camera, cover the lens
for two frames, uncover: that is one registered blink, and
`LIVENESS_BLINK_REQUIRED` is 1. A hand defeated the anti-spoofing check.

Confirmed empirically before changing anything — black, white and random-noise
frames all reported `ear=0.0`, and the ATM's comparison evaluated True for all
three.

**Change.** "No face" is now `None`, which cannot be mistaken for a low EAR: a
caller that forgets to handle it raises `TypeError` rather than silently
passing. Degenerate landmarks (zero eye width) were a second source of a
spurious `0.0` and return `None` too — unmeasurable is not "closed".

The blink state machine moved out of the threaded Tkinter loop in
`ui/atm_interface.py` onto `LivenessDetector.update_blink_state()`, so it
exists once and is testable without a webcam. The ATM keeps the camera and the
timeout; only the counting moved.

**A face lost mid-blink discards the blink in progress.** A blink is "eyes
closed, then open again, on a face we watched the whole time"; without the
face we cannot attest the eyes reopened on a live person, and that gap is the
attack. Cost: a user who turns away mid-blink must blink again.

**Commits.**

| Commit | Change |
|:--|:--|
| `32a0bbf` | Add failing smoke checks for the liveness no-face contract |
| `b02a381` | Stop counting "no face" as "eyes closed" |
| `11a1f76` | Add liveness regression tests, including the photograph case |

**Verified** (no webcam; synthetic frames and enrolled stills):

- Smoke test `liveness no-face contract` and `a still image cannot blink` both
  failed before the fix and pass after — 13/13, 0 NEW. Both were removed from
  the known-failure baseline so they now guard against regression.
- `python -m tests.test_liveness` — 11 assertions pass.
- The attack itself: photo + lens covered 2 frames → 0 blinks (was 1); covered
  4 frames → 0; photo held still ×15 → 0. A real blink still counts 1.

**NOT verified — needs a human at the machine.** No real face, real lighting,
real printed photo, or video replay was tested. Run these at the ATM:

1. `venv/Scripts/python.exe main.py`, authenticate normally, blink once →
   must pass. Baseline behaviour must still work.
2. Hold a printed or on-screen photo of an enrolled face to the camera, lens
   uncovered → must fail with "Liveness check failed".
3. Hold the photo, cover the lens ~2s, uncover, repeat 2–3× → **must still
   fail.** This is the exact attack fixed here; before the fix it succeeded.
4. Begin a real blink and turn away mid-blink → that blink must not count;
   blink again to pass.
5. Sit in dim light and blink several times → confirm a real user is not
   locked out. If they are, the threshold needs revisiting.
6. Check `logs/` for the liveness outcome of each run.

**Deliberately deferred by the project owner (still open).**

- **A still photograph still logs in over the web.** `/api/auth/face-login`
  accepts one frame, matches it, and issues a full session JWT with no
  liveness check of any kind. `/api/auth/face-verify` has the same
  single-frame weakness but is PIN-gated first. Neither was changed in this
  set; the decision on whether to remove passwordless face login or add burst
  liveness was postponed. **This fix hardens the ATM path only.**
- `/api/auth/face-login` also lacks the `MIN_FACE_CONFIDENCE` floor that
  `/api/auth/face-verify` enforces.
- `LIVENESS_BLINK_REQUIRED` is 1 ("lowered from 3 for convenience") while
  `PROGRESSION.md` documents it as 3, and the ATM prompt reads "Blink 2
  times". Left as-is by request; the docs still overstate the strength.
- Even with this fix, blink detection does not defeat a video replay. Real
  anti-spoofing needs depth, IR, or texture analysis this hardware lacks.

---

## 2026-08-02 — Remove the committed JWT signing key

**Problem.** `config.py` fell back to the constant
`"dev-secret-change-in-production"` whenever `JWT_SECRET` was unset — the
default, since `.env.example` never mentioned the variable. That constant is
identical on every machine running this code, so anyone who had seen the
repository could sign a token for any `user_id` and take over any account.
PyJWT separately flagged it as below the RFC 7518 minimum for HS256
(31 bytes; minimum 32).

**Change.** No constant fallback remains. `JWT_SECRET` is read from the
environment; when unset, a 32-byte urlsafe token is generated and cached in
`.jwt_secret` (gitignored). If that file cannot be written, the key stays
ephemeral for the process rather than degrading to a shared constant.

Generating rather than hard-failing at import is deliberate: `config` is
imported by `main.py` and, transitively, the Tkinter ATM. Neither issues a
JWT, so raising there would break enrollment and the CLI over a secret they
never use. `JWT_SECRET_IS_GENERATED` lets the web app warn on its own.

**Commits.**

| Commit | Change |
|:--|:--|
| `5ec9850` | Add `scripts/smoke_test.py` as a pre/post-commit regression gate |
| `bd96856` | Remove the committed `JWT_SECRET` fallback |
| `6d122e7` | Warn at web-app startup when the key was generated |
| `373ba87` | Document `JWT_SECRET` in `.env.example` and the README |

**Verified** (real server on port 8000, real HTTP calls):

- Startup with no `JWT_SECRET` logs the warning naming `.jwt_secret`; with
  `JWT_SECRET` set, no warning is logged.
- A token minted before a restart still authenticates after it (HTTP 200) —
  the persisted key survives restarts and `--reload` cycles.
- After changing `JWT_SECRET`, that same token is rejected (HTTP 401) and a
  freshly minted one works (HTTP 200), which survives a further restart.
- `import config` and `main.py --list-users` both exit 0 with no JWT warning.
- Smoke test 11/11 after every commit; the two baseline failures
  (default secret, key length) are now fixed and no new failure appeared.
- `.jwt_secret` is gitignored, absent from `git status`, and `git grep` for
  its contents across all tracked files returns nothing.

**Not verified.** The Tkinter ATM was not launched — it needs a webcam and a
display this environment does not have. Its exposure is limited to
`import config`, which is covered by the CLI check above. Multi-worker
uvicorn (`--workers N`) was not tested; with an unset `JWT_SECRET` each
worker generates its own key unless `.jwt_secret` already exists, so a first
run under multiple workers could race. Setting `JWT_SECRET` avoids this
entirely.

**Known gaps left open.**

- PINs remain unsalted SHA-256 (`_hash_pin`, `database/db_manager.py`), and
  the smoke test reports the scheme it detects on each run.
- The web login has no lockout; `MAX_PIN_ATTEMPTS` is enforced only in the
  Tkinter dialog.
- `/api/fraud/logs` returns every user's fraud logs to any authenticated
  caller, and `/api/fraud/toggle-blocking` switches fraud blocking off
  process-wide via `webapp/backend/state.py`.
