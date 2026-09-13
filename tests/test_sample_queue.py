from datetime import date
from pathlib import Path

import numpy as np

from sample_queue import DailyByteBudget, SampleQueue, crop_roi, resize_long_edge
from upload_client import UploadClient


def test_daily_byte_budget_rolls_and_limits():
    budget = DailyByteBudget(100)
    assert budget.can_afford(40, today=date(2026, 1, 1))
    assert budget.consume(40, today=date(2026, 1, 1))
    assert budget.remaining(today=date(2026, 1, 1)) == 60
    assert budget.consume(70, today=date(2026, 1, 1)) is False
    # new day resets
    assert budget.consume(70, today=date(2026, 1, 2)) is True


def test_sample_queue_saves_within_budget(tmp_path: Path):
    queue = SampleQueue(
        root_dir=tmp_path,
        daily_budget_bytes=50_000,
        jpeg_quality=50,
        max_long_edge=64,
        device_id="E001",
    )
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:] = (30, 60, 90)
    result = queue.enqueue(
        frame,
        reason="uncertain_conf",
        confidence=0.4,
        predicted_floor="5",
        predicted_direction="up",
        bbox=(10, 10, 80, 80),
    )
    assert result.saved is True
    assert result.image_path is not None and result.image_path.exists()
    assert result.meta_path is not None and result.meta_path.exists()
    assert queue.bytes_used_today() > 0


def test_sample_queue_rejects_when_budget_exceeded(tmp_path: Path):
    queue = SampleQueue(
        root_dir=tmp_path,
        daily_budget_bytes=100,
        jpeg_quality=95,
        max_long_edge=320,
        device_id="E001",
    )
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    first = queue.enqueue(
        frame,
        reason="uncertain_conf",
        confidence=0.4,
        predicted_floor="1",
        predicted_direction=0,
    )
    # Tiny budget: either first fails or second fails; at least one budget_exceeded path
    second = queue.enqueue(
        frame,
        reason="uncertain_conf",
        confidence=0.4,
        predicted_floor="2",
        predicted_direction=0,
    )
    assert first.reason in {"saved", "budget_exceeded"}
    if first.saved:
        assert second.saved is False
        assert second.reason == "budget_exceeded"
    else:
        assert first.reason == "budget_exceeded"


def test_crop_and_resize():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    cropped = crop_roi(frame, (10, 20, 50, 80))
    assert cropped.shape[0] == 60
    assert cropped.shape[1] == 40
    resized = resize_long_edge(frame, 50)
    assert max(resized.shape[0], resized.shape[1]) == 50


def test_upload_client_disabled(tmp_path: Path):
    meta = tmp_path / "a.json"
    image = tmp_path / "a.jpg"
    meta.write_text("{}", encoding="utf-8")
    image.write_bytes(b"jpeg")
    client = UploadClient(enabled=False, url="http://example.invalid/upload")
    result = client.maybe_upload(meta, image)
    assert result.attempted is False
    assert result.detail == "upload_disabled"
