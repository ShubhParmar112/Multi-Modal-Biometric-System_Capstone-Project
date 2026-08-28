"""Contract checks for the evaluation harness.

pytest isn't installed in this repo, so this runs as a plain script:

    venv/Scripts/python.exe -m tests.test_evaluation

Kept pytest-compatible anyway — assertions live in test_* functions that a
future pytest run would collect, and main() just calls them.

These test the *maths*, not the dataset. Every case uses synthetic score
distributions with a known answer, so they run without the extraction cache and
without any model.

Why this file exists at all: the harness works in *distances* (lower = more
similar) while ROC/AUC conventionally want *similarity* (higher = better). A
direction flip anywhere in that chain does not crash — it silently reports
AUC = 1 - x and an EER on the wrong side of the curve. That class of bug is
invisible without a case whose answer is known in advance.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation import metrics, pairs, protocols


# ── Fixtures: separable synthetic populations ────────────────
# Genuine pairs sit at low distance, impostors at high, with a clean gap
# between 0.3 and 0.5. Every expected value below follows from that geometry.

GENUINE = np.linspace(0.05, 0.30, 200)
IMPOSTOR = np.linspace(0.50, 0.95, 400)


# ── Direction: the bug this file exists to catch ─────────────


def test_auc_is_near_one_for_separable_populations():
    """Genuine closer than impostor must give AUC -> 1, never -> 0."""
    value = metrics.auc(GENUINE, IMPOSTOR)
    assert value > 0.99, f"AUC={value} — distance/similarity direction flipped?"


def test_auc_is_near_zero_when_populations_are_swapped():
    """The complement, pinning the direction from both sides."""
    value = metrics.auc(IMPOSTOR, GENUINE)
    assert value < 0.01, f"AUC={value} — expected the mirror of the above"


def test_far_rises_with_threshold_and_frr_falls():
    """Accepting at `distance <= t`: a looser t admits more of everyone."""
    far_low, far_high = metrics.far_at(IMPOSTOR, 0.4), metrics.far_at(IMPOSTOR, 0.9)
    frr_low, frr_high = metrics.frr_at(GENUINE, 0.4), metrics.frr_at(GENUINE, 0.9)
    assert far_low < far_high, "FAR must increase as the threshold loosens"
    assert frr_low >= frr_high, "FRR must decrease as the threshold loosens"


# ── Known-answer arithmetic ──────────────────────────────────


def test_far_is_zero_inside_the_gap():
    """No impostor sits below 0.50, so a threshold of 0.4 admits none."""
    assert metrics.far_at(IMPOSTOR, 0.4) == 0.0


def test_frr_is_zero_inside_the_gap():
    """Every genuine pair sits below 0.30, so 0.4 rejects none."""
    assert metrics.frr_at(GENUINE, 0.4) == 0.0


def test_far_counts_exactly_half():
    """IMPOSTOR is uniform on [0.50, 0.95]; its midpoint admits ~half."""
    far = metrics.far_at(IMPOSTOR, 0.725)
    assert abs(far - 0.5) < 0.01, f"expected ~0.5, got {far}"


def test_eer_lands_in_the_gap():
    """With a clean separation, FAR and FRR can both be zero — the crossover
    must therefore fall between the two populations."""
    result = metrics.eer(GENUINE, IMPOSTOR)
    assert 0.30 <= result["threshold"] <= 0.50, \
        f"EER threshold {result['threshold']} fell outside the gap"
    assert result["eer"] < 0.01


def test_d_prime_is_positive_and_scales_with_separation():
    near = metrics.d_prime(GENUINE, np.linspace(0.35, 0.80, 400))
    far = metrics.d_prime(GENUINE, np.linspace(0.80, 1.25, 400))
    assert near > 0 and far > near, \
        "d' must grow as the populations move apart"


def test_threshold_at_far_respects_its_budget():
    """The returned threshold must actually deliver at or below the target."""
    for target in (0.0, 0.001, 0.01, 0.10):
        threshold = metrics.threshold_at_far(IMPOSTOR, target)
        achieved = metrics.far_at(IMPOSTOR, threshold)
        assert achieved <= target + 1e-9, \
            f"target FAR {target} -> threshold {threshold} gave {achieved}"


# ── Pair construction ────────────────────────────────────────


def _toy_labels(n_users=3, per_user=4):
    return np.array([f"USR{u:03d}" for u in range(n_users)
                     for _ in range(per_user)])


def test_pair_counts_match_the_combinatorics():
    """3 users x 4 images: 3*C(4,2)=18 genuine, C(12,2)-18=48 impostor."""
    counts = pairs.counts(_toy_labels())
    assert counts["n_genuine_pairs"] == 18, counts
    assert counts["n_impostor_pairs"] == 48, counts


def test_pairs_are_counted_once_and_exclude_self():
    """Upper triangle only — no pair appears twice, no sample pairs itself."""
    labels = _toy_labels()
    genuine, impostor = pairs.pair_masks(labels)
    assert not (genuine & impostor).any(), "a pair cannot be both"
    assert np.trace(genuine) == 0 and np.trace(impostor) == 0, \
        "the diagonal (self-comparison) must be excluded"
    total = len(labels) * (len(labels) - 1) // 2
    assert genuine.sum() + impostor.sum() == total


def test_distance_matrix_is_symmetric_with_zero_diagonal():
    rng = np.random.default_rng(42)
    embeddings = rng.normal(size=(10, 32)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    distances = pairs.distance_matrix(embeddings)
    assert np.allclose(distances, distances.T)
    assert np.allclose(np.diag(distances), 0.0)


# ── The deployed decision rule ───────────────────────────────


def test_decide_rejects_beyond_tolerance():
    distances = np.array([0.9, 0.85])
    labels = np.array(["USR001", "USR001"])
    assert protocols.decide(distances, labels, tolerance=0.4)[0] is None


def test_decide_accepts_a_clear_match():
    distances = np.array([0.05, 0.10, 0.90])
    labels = np.array(["USR001", "USR001", "USR002"])
    predicted, confidence = protocols.decide(distances, labels, tolerance=0.4)
    assert predicted == "USR001"
    assert confidence > 0.9


def test_decide_reproduces_the_blend_arithmetic():
    """0.6*(1-d) + 0.4*vote, exactly as face_recognizer.py:151."""
    distances = np.array([0.20, 0.90])
    labels = np.array(["USR001", "USR002"])
    _predicted, confidence = protocols.decide(distances, labels, tolerance=0.4)
    # one match, so vote_confidence = 1.0 -> 0.6*0.80 + 0.4*1.0 = 0.88
    assert abs(confidence - 0.88) < 1e-6, confidence


def test_blend_has_an_algebraic_floor_of_0_76():
    """The finding behind report_high_risk_floor: a sole-user match that just
    clears the 0.40 gate still lands above the 0.75 high-risk floor."""
    distances = np.array([0.40])          # exactly at the tolerance
    labels = np.array(["USR001"])
    _predicted, confidence = protocols.decide(distances, labels, tolerance=0.40,
                                              min_confidence=0.6)
    assert abs(confidence - 0.76) < 1e-6, confidence
    assert confidence > 0.75, \
        "if this ever fails, the high-risk floor has become reachable"


def test_decide_votes_for_the_majority_user():
    """Three matches for USR001 against one for USR002."""
    distances = np.array([0.30, 0.10, 0.15, 0.20])
    labels = np.array(["USR002", "USR001", "USR001", "USR001"])
    predicted, _confidence = protocols.decide(distances, labels, tolerance=0.4)
    assert predicted == "USR001", "the majority of matching embeddings must win"


def test_min_confidence_floor_can_reject():
    """A floor above the blend's output must turn the match away."""
    distances = np.array([0.35])
    labels = np.array(["USR001"])
    predicted, _c = protocols.decide(distances, labels, tolerance=0.4,
                                     min_confidence=0.99)
    assert predicted is None


def test_empty_gallery_is_a_rejection_not_a_crash():
    predicted, confidence = protocols.decide(np.array([]), np.array([]))
    assert predicted is None and confidence == 0.0


# ── Protocol B end-to-end on synthetic embeddings ────────────


def _clustered_embeddings(n_users=4, per_user=5, spread=0.02, seed=7):
    """Tight per-user clusters on the unit sphere — a trivially easy set where
    the deployed rule should score essentially perfectly."""
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(n_users, 64))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)

    embeddings, labels = [], []
    for u in range(n_users):
        for _ in range(per_user):
            vector = centers[u] + rng.normal(scale=spread, size=64)
            embeddings.append(vector / np.linalg.norm(vector))
            labels.append(f"USR{u:03d}")
    return np.array(embeddings, dtype=np.float32), np.array(labels)


def test_protocol_b_solves_an_easy_set():
    embeddings, labels = _clustered_embeddings()
    result = protocols.protocol_b(embeddings, labels)
    assert result["n_trials"] == len(labels)
    assert result["accuracy"] == 1.0, result
    assert result["far"] == 0.0, "well-separated impostors must all be rejected"


def test_protocol_b_trial_counts_are_conserved():
    """Every trial lands in exactly one genuine bucket and one impostor bucket."""
    embeddings, labels = _clustered_embeddings()
    r = protocols.protocol_b(embeddings, labels)
    assert (r["genuine_correct"] + r["genuine_rejected"] +
            r["genuine_misidentified"]) == r["n_trials"]
    assert (r["impostor_rejected"] + r["impostor_accepted"]) == r["n_trials"]


def test_protocol_b_rejects_mismatched_probe_and_gallery():
    """Guards the alignment trap: comparing caches of different lengths would
    silently pair up different photographs."""
    embeddings, labels = _clustered_embeddings()
    try:
        protocols.protocol_b(embeddings, labels, embeddings[:-1])
    except ValueError:
        return
    raise AssertionError("expected a ValueError on a probe/gallery size mismatch")


def test_high_risk_floor_reports_inert_on_an_easy_set():
    """Tight clusters give confidence ~1.0 everywhere, so nothing reaches the
    0.75 floor — the same shape as the finding on the real data."""
    embeddings, labels = _clustered_embeddings()
    result = protocols.protocol_b(embeddings, labels)
    floor = protocols.report_high_risk_floor(result, 0.75)
    assert floor["n_below_floor"] == 0
    assert floor["inert"] is True


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"  ok   {fn.__name__}")
    print(f"\nOK - all {len(tests)} evaluation assertions passed.")


if __name__ == "__main__":
    main()
