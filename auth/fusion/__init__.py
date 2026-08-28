"""
Score-level biometric fusion.

**Nothing in this package makes an authentication decision.** As of step 3 it
only defines the shapes that carry per-modality scores and sample quality, plus
the measurements themselves. The normalisation and weighting that would combine
them arrive in step 4, and even then run offline; letting fusion decide is
step 6 and is not in scope.

Design contract, from docs/fusion_architecture.md §2:

    Vetoes  — card, liveness, PIN, identity agreement.
              Any failure ends the session. No score compensates.
    Fused   — face + fingerprint only.

Liveness deliberately stays a veto. Were it a weighted term, a strong face
score could outvote a failed blink, reinstating the photo attack closed on
2026-08-02. Compensatory fusion is only sound between modalities answering the
same question ("is this the right person"); liveness answers a different one
("is this a person at all").

Everything here is pure: no I/O, no database, no config side effects at call
time. That is what makes it testable offline and unable to disturb the live
pipeline.

Not to be confused with auth/fusion_engine.py, which despite its name performs
no fusion — it is a subsystem holder for the ATM pipeline.
"""
