"""Tests for vibesop.core.badges module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from vibesop.core.badges import Badge, BadgeTracker, BadgeType, get_badge_display


class TestBadgeType:
    """Test badge type enumeration."""

    def test_badge_type_values(self) -> None:
        assert BadgeType.FIRST_FEEDBACK.value == "first_feedback"
        assert BadgeType.SKILL_CHAMPION.value == "skill_champion"
        assert BadgeType.QUALITY_MASTER.value == "quality_master"
        assert BadgeType.ECOSYSTEM_GUARDIAN.value == "ecosystem_guardian"


class TestBadge:
    """Test Badge dataclass serialization."""

    def test_to_dict(self) -> None:
        badge = Badge(
            type=BadgeType.FIRST_FEEDBACK,
            awarded_at="2026-04-22T12:00:00+00:00",
            skill_id="gstack/review",
        )
        data = badge.to_dict()
        assert data["type"] == "first_feedback"
        assert data["awarded_at"] == "2026-04-22T12:00:00+00:00"
        assert data["skill_id"] == "gstack/review"

    def test_from_dict(self) -> None:
        data = {
            "type": "skill_champion",
            "awarded_at": "2026-04-22T12:00:00+00:00",
            "skill_id": "superpowers/debug",
        }
        badge = Badge.from_dict(data)
        assert badge.type == BadgeType.SKILL_CHAMPION
        assert badge.skill_id == "superpowers/debug"

    def test_roundtrip(self) -> None:
        original = Badge(
            type=BadgeType.ECOSYSTEM_GUARDIAN,
            awarded_at="2026-04-22T12:00:00+00:00",
        )
        restored = Badge.from_dict(original.to_dict())
        assert restored.type == original.type
        assert restored.awarded_at == original.awarded_at
        assert restored.skill_id is None


class TestGetBadgeDisplay:
    """Test badge display metadata."""

    def test_known_badge(self) -> None:
        meta = get_badge_display(BadgeType.FIRST_FEEDBACK)
        assert "icon" in meta
        assert "title" in meta
        assert "description" in meta

    def test_unknown_badge(self) -> None:
        # Create a fake badge type for edge case
        class FakeType:
            value = "unknown"

        meta = get_badge_display(FakeType())  # type: ignore[arg-type]
        assert meta["title"] == "unknown"


class TestBadgeTracker:
    """Test BadgeTracker persistence and logic."""

    def test_load_empty_config(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)
        assert tracker.list_badges() == []
        assert not tracker.has_badge(BadgeType.FIRST_FEEDBACK)

    def test_load_existing_badges(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        data = {
            "badges": [
                {"type": "first_feedback", "awarded_at": "2026-04-22T12:00:00+00:00"},
            ],
        }
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        tracker = BadgeTracker(data_path)
        badges = tracker.list_badges()
        assert len(badges) == 1
        assert badges[0].type == BadgeType.FIRST_FEEDBACK
        assert tracker.has_badge(BadgeType.FIRST_FEEDBACK)
        assert not tracker.has_badge(BadgeType.SKILL_CHAMPION)

    def test_award_new_badge(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        badge = tracker.award(BadgeType.FIRST_FEEDBACK)
        assert badge is not None
        assert badge.type == BadgeType.FIRST_FEEDBACK
        assert tracker.has_badge(BadgeType.FIRST_FEEDBACK)

        # Verify persistence
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["badges"]) == 1

    def test_award_duplicate_returns_none(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        tracker.award(BadgeType.FIRST_FEEDBACK)
        second = tracker.award(BadgeType.FIRST_FEEDBACK)
        assert second is None
        assert len(tracker.list_badges()) == 1

    def test_award_with_skill_id(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        badge = tracker.award(BadgeType.SKILL_CHAMPION, skill_id="gstack/review")
        assert badge is not None
        assert badge.skill_id == "gstack/review"

    def test_check_feedback_event_first_feedback(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        new_badges = tracker.check_feedback_event()
        assert len(new_badges) == 1
        assert new_badges[0].type == BadgeType.FIRST_FEEDBACK

    def test_check_feedback_event_ecosystem_guardian(self, tmp_path: Path, tmp_path_factory: Any) -> None:
        # Need to mock feedback file to have 5+ records
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        # Already has first_feedback
        tracker.award(BadgeType.FIRST_FEEDBACK)

        vibe_dir = tmp_path / ".vibe"
        vibe_dir.mkdir(exist_ok=True)
        feedback_path = vibe_dir / "execution_feedback.json"
        with patch.object(Path, "home", return_value=tmp_path):
            with open(feedback_path, "w", encoding="utf-8") as f:
                json.dump([{"skill_id": "a"} for _ in range(5)], f)

            new_badges = tracker.check_feedback_event()
            assert any(b.type == BadgeType.ECOSYSTEM_GUARDIAN for b in new_badges)

    def test_check_route_event_skill_champion(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        history = [{"skill_id": "gstack/review"} for _ in range(10)]
        new_badges = tracker.check_route_event("gstack/review", history)

        assert len(new_badges) == 1
        assert new_badges[0].type == BadgeType.SKILL_CHAMPION
        assert new_badges[0].skill_id == "gstack/review"

    def test_check_route_event_not_enough_routes(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        history = [{"skill_id": "gstack/review"} for _ in range(5)]
        new_badges = tracker.check_route_event("gstack/review", history)
        assert new_badges == []

    def test_check_quality_master(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        class MockEval:
            def __init__(self, grade: str) -> None:
                self.grade = grade

        evals = {
            "skill-a": MockEval("A"),
            "skill-b": MockEval("B"),
        }
        new_badges = tracker.check_quality_master(evals)

        assert len(new_badges) == 1
        assert new_badges[0].type == BadgeType.QUALITY_MASTER

    def test_check_quality_master_with_low_grade(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        class MockEval:
            def __init__(self, grade: str) -> None:
                self.grade = grade

        evals = {
            "skill-a": MockEval("A"),
            "skill-b": MockEval("C"),
        }
        new_badges = tracker.check_quality_master(evals)
        assert new_badges == []

    def test_check_quality_master_empty(self, tmp_path: Path) -> None:
        data_path = tmp_path / "badges.json"
        tracker = BadgeTracker(data_path)

        new_badges = tracker.check_quality_master({})
        assert new_badges == []
