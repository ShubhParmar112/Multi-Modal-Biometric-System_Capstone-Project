"""
Face Recognizer - Real-time face detection and identification.
Uses InsightFace (ArcFace / buffalo_l) with cosine distance matching.
Returns user_id, confidence score, and face location.
"""

import cv2
import numpy as np
import pickle
from typing import Optional, Tuple, Dict, List

import config
from utils.logger import logger


class FaceRecognizer:
    """
    Real-time face recognizer that identifies registered users
    from a webcam feed using 512-d ArcFace embeddings and cosine distance.
    """

    def __init__(self):
        self.known_encodings: List[np.ndarray] = []
        self.known_ids: List[str] = []
        self.is_loaded = False
        self.frame_count = 0
        self._app = None
        # Last recognition result, reused to annotate skipped frames so the
        # bounding box doesn't flicker between processed frames.
        self._last_result: Tuple[Optional[str], float,
                                 Optional[Tuple[int, int, int, int]]] = (None, 0.0, None)

    def _get_app(self):
        if self._app is None:
            from insightface.app import FaceAnalysis
            det = getattr(config, "FACE_DET_SIZE", 320)
            self._app = FaceAnalysis(
                name='buffalo_l',
                providers=['CPUExecutionProvider']
            )
            self._app.prepare(ctx_id=0, det_size=(det, det))
        return self._app

    def load_encodings(self) -> bool:
        """Load pre-computed face encodings from disk."""
        if not config.ENCODINGS_FILE:
            logger.error("Encodings file path not configured")
            return False

        try:
            with open(config.ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)

            self.known_encodings = data["encodings"]
            self.known_ids = data["ids"]
            self.is_loaded = True

            unique_users = set(self.known_ids)
            logger.success(
                f"Face recognizer loaded: {len(self.known_encodings)} embeddings "
                f"for {len(unique_users)} users"
            )
            return True
        except FileNotFoundError:
            logger.error(
                f"Encodings file not found: {config.ENCODINGS_FILE}. "
                "Please run the encoder first."
            )
            return False
        except Exception as e:
            logger.error(f"Failed to load encodings: {e}")
            return False

    @staticmethod
    def _cosine_distances(known: List[np.ndarray],
                          probe: np.ndarray) -> np.ndarray:
        """
        Cosine distance between probe and every known embedding.
        Embeddings are L2-normalised so dot product = cosine similarity.
        distance = 1 - similarity  (range 0..2, lower = more similar)
        """
        known_arr = np.array(known)           # (N, 512)
        sims = known_arr @ probe              # (N,)
        return 1.0 - sims

    def recognize_from_frame(self, frame: np.ndarray) -> Tuple[
            Optional[str], float, Optional[Tuple[int, int, int, int]]]:
        """
        Identify a face in a single frame.

        Args:
            frame: BGR image from OpenCV

        Returns:
            Tuple of (user_id or None, confidence 0-1, face_location or None)
            face_location is (top, right, bottom, left) to match original API

        Behaviour and cost are unchanged. The richer measurements the same
        computation produces are available from recognize_from_frame_detailed()
        without affecting this path.
        """
        return self._recognize(frame, with_quality=False).as_tuple()

    def recognize_from_frame_detailed(self, frame: np.ndarray):
        """
        As recognize_from_frame(), but returns everything that was measured.

        Returns:
            FaceObservation — the decision plus the values the tuple API drops:
            the raw cosine distance, the detector score, the vote fraction, how
            many gallery embeddings matched, and sample quality.

        The raw distance is the important one. It, not the blended confidence,
        is the quantity with a measured genuine/impostor distribution
        (evaluation/output/face_eval_report.md), so it is what step 4 maps to a
        likelihood ratio. The blended confidence is retained only because it is
        what users and the high-risk floor currently see.

        Nothing on the live authentication path calls this yet.
        """
        return self._recognize(frame, with_quality=True)

    def _recognize(self, frame: np.ndarray, with_quality: bool = False):
        """Shared implementation behind both public recognition methods.

        `with_quality` gates the extra image measurements so the legacy path
        costs exactly what it did before this method existed — the ATM runs
        recognition in a loop, and quality is only needed where it is consumed.
        """
        from auth.fusion.scores import FaceObservation

        if not self.is_loaded:
            logger.error("Encodings not loaded. Call load_encodings() first.")
            return FaceObservation()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        app = self._get_app()
        faces = app.get(rgb)

        if not faces:
            self._last_result = (None, 0.0, None)
            return FaceObservation()

        # Filter by detection confidence
        faces = [f for f in faces
                 if f.det_score >= config.MIN_FACE_CONFIDENCE]
        if not faces:
            self._last_result = (None, 0.0, None)
            return FaceObservation()

        # Use the largest face if multiple detected
        face = max(faces,
                   key=lambda f: (f.bbox[2] - f.bbox[0]) *
                                 (f.bbox[3] - f.bbox[1]))

        probe = face.normed_embedding  # 512-d, L2-normalised

        # InsightFace bbox: [x1, y1, x2, y2] → (top, right, bottom, left)
        x1, y1, x2, y2 = face.bbox.astype(int)
        face_loc = (y1, x2, y2, x1)

        quality = {}
        if with_quality:
            from auth.fusion.quality import face_quality
            quality = face_quality(frame, face.bbox, float(face.det_score))

        observation = FaceObservation(
            face_location=face_loc,
            det_score=float(face.det_score),
            quality=quality,
        )

        if len(self.known_encodings) == 0:
            self._last_result = (None, 0.0, face_loc)
            return observation

        distances = self._cosine_distances(self.known_encodings, probe)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        confidence = round(1.0 - best_distance, 4)

        observation.raw_distance = best_distance

        if best_distance <= config.FACE_RECOGNITION_TOLERANCE:
            user_id = self.known_ids[best_idx]

            # Voting: count how many stored embeddings of each user match
            matches = distances <= config.FACE_RECOGNITION_TOLERANCE
            match_counts: Dict[str, int] = {}
            for match, uid in zip(matches, self.known_ids):
                if match:
                    match_counts[uid] = match_counts.get(uid, 0) + 1

            if match_counts:
                voted_id = max(match_counts, key=match_counts.get)
                vote_confidence = (match_counts[voted_id] /
                                   sum(match_counts.values()))
                final_confidence = round(
                    confidence * 0.6 + vote_confidence * 0.4, 4
                )

                observation.vote_confidence = vote_confidence
                observation.n_matching = int(matches.sum())

                if final_confidence < config.MIN_FACE_CONFIDENCE:
                    result = (None, final_confidence, face_loc)
                else:
                    result = (voted_id, final_confidence, face_loc)
            else:
                result = (user_id, confidence, face_loc)
        else:
            result = (None, confidence, face_loc)

        self._last_result = result
        observation.user_id, observation.confidence = result[0], result[1]
        return observation

    def annotate_frame(self, frame: np.ndarray) -> np.ndarray:
        """Draw the most recent recognition result onto a frame without
        running any inference — cheap enough for the UI thread at 30 FPS."""
        user_id, confidence, face_loc = self._last_result
        if not face_loc:
            return frame
        top, right, bottom, left = face_loc
        color = (0, 212, 170) if user_id else (0, 0, 233)
        label = (f"{user_id} ({confidence:.1%})" if user_id
                 else f"Unknown ({confidence:.1%})")
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, label, (left + 2, top - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        return frame
