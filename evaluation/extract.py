"""
Extraction pass: dataset images -> cached embeddings + per-sample quality.

This is the slow half of the harness, separated from the analysis so that
iterating on metrics does not mean re-running the models. Roughly two minutes
per detector size on CPU; every later module reads the cache and runs in
seconds.

Why re-run the model when encodings/face_encodings.pkl already holds 420
embeddings: that pickle records only (embedding, user_id) pairs. It has no
filename, no detection score, and no image-quality measurements, so it cannot
support quality-weighted fusion or per-image error analysis. Re-extracting also
independently verifies the enrolled pickle — see verify_against_pickle().

Detector size matters and is captured deliberately. Enrollment encodes at
det_size 640 (face_encoder.py) while live recognition runs at 320
(config.FACE_DET_SIZE), so the deployed system compares a 320-probe against a
640-gallery. Extracting at both sizes lets Protocol B reproduce that asymmetry
instead of quietly assuming it away.

Reads dataset/ only. Writes only into evaluation/output/.
"""

import argparse
import csv
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.logger import logger

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Detector input sizes to extract at.
#   640 — what face_encoder.py uses at enrollment (the gallery)
#   320 — config.FACE_DET_SIZE, what face_recognizer.py uses live (the probe)
DET_SIZES = (640, 320)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")

CSV_COLUMNS = [
    "user_id", "filename", "det_score", "bbox_area", "bbox_w", "bbox_h",
    "blur_var", "luma_mean", "luma_std", "ear",
]


def samples_csv(det_size: int) -> str:
    return os.path.join(OUTPUT_DIR, f"face_samples_det{det_size}.csv")


def embeddings_npy(det_size: int) -> str:
    return os.path.join(OUTPUT_DIR, f"face_embeddings_det{det_size}.npy")


# ── Quality metrics ──────────────────────────────────────────
# Deliberately NOT reimplemented here. auth/fusion/quality.py is the single
# implementation, so the metrics step 4 fuses on are exactly the ones measured
# in step 1. Two "equivalent" copies would drift apart silently and invalidate
# the comparison.
#
# Note the import direction: the offline harness depends on the shared module,
# never the reverse. Nothing on the live authentication path imports
# `evaluation` — a smoke check enforces that.
from auth.fusion.quality import face_quality


# ── Extraction ───────────────────────────────────────────────


def _build_app(det_size: int):
    """InsightFace pipeline, configured exactly as the runtime builds it."""
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(det_size, det_size))
    return app


def _list_samples() -> List[Tuple[str, str]]:
    """Every (user_id, image_path) in the dataset, in a stable order."""
    samples: List[Tuple[str, str]] = []
    if not os.path.isdir(config.DATASET_DIR):
        return samples
    for user_id in sorted(os.listdir(config.DATASET_DIR)):
        user_dir = os.path.join(config.DATASET_DIR, user_id)
        if not os.path.isdir(user_dir):
            continue
        for name in sorted(os.listdir(user_dir)):
            if name.lower().endswith(IMAGE_EXTS):
                samples.append((user_id, os.path.join(user_dir, name)))
    return samples


def extract(det_size: int, with_ear: bool = True) -> Tuple[int, int]:
    """Run the models over the dataset and cache the results.

    Returns (n_extracted, n_skipped). Images where no face is detected are
    skipped and reported rather than silently dropped — a user whose images
    fail here would otherwise appear to have a smaller gallery for no visible
    reason.
    """
    samples = _list_samples()
    if not samples:
        logger.error(f"No images found under {config.DATASET_DIR}")
        return 0, 0

    logger.info(f"Extracting {len(samples)} images at det_size={det_size}")
    app = _build_app(det_size)

    detector = None
    if with_ear:
        from face_recognition_module.liveness_detector import LivenessDetector
        detector = LivenessDetector()

    rows: List[Dict[str, object]] = []
    embeddings: List[np.ndarray] = []
    skipped: List[str] = []
    started = time.time()

    for idx, (user_id, path) in enumerate(samples, 1):
        image = cv2.imread(path)
        if image is None:
            skipped.append(f"{path} (unreadable)")
            continue

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        faces = app.get(rgb)
        if not faces:
            skipped.append(f"{path} (no face)")
            continue

        # Largest face, matching what both the encoder and recognizer do.
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) *
                                        (f.bbox[3] - f.bbox[1]))
        x1, y1, x2, y2 = face.bbox
        quality = face_quality(image, face.bbox)

        ear = ""
        if detector is not None:
            measured, _closed, _display = detector.check_frame_liveness(image)
            ear = "" if measured is None else round(float(measured), 5)

        rows.append({
            "user_id": user_id,
            "filename": os.path.basename(path),
            "det_score": round(float(face.det_score), 5),
            "bbox_area": round(float((x2 - x1) * (y2 - y1)), 1),
            "bbox_w": round(float(x2 - x1), 1),
            "bbox_h": round(float(y2 - y1), 1),
            "blur_var": round(quality["blur_var"], 3),
            "luma_mean": round(quality["luma_mean"], 3),
            "luma_std": round(quality["luma_std"], 3),
            "ear": ear,
        })
        embeddings.append(np.asarray(face.normed_embedding, dtype=np.float32))

        if idx % 50 == 0:
            logger.info(f"  {idx}/{len(samples)} "
                        f"({time.time() - started:.0f}s elapsed)")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(samples_csv(det_size), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    np.save(embeddings_npy(det_size), np.vstack(embeddings))

    logger.success(
        f"det_size={det_size}: {len(rows)} extracted, {len(skipped)} skipped "
        f"in {time.time() - started:.0f}s -> "
        f"{os.path.basename(samples_csv(det_size))}"
    )
    for note in skipped:
        logger.warning(f"  skipped: {note}")

    return len(rows), len(skipped)


# ── Loading + verification ───────────────────────────────────


def load(det_size: int) -> Tuple[List[Dict[str, str]], np.ndarray]:
    """Read a cached extraction back. Raises if it hasn't been run yet."""
    csv_path, npy_path = samples_csv(det_size), embeddings_npy(det_size)
    if not (os.path.exists(csv_path) and os.path.exists(npy_path)):
        raise FileNotFoundError(
            f"No cached extraction for det_size={det_size}. Run:\n"
            f"    venv/Scripts/python.exe -m evaluation.extract"
        )
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows, np.load(npy_path)


def verify_against_pickle(det_size: int = 640) -> Optional[float]:
    """Cross-check the freshly extracted embeddings against the enrolled ones.

    The enrolled pickle has no filenames, so this compares per-user sets rather
    than per-image: for each user, the mean cosine similarity between their
    extracted embeddings and their enrolled ones. Values near 1.0 mean the
    extraction reproduces enrollment. A low value would mean the harness is
    measuring something other than what the live system matches against, which
    would invalidate every number downstream.

    Returns the overall mean similarity, or None if the pickle is unavailable.
    """
    import pickle
    if not os.path.exists(config.ENCODINGS_FILE):
        return None

    with open(config.ENCODINGS_FILE, "rb") as fh:
        enrolled = pickle.load(fh).get("user_encodings", {})
    if not enrolled:
        return None

    rows, embeddings = load(det_size)
    per_user: Dict[str, List[int]] = {}
    for i, row in enumerate(rows):
        per_user.setdefault(row["user_id"], []).append(i)

    similarities: List[float] = []
    for user_id, indices in per_user.items():
        if user_id not in enrolled:
            continue
        mine = embeddings[indices]                       # (n, 512)
        theirs = np.asarray(enrolled[user_id], np.float32)  # (m, 512)
        # Both sides are L2-normalised, so the dot product is cosine similarity.
        similarities.append(float((mine @ theirs.T).mean()))

    return float(np.mean(similarities)) if similarities else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--det-size", type=int, choices=DET_SIZES,
                        help="extract at one size only (default: both)")
    parser.add_argument("--force", action="store_true",
                        help="re-extract even if a cache already exists")
    parser.add_argument("--no-ear", action="store_true",
                        help="skip the MediaPipe EAR pass (faster)")
    args = parser.parse_args()

    sizes = (args.det_size,) if args.det_size else DET_SIZES
    for det_size in sizes:
        if os.path.exists(samples_csv(det_size)) and not args.force:
            logger.info(f"det_size={det_size}: cache exists, skipping "
                        f"(use --force to redo)")
            continue
        extract(det_size, with_ear=not args.no_ear)

    similarity = verify_against_pickle()
    if similarity is not None:
        verdict = "consistent" if similarity > 0.90 else "DIVERGENT"
        logger.info(f"Enrolled-pickle cross-check: mean cosine similarity "
                    f"{similarity:.4f} ({verdict})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
