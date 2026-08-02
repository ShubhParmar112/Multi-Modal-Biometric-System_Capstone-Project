"""Blink/liveness contract checks.

pytest isn't installed in this repo, so this runs as a plain script:

    venv/Scripts/python.exe -m tests.test_liveness

It's kept pytest-compatible anyway — the assertions live in test_* functions
that a future pytest run would collect, and main() just calls them.

These test the state machine, not the camera. Every case runs without a
webcam: EAR sequences are supplied directly, and the "photograph" case feeds
one enrolled still image repeatedly. MediaPipe is deterministic on identical
input, so a still image produces a perfectly constant EAR (measured spread
0.0 over 15 frames) and can never produce a blink.

What these CANNOT cover: a real face, real lighting, a real printed photo, or
a real video replay. See CHANGE_LOG.md for the manual test list.
"""

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from face_recognition_module.liveness_detector import LivenessDetector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OPEN = 0.31    # comfortably above EYE_AR_THRESH (0.25)
CLOSED = 0.10  # comfortably below
CONSEC = config.EYE_AR_CONSEC_FRAMES


def _fresh():
    d = LivenessDetector()
    d.reset()
    return d


def _feed(detector, ears):
    for e in ears:
        detector.update_blink_state(e)
    return detector.blink_count


# ── The contract: "no face" is not "eyes closed" ─────────────


def test_no_face_reports_none_not_zero():
    """The bug: 0.0 < EYE_AR_THRESH, so a faceless frame read as a shut eye."""
    ear, eyes_closed, _ = _fresh().check_frame_liveness(
        np.zeros((480, 640, 3), dtype=np.uint8))
    assert ear is None, f"expected None for a faceless frame, got {ear!r}"
    assert eyes_closed is False


def test_none_ear_never_counts_as_closed():
    """A long run of no-face frames must not accumulate a blink."""
    assert _feed(_fresh(), [None] * 30) == 0


# ── The attack ───────────────────────────────────────────────


def test_hand_over_lens_is_not_a_blink():
    """FINDING 2 exactly: photo, cover the lens, uncover. Was 1 blink."""
    assert _feed(_fresh(), [OPEN, OPEN, None, None, OPEN, OPEN]) == 0


def test_repeated_still_image_counts_zero_blinks():
    """A photograph held to the camera: the same frame, over and over."""
    samples = sorted(glob.glob(os.path.join(BASE_DIR, "dataset", "*", "*.jpg")))
    if not samples:
        print("    (skipped: no enrolled face images available)")
        return

    import cv2
    frame = cv2.imread(samples[0])
    assert frame is not None, f"could not read {samples[0]}"

    d = _fresh()
    for _ in range(15):
        d.update_blink_state(d.check_frame_liveness(frame)[0])
    assert d.blink_count == 0, \
        f"a still photograph registered {d.blink_count} blink(s)"


# ── A real user must still get through ───────────────────────


def test_real_blink_is_counted():
    """Eyes shut for EYE_AR_CONSEC_FRAMES, then reopened, is one blink."""
    assert _feed(_fresh(), [OPEN] + [CLOSED] * CONSEC + [OPEN]) == 1


def test_two_blinks_are_counted_separately():
    seq = [OPEN] + [CLOSED] * CONSEC + [OPEN, OPEN] + [CLOSED] * CONSEC + [OPEN]
    assert _feed(_fresh(), seq) == 2


def test_blink_completes_only_on_reopening():
    """Eyes still shut at the end of the sequence is not yet a blink."""
    assert _feed(_fresh(), [OPEN] + [CLOSED] * 10) == 0


def test_too_brief_to_be_a_blink():
    """A single sub-threshold frame is noise, not a blink."""
    if CONSEC <= 1:
        print("    (skipped: EYE_AR_CONSEC_FRAMES is 1, every dip counts)")
        return
    assert _feed(_fresh(), [OPEN, CLOSED, OPEN]) == 0


# ── Losing the face mid-blink ────────────────────────────────


def test_face_lost_mid_blink_discards_the_blink():
    """We cannot attest the eyes reopened on a live face, so it does not count."""
    assert _feed(_fresh(), [OPEN] + [CLOSED] * CONSEC + [None, OPEN]) == 0


def test_user_can_recover_after_losing_the_face():
    """The discarded blink costs the user one blink, not the whole attempt."""
    seq = [OPEN] + [CLOSED] * CONSEC + [None, OPEN] + [CLOSED] * CONSEC + [OPEN]
    assert _feed(_fresh(), seq) == 1


def test_reset_clears_in_progress_state():
    d = _fresh()
    _feed(d, [OPEN] + [CLOSED] * CONSEC)
    d.reset()
    assert _feed(d, [OPEN]) == 0


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"  ok   {fn.__name__}")
    print(f"\nOK - all {len(tests)} liveness assertions passed.")


if __name__ == "__main__":
    main()
