import time

from hard_example import HardExampleDetector, pick_best_bbox


def test_uncertain_confidence_is_hard():
    detector = HardExampleDetector(conf_low=0.25, conf_high=0.65, min_interval_sec=0)
    decision = detector.observe(
        floor="5",
        direction="up",
        confidence=0.4,
        bbox=(10, 10, 50, 50),
        now=100.0,
        has_detection=True,
    )
    assert decision.is_hard is True
    assert decision.reason == "uncertain_conf"


def test_high_confidence_is_not_hard():
    detector = HardExampleDetector(conf_low=0.25, conf_high=0.65, min_interval_sec=0)
    decision = detector.observe(
        floor="5",
        direction="up",
        confidence=0.9,
        bbox=(10, 10, 50, 50),
        now=100.0,
        has_detection=True,
    )
    assert decision.is_hard is False


def test_miss_streak_triggers_hard():
    detector = HardExampleDetector(miss_frames=3, min_interval_sec=0)
    for i in range(2):
        d = detector.observe(
            floor=0,
            direction=0,
            confidence=0.0,
            bbox=None,
            now=float(i),
            has_detection=False,
        )
        assert d.is_hard is False
    decision = detector.observe(
        floor=0,
        direction=0,
        confidence=0.0,
        bbox=None,
        now=3.0,
        has_detection=False,
    )
    assert decision.is_hard is True
    assert decision.reason == "miss_streak"


def test_floor_jump_triggers_hard():
    detector = HardExampleDetector(
        conf_low=0.9,
        conf_high=0.95,
        min_interval_sec=0,
        floor_jump_threshold=2,
    )
    first = detector.observe(
        floor="3",
        direction="up",
        confidence=0.99,
        bbox=None,
        now=1.0,
        has_detection=True,
    )
    assert first.is_hard is False
    second = detector.observe(
        floor="8",
        direction="up",
        confidence=0.99,
        bbox=None,
        now=2.0,
        has_detection=True,
    )
    assert second.is_hard is True
    assert second.reason == "floor_jump"


def test_min_interval_throttles():
    detector = HardExampleDetector(min_interval_sec=5.0)
    first = detector.observe(
        floor="5",
        direction=0,
        confidence=0.4,
        bbox=None,
        now=10.0,
        has_detection=True,
    )
    assert first.is_hard is True
    second = detector.observe(
        floor="5",
        direction=0,
        confidence=0.4,
        bbox=None,
        now=12.0,
        has_detection=True,
    )
    assert second.is_hard is False
    assert second.reason == "throttled"


def test_pick_best_bbox():
    rows = [
        {"xmin": 1, "ymin": 1, "xmax": 2, "ymax": 2, "confidence": 0.2},
        {"xmin": 5, "ymin": 5, "xmax": 9, "ymax": 9, "confidence": 0.8},
    ]
    assert pick_best_bbox(rows) == (5.0, 5.0, 9.0, 9.0)
    assert pick_best_bbox([]) is None
