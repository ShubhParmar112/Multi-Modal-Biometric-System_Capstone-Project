"""
Figures for the paper.

Matplotlib with the Agg backend — these run headless and write PNGs; nothing
here opens a window. Each function returns the path it wrote so the caller can
report it.

Styling is deliberately plain: no seaborn, no custom themes, no colour beyond
what distinguishes the series. Figures go into a printed document, where a
grey-on-grey theme costs legibility for nothing.
"""

import os
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

GENUINE_COLOR = "#1f77b4"
IMPOSTOR_COLOR = "#d62728"
MARKER_COLOR = "#2ca02c"


def _save(fig, name: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def score_distributions(genuine: np.ndarray, impostor: np.ndarray,
                        operating_threshold: Optional[float] = None,
                        title: str = "Cosine distance distributions",
                        name: str = "distributions.png") -> str:
    """The headline figure: how far apart the two populations sit.

    Densities rather than counts, because there are ~21x more impostor pairs
    than genuine ones and raw counts would render the genuine peak invisible.
    """
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.linspace(
        float(min(genuine.min(), impostor.min())),
        float(max(genuine.max(), impostor.max())), 80)

    ax.hist(genuine, bins=bins, density=True, alpha=0.65,
            color=GENUINE_COLOR, label=f"Genuine (n={genuine.size:,})")
    ax.hist(impostor, bins=bins, density=True, alpha=0.65,
            color=IMPOSTOR_COLOR, label=f"Impostor (n={impostor.size:,})")

    if operating_threshold is not None:
        ax.axvline(operating_threshold, color=MARKER_COLOR, linestyle="--",
                   linewidth=1.8,
                   label=f"Operating threshold ({operating_threshold:.2f})")

    ax.set_xlabel("Cosine distance  (lower = more similar)")
    ax.set_ylabel("Density")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.25)
    return _save(fig, name)


def roc_curve(genuine: np.ndarray, impostor: np.ndarray,
              operating_threshold: Optional[float] = None,
              title: str = "ROC", name: str = "roc.png") -> str:
    """ROC on log-x, because the interesting region is FAR < 1%."""
    from evaluation import metrics
    curve = metrics.sweep(genuine, impostor, n_points=2000)
    far, tpr = curve["far"], 1.0 - curve["frr"]

    fig, ax = plt.subplots(figsize=(6, 5.5))
    ax.plot(far, tpr, color=GENUINE_COLOR, linewidth=1.8)

    if operating_threshold is not None:
        op_far = metrics.far_at(impostor, operating_threshold)
        op_tpr = 1.0 - metrics.frr_at(genuine, operating_threshold)
        ax.plot(op_far, op_tpr, "o", color=MARKER_COLOR, markersize=9,
                label=f"Operating point ({operating_threshold:.2f})\n"
                      f"FAR={op_far:.4%}, TPR={op_tpr:.2%}")
        ax.legend(loc="lower right")

    ax.set_xscale("symlog", linthresh=1e-5)
    ax.set_xlabel("False accept rate")
    ax.set_ylabel("True positive rate")
    ax.set_title(title)
    ax.grid(alpha=0.25, which="both")
    return _save(fig, name)


def far_frr_sweep(genuine: np.ndarray, impostor: np.ndarray,
                  operating_threshold: Optional[float] = None,
                  eer_point: Optional[Dict] = None,
                  title: str = "FAR / FRR vs threshold",
                  name: str = "far_frr_sweep.png") -> str:
    """The figure that justifies the threshold choice."""
    from evaluation import metrics
    curve = metrics.sweep(genuine, impostor, n_points=2000)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(curve["thresholds"], curve["far"], color=IMPOSTOR_COLOR,
            linewidth=1.8, label="FAR (impostors admitted)")
    ax.plot(curve["thresholds"], curve["frr"], color=GENUINE_COLOR,
            linewidth=1.8, label="FRR (genuine turned away)")

    if operating_threshold is not None:
        ax.axvline(operating_threshold, color=MARKER_COLOR, linestyle="--",
                   linewidth=1.8,
                   label=f"Current threshold ({operating_threshold:.2f})")
    if eer_point is not None:
        ax.plot(eer_point["threshold"], eer_point["eer"], "s", color="#9467bd",
                markersize=8,
                label=f"EER = {eer_point['eer']:.4%} "
                      f"@ {eer_point['threshold']:.3f}")

    ax.set_xlabel("Cosine distance threshold")
    ax.set_ylabel("Error rate")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.25)
    return _save(fig, name)


def tolerance_sweep(rows: List[Dict], current: Optional[float] = None,
                    title: str = "Protocol B: deployed rule vs tolerance",
                    name: str = "tolerance_sweep.png") -> str:
    """System-level errors as the tolerance moves — including the
    mis-identification rate, which the pairwise view cannot show."""
    tolerances = [r["tolerance"] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(tolerances, [r["frr"] for r in rows], color=GENUINE_COLOR,
            linewidth=1.8, label="FRR (genuine rejected)")
    ax.plot(tolerances, [r["far"] for r in rows], color=IMPOSTOR_COLOR,
            linewidth=1.8, label="FAR (impostor accepted)")
    ax.plot(tolerances, [r["misidentification_rate"] for r in rows],
            color="#ff7f0e", linewidth=1.8, linestyle=":",
            label="Mis-identified as another enrolled user")

    if current is not None:
        ax.axvline(current, color=MARKER_COLOR, linestyle="--", linewidth=1.8,
                   label=f"Current ({current:.2f})")

    ax.set_xlabel("FACE_RECOGNITION_TOLERANCE")
    ax.set_ylabel("Rate")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.25)
    return _save(fig, name)


def confidence_histogram(accepted: np.ndarray, floor: float,
                         title: str = "Confidence of genuine acceptances",
                         name: str = "confidence_floor.png") -> str:
    """Where accepted genuine trials land relative to the high-risk floor.

    If the whole mass sits above the floor, the high-risk 'stricter check'
    never fires — which is the claim report_high_risk_floor() tests.
    """
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(accepted, bins=60, color=GENUINE_COLOR, alpha=0.75,
            label=f"Genuine acceptances (n={accepted.size:,})")
    ax.axvline(floor, color=IMPOSTOR_COLOR, linestyle="--", linewidth=2,
               label=f"RISK_HIGH_FACE_MIN_CONFIDENCE ({floor:.2f})")
    ax.set_xlabel("Reported confidence (blended)")
    ax.set_ylabel("Count")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.25)
    return _save(fig, name)


def det_size_comparison(results: Dict[str, Dict],
                        title: str = "Detector input size: accuracy trade-off",
                        name: str = "det_size_comparison.png") -> str:
    """Bar comparison across detector sizes.

    `results` maps a label to a Protocol B result dict.
    """
    labels = list(results.keys())
    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(x - width, [results[k]["frr"] for k in labels], width,
           color=GENUINE_COLOR, label="FRR")
    ax.bar(x, [results[k]["far"] for k in labels], width,
           color=IMPOSTOR_COLOR, label="FAR")
    ax.bar(x + width, [results[k]["misidentification_rate"] for k in labels],
           width, color="#ff7f0e", label="Mis-identification")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Rate")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    return _save(fig, name)
