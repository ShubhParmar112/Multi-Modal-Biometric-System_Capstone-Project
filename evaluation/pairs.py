"""
Genuine / impostor pair construction over the extracted sample set.

Implemented as masks over the full N x N cosine-distance matrix rather than as
explicit pair lists. With N=420 the matrix is 176,400 floats — trivial to hold
in memory — and masking is both faster and far less error-prone than building
~88,000 index tuples by hand.

Distance convention throughout the harness:
    distance   = 1 - cosine_similarity   (0 = identical, higher = less alike)
    similarity = 1 - distance            (used for ROC, higher = more genuine)

Embeddings are L2-normalised by ArcFace, so a plain dot product is already the
cosine similarity. Nothing here re-normalises.
"""

from typing import List, Tuple

import numpy as np


def distance_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Full pairwise cosine-distance matrix, shape (N, N).

    The diagonal is forced to exactly 0.0: floating-point error otherwise
    leaves self-comparisons at ~1e-8 rather than 0, which is harmless for
    analysis but confusing to read in a dump.
    """
    similarities = embeddings @ embeddings.T
    distances = 1.0 - similarities
    np.fill_diagonal(distances, 0.0)
    return distances


def label_array(rows: List[dict]) -> np.ndarray:
    """User id per sample, aligned with the embedding matrix rows."""
    return np.array([r["user_id"] for r in rows])


def pair_masks(labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Upper-triangular genuine and impostor masks.

    Only the upper triangle is used, so each unordered pair is counted once and
    self-comparisons are excluded. For the enrolled set (21 users x 20 images)
    this yields 3,990 genuine and 84,000 impostor pairs.
    """
    same_user = labels[:, None] == labels[None, :]
    upper = np.triu(np.ones(same_user.shape, dtype=bool), k=1)
    return same_user & upper, (~same_user) & upper


def genuine_impostor_distances(
        embeddings: np.ndarray,
        labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """The two distance populations that every downstream metric consumes."""
    distances = distance_matrix(embeddings)
    genuine_mask, impostor_mask = pair_masks(labels)
    return distances[genuine_mask], distances[impostor_mask]


def counts(labels: np.ndarray) -> dict:
    """Sample and pair counts, for reporting the evaluation's scale."""
    genuine_mask, impostor_mask = pair_masks(labels)
    return {
        "n_samples": int(labels.size),
        "n_users": int(len(set(labels.tolist()))),
        "n_genuine_pairs": int(genuine_mask.sum()),
        "n_impostor_pairs": int(impostor_mask.sum()),
    }
