"""Step 3 score-plumbing contract.

pytest isn't installed in this repo, so this runs as a plain script:

    venv/Scripts/python.exe -m tests.test_fusion_plumbing

The whole point of step 3 is that it adds data without changing behaviour, so
these tests are mostly about what did *not* change:

  - the legacy tuple APIs keep their exact shapes and values
  - the liveness verdict is unaffected by recording the EAR trajectory
  - "not measured" never collapses into "measured as zero"

Quality metrics and dataclasses run without any model. The face recognizer is
exercised only where it needs no ONNX session; the equivalence of the legacy
and detailed recognition paths is asserted structurally, and end-to-end by the
smoke test's existing face checks.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from auth.fusion import quality, scores


# ── Quality: face ────────────────────────────────────────────


def _frame(value=128, size=(120, 160)):
    return np.full((size[0], size[1], 3), value, dtype=np.uint8)


def test_face_quality_reports_all_metrics():
    metrics = quality.face_quality(_frame(), [10, 10, 100, 100], det_score=0.9)
    for key in ("blur_var", "luma_mean", "luma_std", "bbox_area", "det_score"):
        assert key in metrics, f"{key} missing from {sorted(metrics)}"


def test_flat_image_has_zero_blur_variance():
    """A uniform crop has no edges, so the focus measure must bottom out."""
    metrics = quality.face_quality(_frame(128), [0, 0, 100, 100])
    assert metrics["blur_var"] == 0.0
    assert metrics["luma_mean"] == 128.0
    assert metrics["luma_std"] == 0.0


def test_noisy_image_has_higher_blur_variance_than_flat():
    rng = np.random.default_rng(0)
    noisy = rng.integers(0, 255, (120, 160, 3), dtype=np.uint8)
    sharp = quality.face_quality(noisy, [0, 0, 160, 120])["blur_var"]
    flat = quality.face_quality(_frame(), [0, 0, 160, 120])["blur_var"]
    assert sharp > flat, "a textured crop must measure sharper than a flat one"


def test_bbox_is_clamped_to_the_image():
    """Detector boxes routinely overhang the frame; numpy would silently
    truncate the slice and measure a different region."""
    metrics = quality.face_quality(_frame(), [-50, -50, 9999, 9999])
    assert metrics["bbox_area"] == 120 * 160, \
        "clamped area should equal the whole frame, got " \
        f"{metrics['bbox_area']}"


def test_degenerate_bbox_yields_zeros_not_an_exception():
    metrics = quality.face_quality(_frame(), [50, 50, 50, 50])
    assert metrics["blur_var"] == 0.0 and metrics["bbox_area"] == 0.0


def test_bbox_entirely_outside_the_image():
    metrics = quality.face_quality(_frame(), [500, 500, 600, 600])
    assert metrics["bbox_area"] == 0.0


def test_det_score_is_omitted_when_unknown():
    """Absent inputs are omitted, never defaulted — see the fingerprint case."""
    assert "det_score" not in quality.face_quality(_frame(), [0, 0, 50, 50])


# ── Quality: fingerprint ─────────────────────────────────────


def test_fingerprint_quality_omits_absent_inputs():
    assert quality.fingerprint_quality() == {}
    assert quality.fingerprint_quality(keypoint_count=120) == {
        "keypoint_count": 120.0}
    assert quality.fingerprint_quality(sensor_confidence=145) == {
        "sensor_confidence": 145.0}


def test_fingerprint_zero_is_kept_distinct_from_missing():
    """A sensor score of 0 is a measurement; absence is not."""
    assert quality.fingerprint_quality(sensor_confidence=0) == {
        "sensor_confidence": 0.0}
    assert "sensor_confidence" not in quality.fingerprint_quality()


# ── Quality: liveness trajectory ─────────────────────────────


def test_liveness_quality_on_a_constant_trajectory():
    """A still photograph produces a perfectly constant EAR — the signature
    this statistic exists to expose.

    Compared against a tolerance rather than exact zero: 0.3 has no exact
    binary representation, so the mean of fifteen identical copies differs from
    each by ~1e-17 and the variance lands near 1e-33 rather than at 0.0. Any
    threshold distinguishing a photo from a live face sits far above that.
    """
    stats = quality.liveness_quality([0.3] * 15)
    assert stats["ear_variance"] < 1e-12, stats["ear_variance"]
    assert stats["ear_range"] == 0.0     # max - min of equal floats is exact
    assert stats["face_seen_ratio"] == 1.0


def test_liveness_quality_on_a_blink():
    stats = quality.liveness_quality([0.30, 0.30, 0.10, 0.10, 0.30])
    assert stats["ear_variance"] > 0.0
    assert stats["ear_min"] == 0.10 and stats["ear_max"] == 0.30


def test_liveness_quality_counts_missing_faces():
    stats = quality.liveness_quality([0.3, None, 0.3, None])
    assert stats["n_frames"] == 4.0
    assert stats["n_measured"] == 2.0
    assert stats["face_seen_ratio"] == 0.5


def test_liveness_quality_with_no_face_at_all():
    stats = quality.liveness_quality([None] * 5)
    assert stats["face_seen_ratio"] == 0.0
    assert "ear_variance" not in stats, \
        "no measurement means no statistic, not a fabricated zero"


def test_liveness_quality_on_empty_input():
    stats = quality.liveness_quality([])
    assert stats["n_frames"] == 0.0 and stats["face_seen_ratio"] == 0.0


# ── Observation containers ───────────────────────────────────


def test_face_observation_legacy_tuple_shape():
    obs = scores.FaceObservation(user_id="USR001", confidence=0.88,
                                 face_location=(1, 2, 3, 4))
    assert obs.as_tuple() == ("USR001", 0.88, (1, 2, 3, 4))


def test_face_availability_requires_a_measured_distance():
    assert not scores.FaceObservation().available
    assert not scores.FaceObservation(face_location=(1, 2, 3, 4)).available, \
        "a detected but unscored face has no distance to fuse"
    assert scores.FaceObservation(raw_distance=0.9).available, \
        "a rejected face is still a measurement"


def test_fingerprint_availability_requires_a_score():
    """The case that motivated step 2: a bare yes/no cannot be fused."""
    assert not scores.FingerprintObservation(
        fingerprint_id=3, is_match=True).available
    assert scores.FingerprintObservation(sensor_confidence=145).available
    assert scores.FingerprintObservation(match_score=40).available


def test_fingerprint_zero_score_is_available():
    assert scores.FingerprintObservation(sensor_confidence=0).available, \
        "a measured zero is data; only None means unmeasured"


def test_fingerprint_legacy_tuple_shape():
    obs = scores.FingerprintObservation(fingerprint_id=5, is_match=True)
    assert obs.as_tuple() == (5, True)


def test_liveness_observation_verdict():
    assert scores.LivenessObservation(blink_count=2, required=1).passed
    assert not scores.LivenessObservation(blink_count=0, required=1).passed


# ── The liveness verdict must be unchanged by the recording ──


def _detector():
    from face_recognition_module.liveness_detector import LivenessDetector
    d = LivenessDetector()
    d.reset()
    return d


OPEN, CLOSED = 0.31, 0.10
CONSEC = config.EYE_AR_CONSEC_FRAMES


def test_recording_the_trajectory_does_not_change_blink_counting():
    d = _detector()
    for ear in [OPEN] + [CLOSED] * CONSEC + [OPEN]:
        d.update_blink_state(ear)
    assert d.blink_count == 1, "the blink verdict changed under step 3"


def test_none_still_discards_an_in_progress_blink():
    d = _detector()
    for ear in [OPEN] + [CLOSED] * CONSEC + [None, OPEN]:
        d.update_blink_state(ear)
    assert d.blink_count == 0, "the no-face contract changed under step 3"


def test_trajectory_records_every_frame_including_none():
    d = _detector()
    fed = [OPEN, None, CLOSED, OPEN]
    for ear in fed:
        d.update_blink_state(ear)
    assert d.ear_history == fed


def test_reset_clears_the_trajectory():
    d = _detector()
    d.update_blink_state(OPEN)
    d.reset()
    assert d.ear_history == []


def test_trajectory_is_bounded():
    """A detector reused without reset() must not grow without limit."""
    from face_recognition_module.liveness_detector import LivenessDetector
    d = _detector()
    for _ in range(LivenessDetector._MAX_HISTORY + 250):
        d.update_blink_state(OPEN)
    assert len(d.ear_history) == LivenessDetector._MAX_HISTORY


def test_detector_observation_round_trip():
    d = _detector()
    for ear in [OPEN] + [CLOSED] * CONSEC + [OPEN]:
        d.update_blink_state(ear)
    obs = d.observation()
    assert obs.blink_count == 1
    assert obs.required == config.LIVENESS_BLINK_REQUIRED
    assert obs.quality["ear_variance"] > 0.0
    assert obs.available


# ── Legacy APIs keep their shapes ────────────────────────────


def test_recognizer_legacy_method_returns_a_three_tuple():
    import inspect
    from face_recognition_module.face_recognizer import FaceRecognizer

    # Unloaded recognizer short-circuits before any model is needed.
    recognizer = FaceRecognizer()
    result = recognizer.recognize_from_frame(np.zeros((8, 8, 3), np.uint8))
    assert isinstance(result, tuple) and len(result) == 3, \
        f"ui/atm_interface.py:538 unpacks three values, got {result!r}"
    assert result == (None, 0.0, None)

    assert hasattr(FaceRecognizer, "recognize_from_frame_detailed")
    assert "with_quality" in inspect.signature(
        FaceRecognizer._recognize).parameters


def test_detailed_recognition_returns_an_observation():
    from face_recognition_module.face_recognizer import FaceRecognizer
    obs = FaceRecognizer().recognize_from_frame_detailed(
        np.zeros((8, 8, 3), np.uint8))
    assert isinstance(obs, scores.FaceObservation)
    assert obs.as_tuple() == (None, 0.0, None), \
        "the detailed path must agree with the legacy path"


def test_matcher_exposes_raw_details_and_keeps_its_tuple():
    import inspect
    from fingerprint_module.image_matcher import FingerprintImageMatcher

    matcher = FingerprintImageMatcher()
    assert matcher.last_match_details == {}
    assert hasattr(matcher, "match_detailed")

    signature = inspect.signature(FingerprintImageMatcher.match)
    assert list(signature.parameters) == ["self", "image_path", "threshold"], \
        "match() signature changed; ui/atm_interface.py:649 unpacks 3 values"


def test_unreadable_probe_leaves_details_empty():
    """A failed match must not leave stale measurements from a previous one."""
    from fingerprint_module.image_matcher import FingerprintImageMatcher
    matcher = FingerprintImageMatcher()
    matcher.last_match_details = {"good_matches": 999}
    result = matcher.match("does_not_exist_anywhere.png")
    assert result == (None, False, 0.0)
    assert matcher.last_match_details == {}, \
        "stale details survived a failed match"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"  ok   {fn.__name__}")
    print(f"\nOK - all {len(tests)} plumbing assertions passed.")


if __name__ == "__main__":
    main()
