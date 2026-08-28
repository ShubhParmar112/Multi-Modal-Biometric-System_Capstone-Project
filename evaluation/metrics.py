"""
Verification metrics: FAR/FRR sweeps, EER, AUC, d'.

All functions take *distances* (lower = more similar), matching the convention
in pairs.py and in face_recognizer.py, and handle the direction flip internally
where a metric needs similarity. Getting that backwards silently produces an
AUC of 1-x instead of x, so the direction is fixed in one place here rather
than at each call site.

Operating-point semantics follow the deployed rule in
face_recognizer.py:137 — a probe is accepted when

    distance <= threshold

so FAR(t) is the fraction of impostor pairs at or below t, and FRR(t) is the
fraction of genuine pairs above t. Both are therefore step functions evaluated
on the empirical distributions; no parametric fit is assumed anywhere.
"""

from typing import Dict, Optional

import numpy as np


def far_at(impostor_distances: np.ndarray, threshold: float) -> float:
    """False accept rate: impostors that would be admitted at this threshold."""
    if impostor_distances.size == 0:
        return float("nan")
    return float((impostor_distances <= threshold).mean())


def frr_at(genuine_distances: np.ndarray, threshold: float) -> float:
    """False reject rate: genuine users that would be turned away."""
    if genuine_distances.size == 0:
        return float("nan")
    return float((genuine_distances > threshold).mean())


def sweep(genuine: np.ndarray, impostor: np.ndarray,
          n_points: int = 1000) -> Dict[str, np.ndarray]:
    """FAR and FRR across the full threshold range.

    Thresholds span the combined observed range so both curves are complete
    (FAR from 0 to 1, FRR from 1 to 0) rather than clipped to whichever
    population happens to be narrower.
    """
    lo = float(min(genuine.min(), impostor.min()))
    hi = float(max(genuine.max(), impostor.max()))
    thresholds = np.linspace(lo, hi, n_points)

    # Vectorised: (n_points, n_pairs) comparisons via broadcasting.
    far = (impostor[None, :] <= thresholds[:, None]).mean(axis=1)
    frr = (genuine[None, :] > thresholds[:, None]).mean(axis=1)
    return {"thresholds": thresholds, "far": far, "frr": frr}


def eer(genuine: np.ndarray, impostor: np.ndarray,
        n_points: int = 10000) -> Dict[str, float]:
    """Equal error rate — where FAR and FRR cross.

    Both curves are step functions on finite samples, so an exact crossing
    generally does not exist. The convention used here is the threshold
    minimising |FAR - FRR|, with the EER reported as their mean at that point.
    """
    curve = sweep(genuine, impostor, n_points)
    gap = np.abs(curve["far"] - curve["frr"])
    i = int(np.argmin(gap))
    return {
        "eer": float((curve["far"][i] + curve["frr"][i]) / 2.0),
        "threshold": float(curve["thresholds"][i]),
        "far": float(curve["far"][i]),
        "frr": float(curve["frr"][i]),
    }


def auc(genuine: np.ndarray, impostor: np.ndarray) -> float:
    """Area under the ROC curve.

    Computed as the probability that a random genuine pair scores more similar
    than a random impostor pair — the Mann-Whitney form of AUC. This avoids any
    dependence on threshold sampling density, so it does not drift with
    n_points the way a trapezoid over a swept curve would.
    """
    from sklearn.metrics import roc_auc_score
    # Flip to similarity so that "higher = more genuine" holds for the scorer.
    scores = np.concatenate([1.0 - genuine, 1.0 - impostor])
    truth = np.concatenate([np.ones(genuine.size), np.zeros(impostor.size)])
    return float(roc_auc_score(truth, scores))


def d_prime(genuine: np.ndarray, impostor: np.ndarray) -> float:
    """Separation between the two distributions, in pooled standard deviations.

    d' = |mu_i - mu_g| / sqrt((var_g + var_i) / 2)

    Unlike AUC this is unbounded, which makes it the more useful quantity for
    setting fusion weights in step 4: a modality that separates twice as well
    should carry more weight, and d' says by how much.
    """
    var = (genuine.var() + impostor.var()) / 2.0
    if var <= 0:
        return float("nan")
    return float(abs(impostor.mean() - genuine.mean()) / np.sqrt(var))


def threshold_at_far(impostor: np.ndarray, target_far: float) -> float:
    """Largest threshold whose FAR stays at or below the target.

    This is how step 4 will compare fusion strategies at a matched operating
    point: pick the threshold each strategy needs to hit the same FAR, then
    compare their FRRs. Comparing at different FARs would be meaningless.

    Returns the smallest observed distance minus a hair when no threshold
    achieves the target (i.e. the target FAR is below this sample's resolution),
    so the caller gets a usable, conservative value rather than a NaN.
    """
    ordered = np.sort(impostor)
    # Number of impostors we may admit while staying within target_far.
    budget = int(np.floor(target_far * ordered.size))
    if budget <= 0:
        return float(ordered[0]) - 1e-9
    return float(ordered[budget - 1])


def rule_of_three(n_trials: int) -> float:
    """95% upper confidence bound on a rate when zero events were observed.

    Observing no false accepts in n trials does not mean the rate is zero — it
    means it is below roughly 3/n with 95% confidence. Reporting a bare "FAR =
    0%" invites exactly the criticism the fraud module's F1 = 1.0 attracts, so
    every zero in this harness is published with its bound attached.

    The approximation comes from solving (1-p)^n = 0.05, giving p ~ 3/n for
    reasonably large n. Standard practice in biometric evaluation.
    """
    if n_trials <= 0:
        return float("nan")
    return 3.0 / n_trials


def summarize(genuine: np.ndarray, impostor: np.ndarray,
              operating_threshold: Optional[float] = None) -> Dict[str, float]:
    """Everything the report needs about one modality, in one call."""
    result = {
        "n_genuine": int(genuine.size),
        "n_impostor": int(impostor.size),
        "genuine_mean": float(genuine.mean()),
        "genuine_std": float(genuine.std()),
        "impostor_mean": float(impostor.mean()),
        "impostor_std": float(impostor.std()),
        "auc": auc(genuine, impostor),
        "d_prime": d_prime(genuine, impostor),
    }
    result.update({f"eer_{k}": v for k, v in eer(genuine, impostor).items()})

    if operating_threshold is not None:
        result["operating_threshold"] = float(operating_threshold)
        result["operating_far"] = far_at(impostor, operating_threshold)
        result["operating_frr"] = frr_at(genuine, operating_threshold)
    return result
