"""Hard-example detection for active learning on the edge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple


BBox = Tuple[float, float, float, float]  # xmin, ymin, xmax, ymax


@dataclass
class HardExampleDecision:
    is_hard: bool
    reason: str
    confidence: float
    bbox: Optional[BBox] = None


class HardExampleDetector:
    """Decide whether an elevator detection frame is worth saving."""

    def __init__(
        self,
        conf_low: float = 0.25,
        conf_high: float = 0.65,
        miss_frames: int = 5,
        min_interval_sec: float = 3.0,
        floor_jump_threshold: int = 2,
    ) -> None:
        self.conf_low = float(conf_low)
        self.conf_high = float(conf_high)
        self.miss_frames = int(miss_frames)
        self.min_interval_sec = float(min_interval_sec)
        self.floor_jump_threshold = int(floor_jump_threshold)

        self._miss_streak = 0
        self._last_floor: Optional[int] = None
        self._last_saved_at: float = 0.0

    def observe(
        self,
        *,
        floor: Any,
        direction: Any,
        confidence: float,
        bbox: Optional[BBox],
        now: float,
        has_detection: bool,
    ) -> HardExampleDecision:
        conf = float(confidence or 0.0)
        reason = ""

        if not has_detection or (not _is_floor(floor) and not _is_direction(direction)):
            self._miss_streak += 1
            if self._miss_streak >= self.miss_frames:
                reason = "miss_streak"
        else:
            self._miss_streak = 0

        if not reason and self.conf_low <= conf <= self.conf_high:
            reason = "uncertain_conf"

        floor_int = _to_floor_int(floor)
        if (
            not reason
            and floor_int is not None
            and self._last_floor is not None
            and abs(floor_int - self._last_floor) >= self.floor_jump_threshold
        ):
            reason = "floor_jump"

        if floor_int is not None:
            self._last_floor = floor_int

        if not reason:
            return HardExampleDecision(False, "", conf, bbox)

        if now - self._last_saved_at < self.min_interval_sec:
            return HardExampleDecision(False, "throttled", conf, bbox)

        self._last_saved_at = now
        return HardExampleDecision(True, reason, conf, bbox)


def pick_best_bbox(rows: Sequence[dict]) -> Optional[BBox]:
    """Pick bbox of the highest-confidence row. Rows need xmin/ymin/xmax/ymax/confidence."""
    if not rows:
        return None
    best = max(rows, key=lambda r: float(r.get("confidence", 0.0)))
    try:
        return (
            float(best["xmin"]),
            float(best["ymin"]),
            float(best["xmax"]),
            float(best["ymax"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _is_floor(floor: Any) -> bool:
    if floor is None or floor == 0 or floor == "0":
        return False
    return str(floor).strip().isdigit()


def _is_direction(direction: Any) -> bool:
    if direction is None or direction == 0:
        return False
    return str(direction).strip().lower() in {"up", "down"}


def _to_floor_int(floor: Any) -> Optional[int]:
    if not _is_floor(floor):
        return None
    try:
        return int(str(floor).strip())
    except ValueError:
        return None
