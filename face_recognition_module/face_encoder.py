"""
Face Encoder - Generates 512-dimensional ArcFace embeddings using InsightFace.
Processes the dataset directory and creates a serialized encoding file
for fast recognition at runtime.
"""

import os
import pickle
import shutil
import cv2
import numpy as np
from typing import Dict, List, Optional

import config
from utils.logger import logger


class FaceEncoder:
    """
    Encodes face images from the dataset directory into 512-d ArcFace vectors
    via InsightFace (buffalo_l model). Saves encodings to disk for efficient
    loading during recognition.
    """

    def __init__(self):
        self.known_encodings: Dict[str, List[np.ndarray]] = {}
        self.known_names: Dict[str, str] = {}
        self._app = None

    def _get_app(self):
        if self._app is None:
            from insightface.app import FaceAnalysis
            self._app = FaceAnalysis(
                name='buffalo_l',
                providers=['CPUExecutionProvider']
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace buffalo_l model loaded")
        return self._app

    def _encode_user_images(self, user_id: str, user_path: str,
                            images: List[str]) -> List[np.ndarray]:
        """Run the ArcFace model over one user's images. Returns their embeddings."""
        app = self._get_app()
        user_encodings: List[np.ndarray] = []

        for img_name in images:
            img_path = os.path.join(user_path, img_name)
            try:
                image = cv2.imread(img_path)
                if image is None:
                    logger.warning(f"Cannot read image: {img_name}")
                    continue

                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                faces = app.get(rgb)

                if len(faces) == 0:
                    logger.warning(f"No face found in {img_name}")
                    continue

                if len(faces) > 1:
                    logger.warning(
                        f"Multiple faces in {img_name}, using largest"
                    )
                    faces = [max(
                        faces,
                        key=lambda f: (
                            (f.bbox[2] - f.bbox[0]) *
                            (f.bbox[3] - f.bbox[1])
                        )
                    )]

                # 512-d L2-normalised ArcFace embedding
                user_encodings.append(faces[0].normed_embedding)

            except Exception as e:
                logger.error(f"Error processing {img_path}: {e}")

        return user_encodings

    def encode_dataset(self, force: bool = False) -> bool:
        """
        Generate 512-d embeddings for every user in the dataset directory.

        ArcFace embeddings are deterministic, so users already present in the
        encodings file (with a matching image count) are reused from cache
        rather than re-encoded — only new or changed users hit the model. This
        keeps enrollment fast as the dataset grows. Pass ``force=True`` to
        re-encode everyone from scratch (e.g. after swapping the model).

        Expected directory structure:
            dataset/
              USR001/
                USR001_000.jpg
                ...
              USR002/
                ...

        Returns:
            True if encodings were generated successfully
        """
        if not os.path.exists(config.DATASET_DIR):
            logger.error(f"Dataset directory not found: {config.DATASET_DIR}")
            return False

        user_dirs = [d for d in os.listdir(config.DATASET_DIR)
                     if os.path.isdir(os.path.join(config.DATASET_DIR, d))]

        if not user_dirs:
            logger.error("No user directories found in dataset")
            return False

        # Load whatever is already encoded so we can reuse unchanged users.
        cached: Dict[str, List[np.ndarray]] = {}
        if not force and os.path.exists(config.ENCODINGS_FILE):
            try:
                with open(config.ENCODINGS_FILE, "rb") as f:
                    cached = pickle.load(f).get("user_encodings", {})
            except Exception as e:
                logger.warning(f"Could not read cached encodings, re-encoding all: {e}")
                cached = {}

        self.known_encodings = {}
        reused_users = 0
        encoded_users = 0
        failed_images = 0

        for user_id in user_dirs:
            user_path = os.path.join(config.DATASET_DIR, user_id)
            images = [f for f in os.listdir(user_path)
                      if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]

            if not images:
                logger.warning(f"No images found for user {user_id}")
                continue

            # Reuse cached embeddings when the image count is unchanged.
            if user_id in cached and len(cached[user_id]) == len(images):
                self.known_encodings[user_id] = cached[user_id]
                reused_users += 1
                logger.info(
                    f"User {user_id}: reused {len(images)} cached embeddings"
                )
                continue

            logger.info(f"Encoding {len(images)} images for user: {user_id}")
            user_encodings = self._encode_user_images(user_id, user_path, images)
            failed_images += len(images) - len(user_encodings)

            if user_encodings:
                self.known_encodings[user_id] = user_encodings
                encoded_users += 1
                logger.success(
                    f"User {user_id}: {len(user_encodings)} embeddings generated"
                )

        if not self.known_encodings:
            logger.error("No valid encodings generated from dataset")
            return False

        # Rebuild the flat parallel lists from the per-user map so they stay
        # in sync (and users whose folders were deleted are dropped).
        all_encodings: List[np.ndarray] = []
        all_ids: List[str] = []
        for user_id, encs in self.known_encodings.items():
            all_encodings.extend(encs)
            all_ids.extend([user_id] * len(encs))

        encoding_data = {
            "encodings": all_encodings,
            "ids": all_ids,
            "user_encodings": self.known_encodings,
        }

        os.makedirs(config.ENCODINGS_DIR, exist_ok=True)
        with open(config.ENCODINGS_FILE, "wb") as f:
            pickle.dump(encoding_data, f)

        logger.success(
            f"Encodings saved: {len(all_encodings)} faces from "
            f"{len(self.known_encodings)} users "
            f"({encoded_users} encoded, {reused_users} reused from cache, "
            f"{failed_images} failed) -> {config.ENCODINGS_FILE}"
        )
        return True

    def load_encodings(self) -> bool:
        """Load pre-computed encodings from disk."""
        if not os.path.exists(config.ENCODINGS_FILE):
            logger.error(
                f"Encodings file not found: {config.ENCODINGS_FILE}. "
                "Run encode_dataset() first."
            )
            return False

        try:
            with open(config.ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)

            self.known_encodings = data.get("user_encodings", {})
            logger.success(
                f"Loaded encodings for {len(self.known_encodings)} users"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to load encodings: {e}")
            return False

    def get_average_encoding(self, user_id: str) -> Optional[np.ndarray]:
        """
        Get the average embedding for a user (used for DB storage).
        Re-normalises after averaging so the vector stays unit-length.
        """
        if user_id in self.known_encodings:
            encodings = self.known_encodings[user_id]
            avg = np.mean(encodings, axis=0)
            norm = np.linalg.norm(avg)
            return avg / norm if norm > 0 else avg
        return None

    def add_encoding(self, user_id: str, encoding: np.ndarray):
        """Add a single embedding for a user (for live enrollment)."""
        if user_id not in self.known_encodings:
            self.known_encodings[user_id] = []
        self.known_encodings[user_id].append(encoding)

    def remove_user_data(self, user_id: str) -> bool:
        """
        Delete all stored face data for a user: their dataset image folder
        and every embedding of theirs in the encodings file.

        Returns:
            True if cleanup succeeded (also when there was nothing to delete)
        """
        ok = True

        user_dir = os.path.join(config.DATASET_DIR, user_id)
        if os.path.isdir(user_dir):
            try:
                shutil.rmtree(user_dir)
                logger.info(f"Deleted dataset folder: {user_dir}")
            except Exception as e:
                logger.error(f"Failed to delete dataset folder for {user_id}: {e}")
                ok = False

        if os.path.exists(config.ENCODINGS_FILE):
            try:
                with open(config.ENCODINGS_FILE, "rb") as f:
                    data = pickle.load(f)

                ids = data.get("ids", [])
                if user_id in ids or user_id in data.get("user_encodings", {}):
                    keep = [i for i, uid in enumerate(ids) if uid != user_id]
                    data["encodings"] = [data["encodings"][i] for i in keep]
                    data["ids"] = [ids[i] for i in keep]
                    data.get("user_encodings", {}).pop(user_id, None)

                    with open(config.ENCODINGS_FILE, "wb") as f:
                        pickle.dump(data, f)
                    logger.info(f"Removed encodings for {user_id} "
                                f"from {config.ENCODINGS_FILE}")
            except Exception as e:
                logger.error(f"Failed to purge encodings for {user_id}: {e}")
                ok = False

        self.known_encodings.pop(user_id, None)
        return ok
