"""
Liveness Detection Module - Anti-spoofing via blink detection.
Uses MediaPipe Face Landmarker Tasks API (mediapipe >= 0.10.x).
Falls back to legacy solutions API for older mediapipe versions.

Eye Aspect Ratio (EAR) indices from the 478-landmark model:
  Left eye:  [362, 385, 387, 263, 373, 380]
  Right eye: [33,  160, 158, 133, 153, 144]
"""

import os
from collections import deque
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple

import config
from utils.logger import logger

_LEFT_EYE_EAR  = [362, 385, 387, 263, 373, 380]
_RIGHT_EYE_EAR = [33,  160, 158, 133, 153, 144]

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)
_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "face_landmarker.task"
)


def _download_model():
    """Download the FaceLandmarker model if not already present."""
    if os.path.exists(_MODEL_PATH):
        return
    os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
    logger.info("Downloading MediaPipe face_landmarker model (~29MB)...")
    import urllib.request
    urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
    logger.success("face_landmarker model downloaded")


class LivenessDetector:
    """
    Anti-spoofing detector using MediaPipe Face Landmarker Eye Aspect Ratio.
    A real person must blink LIVENESS_BLINK_REQUIRED times to pass.
    """

    # Upper bound on the retained EAR trajectory. A 15 s ATM check at ~20 fps
    # is ~300 frames and a web burst is 20, so this holds a whole attempt with
    # room to spare while keeping memory bounded if a detector is reused across
    # many checks without reset().
    _MAX_HISTORY = 512

    def __init__(self):
        self.blink_count = 0
        self._consec_closed = 0
        self._detector   = None  # FaceLandmarker (Tasks API)
        # EAR per frame fed to update_blink_state, None where no face was seen.
        # Descriptive only — the blink state machine does not read it, so the
        # liveness verdict is exactly what it was before this existed.
        self._ear_history = deque(maxlen=self._MAX_HISTORY)

    # ─────────────────────────────────────────────────────────────
    # Detector initialisation
    # ─────────────────────────────────────────────────────────────

    def _get_detector(self):
        """Lazy-init the MediaPipe FaceLandmarker (Tasks API)."""
        if self._detector is None:
            _download_model()
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            options = mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(
                    model_asset_path=_MODEL_PATH
                ),
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._detector = mp_vision.FaceLandmarker.create_from_options(options)
        return self._detector

    # ─────────────────────────────────────────────────────────────
    # EAR helpers
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _eye_aspect_ratio(eye_points: np.ndarray) -> Optional[float]:
        """EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)

        Returns None when the eye is degenerate (zero width), which means the
        landmarks are unusable — not that the eye is shut. See the module
        docstring for why that distinction matters.
        """
        v1 = np.linalg.norm(eye_points[1] - eye_points[5])
        v2 = np.linalg.norm(eye_points[2] - eye_points[4])
        h  = np.linalg.norm(eye_points[0] - eye_points[3])
        return (v1 + v2) / (2.0 * h) if h > 0 else None

    def _get_ear_from_frame(self, rgb_frame: np.ndarray) -> Tuple[
            Optional[float], np.ndarray, np.ndarray]:
        """
        Run the FaceLandmarker on one RGB frame.
        Returns (EAR, left_eye_pts, right_eye_pts) in pixel coordinates,
        or (None, empty, empty) when no face is detected.
        """
        import mediapipe as mp

        detector = self._get_detector()
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result   = detector.detect(mp_image)

        if not result.face_landmarks:
            return None, np.array([]), np.array([])

        lm   = result.face_landmarks[0]
        h, w = rgb_frame.shape[:2]

        left_pts  = np.array([(lm[i].x * w, lm[i].y * h) for i in _LEFT_EYE_EAR])
        right_pts = np.array([(lm[i].x * w, lm[i].y * h) for i in _RIGHT_EYE_EAR])

        left_ear  = self._eye_aspect_ratio(left_pts)
        right_ear = self._eye_aspect_ratio(right_pts)
        usable = [e for e in (left_ear, right_ear) if e is not None]
        if not usable:
            # Landmarks came back degenerate — we saw something, but we cannot
            # measure it. Unmeasurable is not "closed".
            return None, left_pts, right_pts

        return sum(usable) / len(usable), left_pts, right_pts

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def check_frame_liveness(self, frame: np.ndarray) -> Tuple[
            Optional[float], bool, np.ndarray]:
        """
        Check liveness on a single frame (used by the UI live feed).

        Returns:
            Tuple of (ear_value, eyes_closed, annotated_frame), where
            ear_value is None when no face was found or the landmarks were
            unusable. `eyes_closed` describes THIS frame only — a blink is a
            temporal event, so use update_blink_state() to count blinks.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ear, left_pts, right_pts = self._get_ear_from_frame(rgb)
        display = frame.copy()

        if left_pts.size > 0:
            cv2.polylines(display, [left_pts.astype(np.int32)],
                          True, (0, 212, 170), 1)
            cv2.polylines(display, [right_pts.astype(np.int32)],
                          True, (0, 212, 170), 1)

        if ear is None:
            return None, False, display
        return ear, ear < config.EYE_AR_THRESH, display

    # ─────────────────────────────────────────────────────────────
    # Blink state machine
    # ─────────────────────────────────────────────────────────────

    def update_blink_state(self, ear: Optional[float]) -> bool:
        """
        Feed one frame's EAR to the blink counter.

        Returns True on the frame where a blink COMPLETES, i.e. the eyes have
        been shut for at least EYE_AR_CONSEC_FRAMES and have now reopened.
        `self.blink_count` accumulates completed blinks.

        A blink is "eyes closed, then open again, on a face we watched the
        whole time". When ear is None we did not see a face, so any blink in
        progress is DISCARDED rather than completed: without the face we
        cannot attest that the eyes reopened on a live person. That gap is
        precisely the attack this guards against — hold a photograph, cover
        the lens for two frames, uncover, and a naive counter scores a blink.
        Losing the face mid-blink therefore costs the user that blink and
        they must blink again; that is the intended trade.
        """
        self._ear_history.append(ear)

        if ear is None:
            self._consec_closed = 0
            return False

        if ear < config.EYE_AR_THRESH:
            self._consec_closed += 1
            return False

        # Eyes are open. If they were shut long enough, that was a blink.
        completed = self._consec_closed >= config.EYE_AR_CONSEC_FRAMES
        self._consec_closed = 0
        if completed:
            self.blink_count += 1
        return completed

    def reset(self):
        """Reset blink counter and state for a new liveness check."""
        self.blink_count = 0
        self._consec_closed = 0
        self._ear_history.clear()

    # ─────────────────────────────────────────────────────────────
    # Trajectory (descriptive — does not affect the liveness verdict)
    # ─────────────────────────────────────────────────────────────

    @property
    def ear_history(self) -> List[Optional[float]]:
        """EAR per frame since the last reset(), None where no face was seen."""
        return list(self._ear_history)

    def trajectory_stats(self) -> Dict[str, float]:
        """Descriptive statistics over the EAR trajectory.

        Liveness stays a veto rather than a fused term, so these do not enter
        any weighted sum. They serve two other purposes: recording how
        confidently liveness was established, and devaluing a face sample taken
        during a burst where the face was mostly not visible.

        ear_variance is the discriminative one — a still photograph produces a
        perfectly constant EAR, so near-zero variance is itself evidence of a
        static presentation.
        """
        from auth.fusion.quality import liveness_quality
        return liveness_quality(self.ear_history)

    def observation(self):
        """The trajectory and verdict as a LivenessObservation."""
        from auth.fusion.scores import LivenessObservation
        return LivenessObservation(
            blink_count=self.blink_count,
            required=config.LIVENESS_BLINK_REQUIRED,
            ear_history=self.ear_history,
            quality=self.trajectory_stats(),
        )
