"""Tests for skill suggestion collector."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vibesop.core.skills.suggestion_collector import SkillSuggestion, SkillSuggestionCollector


class TestSkillSuggestion:
    """Test SkillSuggestion dataclass."""

    def test_creation(self):
        sug = SkillSuggestion(
            id="sug_1",
            pattern_steps=["step1", "step2"],
            success_rate=0.8,
            occurrences=5,
            suggested_name="test-workflow",
        )
        assert sug.id == "sug_1"
        assert sug.pattern_steps == ["step1", "step2"]
        assert sug.status == "pending"
        assert sug.confidence == pytest.approx(0.5)

    def test_to_dict(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        sug = SkillSuggestion(
            id="sug_1",
            pattern_steps=["a"],
            success_rate=0.5,
            occurrences=1,
            suggested_name="n",
            suggested_description="d",
            confidence=0.7,
            context_tags=["t"],
            status="pending",
            created_at=dt,
            skill_id=None,
        )
        d = sug.to_dict()
        assert d["id"] == "sug_1"
        assert d["confidence"] == pytest.approx(0.7)
        assert d["created_at"] == "2026-01-01T12:00:00"

    def test_from_dict(self):
        d = {
            "id": "sug_1",
            "pattern_steps": ["a"],
            "success_rate": 0.5,
            "occurrences": 1,
            "suggested_name": "n",
            "suggested_description": "d",
            "confidence": 0.7,
            "context_tags": ["t"],
            "status": "created",
            "created_at": "2026-01-01T12:00:00",
            "skill_id": "skill/1",
        }
        sug = SkillSuggestion.from_dict(d)
        assert sug.id == "sug_1"
        assert sug.status == "created"
        assert sug.skill_id == "skill/1"

    def test_from_sequence_pattern(self):
        pattern = MagicMock()
        pattern.sequence_hash = "abc123"
        pattern.steps = ["read:file", "edit:code", "write:test"]
        pattern.success_rate = 0.9
        pattern.total_count = 10
        pattern.context_tags = ["python", "testing"]

        sug = SkillSuggestion.from_sequence_pattern(pattern)
        assert sug.id == "sug_abc123"
        assert sug.success_rate == pytest.approx(0.9)
        assert sug.occurrences == 10
        assert "python" in sug.suggested_description

    def test_infer_name(self):
        assert SkillSuggestion._infer_name([]) == "auto-workflow"
        assert SkillSuggestion._infer_name(["read:file"]) == "file"
        name = SkillSuggestion._infer_name(["read:config", "edit:settings", "write:output"])
        assert "config" in name

    def test_infer_name_long(self):
        steps = ["a:b" * 20] * 5
        name = SkillSuggestion._infer_name(steps)
        assert len(name) <= 40

    def test_infer_description(self):
        desc = SkillSuggestion._infer_description(["a", "b"], ["tag1"])
        assert "Auto-detected workflow" in desc
        assert "tag1" in desc

    def test_infer_description_no_tags(self):
        desc = SkillSuggestion._infer_description(["a", "b"], [])
        assert "Auto-detected workflow" in desc
        assert "(" not in desc


class TestSkillSuggestionCollector:
    """Test SkillSuggestionCollector lifecycle."""

    def test_init_creates_directory(self, tmp_path: Path):
        SkillSuggestionCollector(storage_dir=tmp_path)
        assert tmp_path.exists()

    def test_add_from_pattern(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a", "b"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        sug = collector.add_from_pattern(pattern)
        assert sug is not None
        assert sug.id == "sug_abc"
        assert collector.get("sug_abc") is not None

    def test_add_dismissed_pattern_returns_none(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        collector.add_from_pattern(pattern)
        collector.dismiss("sug_abc")

        result = collector.add_from_pattern(pattern)
        assert result is None

    def test_get_pending(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        collector.add_from_pattern(pattern)
        pending = collector.get_pending()
        assert len(pending) == 1
        assert pending[0].id == "sug_abc"

    def test_should_prompt(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        assert collector.should_prompt(threshold=3) is False

        for i in range(3):
            pattern = MagicMock()
            pattern.sequence_hash = f"abc{i}"
            pattern.steps = ["a"]
            pattern.success_rate = 0.8
            pattern.total_count = 5
            pattern.context_tags = []
            collector.add_from_pattern(pattern)

        assert collector.should_prompt(threshold=3) is True

    def test_dismiss(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        collector.add_from_pattern(pattern)
        collector.dismiss("sug_abc")
        assert collector.get("sug_abc").status == "dismissed"
        assert collector.get_pending() == []

    def test_dismiss_all(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        for i in range(2):
            pattern = MagicMock()
            pattern.sequence_hash = f"abc{i}"
            pattern.steps = ["a"]
            pattern.success_rate = 0.8
            pattern.total_count = 5
            pattern.context_tags = []
            collector.add_from_pattern(pattern)

        count = collector.dismiss_all()
        assert count == 2
        assert collector.get_pending() == []

    def test_mark_created(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        collector.add_from_pattern(pattern)
        collector.mark_created("sug_abc", "my/skill")
        sug = collector.get("sug_abc")
        assert sug.status == "created"
        assert sug.skill_id == "my/skill"

    def test_get_stats(self, tmp_path: Path):
        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        collector.add_from_pattern(pattern)
        stats = collector.get_stats()
        assert stats["total"] == 1
        assert stats["pending"] == 1
        assert stats["created"] == 0
        assert stats["dismissed"] == 0
        assert stats["will_prompt"] is False

    def test_persistence(self, tmp_path: Path):
        collector1 = SkillSuggestionCollector(storage_dir=tmp_path)
        pattern = MagicMock()
        pattern.sequence_hash = "abc"
        pattern.steps = ["a"]
        pattern.success_rate = 0.8
        pattern.total_count = 5
        pattern.context_tags = []

        collector1.add_from_pattern(pattern)

        collector2 = SkillSuggestionCollector(storage_dir=tmp_path)
        assert collector2.get("sug_abc") is not None
        assert collector2.get("sug_abc").status == "pending"

    def test_persistence_skips_corrupted_lines(self, tmp_path: Path):
        storage_file = tmp_path / "skill_candidates.jsonl"
        storage_file.write_text(
            'not json\n{"id": "sug_x", "pattern_steps": [], "success_rate": 0.5, "occurrences": 1, "suggested_name": "n", "created_at": "2026-01-01T12:00:00"}\n'
        )

        collector = SkillSuggestionCollector(storage_dir=tmp_path)
        assert collector.get("sug_x") is not None
        assert collector.get("missing") is None
