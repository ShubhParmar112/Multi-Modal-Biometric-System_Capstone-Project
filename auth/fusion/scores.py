"""
Containers for what each modality measured.

These are *observations*, not decisions: everything a modality produced during
one authentication attempt, including the values the pipeline currently
discards. Step 3 fills them; step 4 normalises and combines them.

Why dataclasses instead of widening the existing return tuples: every existing
call site keeps working unchanged. `recognize_from_frame()` still returns its
3-tuple and `request_fingerprint_scan()` still returns its 2-tuple; the richer
data travels through parallel `*_detailed()` methods that nothing on the live
path calls yet.

`available` is deliberately explicit throughout. A modality that could not be
measured — an unflashed sensor reporting no score, a frame with no face — must
never be read as "measured, and the result was bad". Fusion renormalises its
weights over the modalities that are actually present.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class FaceObservation:
    """One face recognition attempt.

    Attributes beyond the current 3-tuple:
        raw_distance      the minimum cosine distance before any blending.
                          This is the quantity with a measured genuine/impostor
                          distribution (evaluation/output/face_eval_report.md),
                          so it — not the blended confidence — is what step 4
                          maps to a likelihood ratio.
        vote_confidence   fraction of matching gallery embeddings belonging to
                          the winning user.
        n_matching        how many gallery embeddings fell inside tolerance.
        confidence        the blended value the live rule reports. Retained
                          because it is what users and the high-risk floor see,
                          not because fusion should consume it.
    """
    user_id: Optional[str] = None
    confidence: float = 0.0
    face_location: Optional[Tuple[int, int, int, int]] = None
    raw_distance: Optional[float] = None
    det_score: Optional[float] = None
    vote_confidence: Optional[float] = None
    n_matching: int = 0
    quality: Dict[str, float] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """True when a face was detected and scored, matched or not.

        A rejected face is still a measurement. Only the absence of any face
        makes the modality unavailable.
        """
        return self.raw_distance is not None

    def as_tuple(self) -> Tuple[Optional[str], float,
                                Optional[Tuple[int, int, int, int]]]:
        """The legacy 3-tuple, so the old API can be served from this object."""
        return self.user_id, self.confidence, self.face_location


@dataclass
class FingerprintObservation:
    """One fingerprint scan, from either the hardware or software path.

    `sensor_confidence` is the R307S match score recovered in step 2; it is
    None on firmware predating that change, in simulation, and on every
    non-match (the sensor reports no score below its internal threshold, which
    censors the low end of the impostor distribution).

    `match_score` is the software matcher's good-match count. The two paths
    produce numbers on entirely different scales, which is exactly why step 4
    normalises per source rather than comparing them directly.
    """
    fingerprint_id: Optional[int] = None
    is_match: bool = False
    confidence: float = 0.0
    sensor_confidence: Optional[int] = None
    match_score: Optional[int] = None
    source: str = "unknown"           # "hardware" | "software" | "simulation"
    quality: Dict[str, float] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """True only when a real score was measured.

        A bare match/no-match verdict carries no score, so it cannot take part
        in score-level fusion — the case that motivated step 2.
        """
        return self.sensor_confidence is not None or self.match_score is not None

    def as_tuple(self) -> Tuple[Optional[int], bool]:
        """The legacy 2-tuple used by ui/atm_interface.py."""
        return self.fingerprint_id, self.is_match


@dataclass
class LivenessObservation:
    """One liveness check, with the trajectory behind the verdict.

    Stays a veto rather than a fused term. Retained because the trajectory
    describes how confidently liveness was established, and because a low
    face_seen_ratio devalues the face sample it was measured alongside.
    """
    blink_count: int = 0
    required: int = 0
    ear_history: List[Optional[float]] = field(default_factory=list)
    quality: Dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.blink_count >= self.required

    @property
    def available(self) -> bool:
        return any(e is not None for e in self.ear_history)
