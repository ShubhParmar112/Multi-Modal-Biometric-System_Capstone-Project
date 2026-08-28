"""
Per-sample quality measurements.

Quality is the input to the *adaptive* half of quality-adaptive fusion: a
blurry face in a dark vestibule should not carry the same weight as a sharp,
well-lit one, and when the face sample is poor the fingerprint should carry
more of the decision.

This module is the single implementation of those measurements. The offline
harness (evaluation/extract.py) imports it rather than keeping its own copy, so
the numbers step 4 fuses on are exactly the numbers step 1 measured. Two
"equivalent" implementations that drift apart would invalidate the comparison
silently.

Raw measurements only — no 0-1 quality scalar here. Collapsing these into a
single weight needs calibration constants derived from the measured
distributions, which is a step-4 concern. Keeping the raw values means the
calibration can change without re-measuring.

All functions are pure: no I/O, no config reads, deterministic for a given
input.
"""

from typing import Dict, Optional, Sequence

import cv2
import numpy as np


# ── Face ─────────────────────────────────────────────────────


def crop_to_bbox(image: np.ndarray, bbox: Sequence[float]) -> Optional[np.ndarray]:
    """Clamp a detector bbox to the image bounds and return that crop.

    Detector boxes routinely extend past the frame edge when a subject is close
    to the camera, and numpy silently accepts out-of-range slices by truncating
    — which would measure a different region than intended. Returns None when
    the clamped box is empty.
    """
    height, width = image.shape[:2]
    x1, y1, x2, y2 = (int(round(float(v))) for v in bbox)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def face_quality(image: np.ndarray, bbox: Sequence[float],
                 det_score: Optional[float] = None) -> Dict[str, float]:
    """Sharpness, exposure and scale of a detected face.

    Measured on the face crop, not the whole frame: a sharp face against a
    blurry background is a good sample, and whole-frame statistics would score
    it as a bad one.

    Returns:
        blur_var   variance of the Laplacian — the standard focus measure.
                   Low means few edges, i.e. a soft or out-of-focus face.
        luma_mean  mean brightness. A dim vestibule drives this down.
        luma_std   brightness spread. Backlighting drives this up.
        bbox_area  face area in pixels — a proxy for subject distance.
        det_score  the detector's own confidence, passed through when known.

    A bbox that does not intersect the image yields zeros rather than raising:
    an unmeasurable sample is a low-quality sample, and the caller decides what
    to do about it.
    """
    face = crop_to_bbox(image, bbox)
    metrics: Dict[str, float] = {
        "blur_var": 0.0,
        "luma_mean": 0.0,
        "luma_std": 0.0,
        "bbox_area": 0.0,
    }
    if det_score is not None:
        metrics["det_score"] = float(det_score)

    if face is None or face.size == 0:
        return metrics

    gray = (cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
            if face.ndim == 3 else face)

    metrics["blur_var"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    metrics["luma_mean"] = float(gray.mean())
    metrics["luma_std"] = float(gray.std())
    metrics["bbox_area"] = float(gray.shape[0] * gray.shape[1])
    return metrics


# ── Fingerprint ──────────────────────────────────────────────


def fingerprint_quality(keypoint_count: Optional[int] = None,
                        sensor_confidence: Optional[int] = None
                        ) -> Dict[str, float]:
    """Quality signals available from the two fingerprint paths.

    keypoint_count comes from the software SIFT matcher: too few features means
    a smudged, partial or low-contrast print, regardless of how well it scored.

    sensor_confidence is the R307S's own match score (see step 2). The hardware
    exposes no separate quality measure — only a score — so on that path score
    and quality are the same number. That limitation is worth stating in the
    paper rather than papering over.

    Absent inputs are simply omitted, never defaulted to 0: "not measured" and
    "measured as bad" must stay distinguishable.
    """
    metrics: Dict[str, float] = {}
    if keypoint_count is not None:
        metrics["keypoint_count"] = float(keypoint_count)
    if sensor_confidence is not None:
        metrics["sensor_confidence"] = float(sensor_confidence)
    return metrics


# ── Liveness ─────────────────────────────────────────────────


def liveness_quality(ear_history: Sequence[Optional[float]]) -> Dict[str, float]:
    """Descriptive statistics over an eye-aspect-ratio trajectory.

    Liveness remains a veto, not a fused term (see the package docstring), so
    these do not feed a weighted sum. They serve two other purposes: describing
    how confidently liveness was established, and modulating *face* quality —
    a burst where the face was visible in only a third of frames is a poor
    basis for recognition regardless of whether a blink was seen.

    ear_variance is the discriminative one. A still photograph produces a
    perfectly constant EAR (measured spread 0.0 over 15 frames, see
    tests/test_liveness.py), so near-zero variance across a burst is itself
    evidence of a static presentation.

    None entries mean "no face in that frame" and are excluded from the
    statistics but counted in face_seen_ratio.
    """
    total = len(ear_history)
    measured = [e for e in ear_history if e is not None]

    if not measured:
        return {
            "n_frames": float(total),
            "n_measured": 0.0,
            "face_seen_ratio": 0.0,
        }

    values = np.asarray(measured, dtype=float)
    return {
        "n_frames": float(total),
        "n_measured": float(values.size),
        "face_seen_ratio": float(values.size / total) if total else 0.0,
        "ear_min": float(values.min()),
        "ear_max": float(values.max()),
        "ear_mean": float(values.mean()),
        "ear_variance": float(values.var()),
        "ear_range": float(values.max() - values.min()),
    }
