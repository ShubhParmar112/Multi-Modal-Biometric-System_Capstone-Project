"""
Two evaluation protocols, measuring deliberately different things.

Protocol A — pairwise (1:1 verification)
    Every image against every other. Measures the ArcFace *embedding* and is
    directly comparable to published face-verification numbers. It says nothing
    about the thresholds, voting, or confidence blending this project layers on
    top of the model.

Protocol B — leave-one-image-out (open-set identification, the deployed rule)
    Reproduces face_recognizer.recognize_from_frame() exactly: minimum cosine
    distance, the tolerance gate, the vote across matching gallery embeddings,
    the 0.6/0.4 confidence blend, and the MIN_FACE_CONFIDENCE floor. Measures
    *this system*, not the model.

Protocol B is the one that makes the project's own thresholds testable, so its
decision function is parameterised rather than reading config directly. That
lets face_eval.py sweep the values instead of asserting them:

  - FACE_RECOGNITION_TOLERANCE (0.40)
  - MIN_FACE_CONFIDENCE (0.6), which face_recognizer.py uses for two unrelated
    jobs — a det_score floor at line 112 and a fused-confidence floor at 155
  - the 0.6 / 0.4 blend weights at line 151, which have no stated derivation
  - RISK_HIGH_FACE_MIN_CONFIDENCE (0.75), which arithmetic suggests may be
    unreachable-to-fail; report_high_risk_floor() measures whether it is

Trial construction:
    genuine  — probe i, gallery = every sample except i
               (the probe's own user keeps 19 of its 20 enrolled images)
    impostor — probe i, gallery = every sample whose user is not the probe's
               (an open-set trial: the correct answer is "reject")

With 420 samples that is 420 genuine and 420 impostor trials.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from evaluation import metrics, pairs

# Defaults mirror config.py at the time of writing. Passed explicitly rather
# than read from config inside the decision function, so sweeps are possible.
DEFAULT_TOLERANCE = 0.40
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_BLEND_DISTANCE = 0.6
DEFAULT_BLEND_VOTE = 0.4


# ── Protocol A ───────────────────────────────────────────────


def protocol_a(embeddings: np.ndarray, labels: np.ndarray,
               operating_threshold: float = DEFAULT_TOLERANCE) -> Dict:
    """Pairwise verification over all image pairs."""
    genuine, impostor = pairs.genuine_impostor_distances(embeddings, labels)
    summary = metrics.summarize(genuine, impostor, operating_threshold)
    summary.update(pairs.counts(labels))
    return {"summary": summary, "genuine": genuine, "impostor": impostor}


# ── Protocol B: the deployed decision rule ───────────────────


def decide(distances: np.ndarray, gallery_labels: np.ndarray,
           tolerance: float = DEFAULT_TOLERANCE,
           min_confidence: float = DEFAULT_MIN_CONFIDENCE,
           blend_distance: float = DEFAULT_BLEND_DISTANCE,
           blend_vote: float = DEFAULT_BLEND_VOTE
           ) -> Tuple[Optional[str], float]:
    """One recognition decision, faithful to face_recognizer.py:132-162.

    Args:
        distances: cosine distance from the probe to every gallery embedding.
        gallery_labels: user id per gallery embedding, aligned with distances.

    Returns:
        (user_id or None, reported confidence)

    The tie-break in the vote follows the original: max() over a dict returns
    the first key inserted at the winning count, and insertion order follows
    gallery order. Replicated here by iterating in the same order.
    """
    if distances.size == 0:
        return None, 0.0

    best_idx = int(np.argmin(distances))
    best_distance = float(distances[best_idx])
    confidence = round(1.0 - best_distance, 4)

    if best_distance > tolerance:
        return None, confidence

    matches = distances <= tolerance
    match_counts: Dict[str, int] = {}
    for matched, uid in zip(matches, gallery_labels):
        if matched:
            match_counts[uid] = match_counts.get(uid, 0) + 1

    if not match_counts:
        # Unreachable in practice (best_distance <= tolerance guarantees at
        # least one match), but the original has this branch, so keep it.
        return gallery_labels[best_idx], confidence

    voted_id = max(match_counts, key=match_counts.get)
    vote_confidence = match_counts[voted_id] / sum(match_counts.values())
    final_confidence = round(confidence * blend_distance +
                             vote_confidence * blend_vote, 4)

    if final_confidence < min_confidence:
        return None, final_confidence
    return voted_id, final_confidence


def protocol_b(gallery_embeddings: np.ndarray, labels: np.ndarray,
               probe_embeddings: Optional[np.ndarray] = None,
               **rule) -> Dict:
    """Leave-one-image-out open-set identification.

    Args:
        gallery_embeddings: the enrolled side (extracted at det_size 640,
            matching how face_encoder.py builds the real gallery).
        labels: user id per sample, shared by gallery and probes.
        probe_embeddings: the probe side. Defaults to the gallery, which
            measures the rule in isolation. Pass the det_size-320 extraction to
            reproduce the deployed asymmetry, where live probes are detected at
            a smaller input size than the enrolled gallery.
        **rule: threshold overrides forwarded to decide().

    Returns per-trial outcomes plus counts. Genuine errors are split into
    rejections and mis-identifications: being turned away is an availability
    failure, but being recognised as *a different enrolled user* is a security
    failure, and averaging them into one "error rate" hides that.
    """
    probes = gallery_embeddings if probe_embeddings is None else probe_embeddings
    if probes.shape[0] != gallery_embeddings.shape[0]:
        raise ValueError(
            f"probe/gallery sample count mismatch: {probes.shape[0]} vs "
            f"{gallery_embeddings.shape[0]} — both extractions must cover the "
            f"same images")

    n = gallery_embeddings.shape[0]
    all_distances = 1.0 - (probes @ gallery_embeddings.T)   # (n_probe, n_gal)

    genuine_correct = 0
    genuine_rejected = 0
    genuine_misidentified = 0
    impostor_rejected = 0
    impostor_accepted = 0

    genuine_confidences: List[float] = []
    genuine_accept_confidences: List[float] = []
    impostor_accept_confidences: List[float] = []
    misidentified_trials: List[Tuple[int, str, str]] = []

    for i in range(n):
        true_id = labels[i]
        row = all_distances[i]

        # ── genuine trial: gallery keeps every sample but this one ──
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        predicted, confidence = decide(row[keep], labels[keep], **rule)
        genuine_confidences.append(confidence)

        if predicted == true_id:
            genuine_correct += 1
            genuine_accept_confidences.append(confidence)
        elif predicted is None:
            genuine_rejected += 1
        else:
            genuine_misidentified += 1
            misidentified_trials.append((i, true_id, predicted))

        # ── impostor trial: this user is absent from the gallery ──
        others = labels != true_id
        predicted, confidence = decide(row[others], labels[others], **rule)
        if predicted is None:
            impostor_rejected += 1
        else:
            impostor_accepted += 1
            impostor_accept_confidences.append(confidence)

    return {
        "n_trials": n,
        "genuine_correct": genuine_correct,
        "genuine_rejected": genuine_rejected,
        "genuine_misidentified": genuine_misidentified,
        "impostor_rejected": impostor_rejected,
        "impostor_accepted": impostor_accepted,
        "frr": genuine_rejected / n,
        "far": impostor_accepted / n,
        "misidentification_rate": genuine_misidentified / n,
        "accuracy": genuine_correct / n,
        "genuine_confidences": np.array(genuine_confidences),
        "genuine_accept_confidences": np.array(genuine_accept_confidences),
        "impostor_accept_confidences": np.array(impostor_accept_confidences),
        "misidentified_trials": misidentified_trials,
    }


# ── Targeted questions about the deployed thresholds ─────────


def report_high_risk_floor(result: Dict, floor: float = 0.75) -> Dict:
    """Does RISK_HIGH_FACE_MIN_CONFIDENCE actually reject anything?

    webapp/backend/auth.py:358 rejects a high-risk step-up when the reported
    confidence falls below this floor. But the confidence it tests is the
    blended value, and the blend has an algebraic floor of its own: clearing
    the 0.40 tolerance gate forces confidence >= 0.60, and a probe matching
    only its own user's embeddings gives vote_confidence = 1.0, so

        final >= 0.6 * 0.60 + 0.4 * 1.0 = 0.76 > 0.75

    If that holds for every genuine acceptance in practice, the "stricter check
    for high-risk sessions" cannot reject a legitimate user, and the control is
    inert rather than strict.

    Returns the measured fraction of genuine acceptances that fall below the
    floor — the rate at which the control does anything at all.
    """
    accepted = result["genuine_accept_confidences"]
    if accepted.size == 0:
        return {"floor": floor, "n_accepted": 0, "n_below_floor": 0,
                "fraction_below_floor": float("nan"), "min_confidence": float("nan")}

    below = int((accepted < floor).sum())
    return {
        "floor": floor,
        "n_accepted": int(accepted.size),
        "n_below_floor": below,
        "fraction_below_floor": below / accepted.size,
        "min_confidence": float(accepted.min()),
        "inert": below == 0,
    }


def sweep_tolerance(gallery: np.ndarray, labels: np.ndarray,
                    tolerances, probe: Optional[np.ndarray] = None,
                    **rule) -> List[Dict]:
    """Protocol B repeated across tolerance values, for the operating-point
    figure. This is what justifies FACE_RECOGNITION_TOLERANCE empirically
    instead of inheriting it."""
    rows = []
    for tolerance in tolerances:
        result = protocol_b(gallery, labels, probe, tolerance=tolerance, **rule)
        rows.append({
            "tolerance": float(tolerance),
            "frr": result["frr"],
            "far": result["far"],
            "misidentification_rate": result["misidentification_rate"],
            "accuracy": result["accuracy"],
        })
    return rows


def sweep_blend(gallery: np.ndarray, labels: np.ndarray,
                weights, probe: Optional[np.ndarray] = None,
                **rule) -> List[Dict]:
    """Protocol B across blend weights, testing whether 0.6/0.4 is justified.

    `weights` is an iterable of distance-weights; the vote weight is its
    complement, matching the original's implicit constraint that they sum to 1.
    """
    rows = []
    for w_distance in weights:
        result = protocol_b(gallery, labels, probe,
                            blend_distance=float(w_distance),
                            blend_vote=float(1.0 - w_distance), **rule)
        rows.append({
            "blend_distance": float(w_distance),
            "blend_vote": float(1.0 - w_distance),
            "frr": result["frr"],
            "far": result["far"],
            "accuracy": result["accuracy"],
        })
    return rows
