# Change Log

Security and infrastructure changes, newest first. Each entry records what
changed, how it was verified, and what was left undone.

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
