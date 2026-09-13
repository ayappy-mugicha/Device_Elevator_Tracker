"""Local hard-example queue with daily byte budget."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np

from hard_example import BBox


@dataclass
class EnqueueResult:
    saved: bool
    reason: str
    meta_path: Optional[Path] = None
    image_path: Optional[Path] = None
    bytes_used_today: int = 0


class DailyByteBudget:
    """In-memory daily byte budget tracker (also used by unit tests)."""

    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = int(limit_bytes)
        self._date: Optional[date] = None
        self._used = 0

    def remaining(self, today: Optional[date] = None) -> int:
        self._roll(today or date.today())
        return max(0, self.limit_bytes - self._used)

    def can_afford(self, size: int, today: Optional[date] = None) -> bool:
        return size <= self.remaining(today)

    def consume(self, size: int, today: Optional[date] = None) -> bool:
        day = today or date.today()
        self._roll(day)
        if self._used + size > self.limit_bytes:
            return False
        self._used += size
        return True

    def _roll(self, day: date) -> None:
        if self._date != day:
            self._date = day
            self._used = 0


class SampleQueue:
    """Persist ROI JPEG + metadata JSON under a queue directory."""

    def __init__(
        self,
        root_dir: Path,
        daily_budget_bytes: int = 5 * 1024 * 1024,
        jpeg_quality: int = 70,
        max_long_edge: int = 320,
        device_id: str = "unknown",
    ) -> None:
        self.root_dir = Path(root_dir)
        self.images_dir = self.root_dir / "images"
        self.meta_dir = self.root_dir / "meta"
        self.budget_path = self.root_dir / "budget.json"
        self.daily_budget_bytes = int(daily_budget_bytes)
        self.jpeg_quality = int(jpeg_quality)
        self.max_long_edge = int(max_long_edge)
        self.device_id = device_id

        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def bytes_used_today(self, today: Optional[date] = None) -> int:
        state = self._load_budget()
        day = (today or date.today()).isoformat()
        if state.get("date") != day:
            return 0
        return int(state.get("bytes_used", 0))

    def enqueue(
        self,
        frame: np.ndarray,
        *,
        reason: str,
        confidence: float,
        predicted_floor: Any,
        predicted_direction: Any,
        bbox: Optional[BBox] = None,
        extra: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> EnqueueResult:
        used = self.bytes_used_today()
        if used >= self.daily_budget_bytes:
            return EnqueueResult(False, "budget_exceeded", bytes_used_today=used)

        roi = crop_roi(frame, bbox)
        resized = resize_long_edge(roi, self.max_long_edge)
        ok, buf = cv2.imencode(
            ".jpg",
            resized,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            return EnqueueResult(False, "encode_failed", bytes_used_today=used)

        payload = buf.tobytes()
        if used + len(payload) > self.daily_budget_bytes:
            return EnqueueResult(False, "budget_exceeded", bytes_used_today=used)

        ts = now or datetime.now(timezone.utc)
        sample_id = f"{ts.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
        image_name = f"{sample_id}.jpg"
        meta_name = f"{sample_id}.json"
        image_path = self.images_dir / image_name
        meta_path = self.meta_dir / meta_name

        image_path.write_bytes(payload)
        meta = {
            "sample_id": sample_id,
            "device_id": self.device_id,
            "timestamp": ts.isoformat(),
            "predicted_floor": predicted_floor,
            "predicted_direction": predicted_direction,
            "confidence": float(confidence),
            "reason": reason,
            "bbox": list(bbox) if bbox else None,
            "image_relpath": f"images/{image_name}",
            "image_bytes": len(payload),
        }
        if extra:
            meta["extra"] = extra
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        new_used = used + len(payload) + meta_path.stat().st_size
        self._save_budget(new_used, ts.date())
        return EnqueueResult(True, "saved", meta_path, image_path, new_used)

    def _load_budget(self) -> Dict[str, Any]:
        defaults = {"date": date.today().isoformat(), "bytes_used": 0}
        if not self.budget_path.exists():
            return defaults
        try:
            data = json.loads(self.budget_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return defaults
            return data
        except (OSError, json.JSONDecodeError):
            return defaults

    def _save_budget(self, bytes_used: int, day: date) -> None:
        payload = {"date": day.isoformat(), "bytes_used": int(bytes_used)}
        self.budget_path.write_text(json.dumps(payload), encoding="utf-8")


def crop_roi(frame: np.ndarray, bbox: Optional[BBox]) -> np.ndarray:
    if bbox is None:
        return frame
    h, w = frame.shape[:2]
    xmin, ymin, xmax, ymax = bbox
    x1 = max(0, min(w - 1, int(xmin)))
    y1 = max(0, min(h - 1, int(ymin)))
    x2 = max(0, min(w, int(xmax)))
    y2 = max(0, min(h, int(ymax)))
    if x2 <= x1 or y2 <= y1:
        return frame
    return frame[y1:y2, x1:x2]


def resize_long_edge(image: np.ndarray, max_long_edge: int) -> np.ndarray:
    if max_long_edge <= 0:
        return image
    h, w = image.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_long_edge:
        return image
    scale = max_long_edge / float(long_edge)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
