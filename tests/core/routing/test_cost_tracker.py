"""Tests for cost_tracker.py."""

from pathlib import Path

import pytest

from vibesop.core.routing.cost_tracker import (
    TriageCallRecord,
    TriageCostTracker,
    _estimate_cost,
)


class TestEstimateCost:
    """Tests for _estimate_cost function."""

    def test_exact_model_match(self):
        cost = _estimate_cost("claude-3-5-haiku-20241022", 1000, 500)
        # (1000 * 0.80 + 500 * 4.00) / 1_000_000 = 0.0028
        assert cost == pytest.approx(0.0028)

    def test_prefix_model_match(self):
        cost = _estimate_cost("claude-3-5-sonnet-20241022-beta", 2000, 1000)
        # (2000 * 3.00 + 1000 * 15.00) / 1_000_000 = 0.021
        assert cost == pytest.approx(0.021)

    def test_unknown_model_uses_default_pricing(self):
        cost = _estimate_cost("unknown-model", 1000000, 1000000)
        # (1M * 1.00 + 1M * 3.00) / 1_000_000 = 4.00
        assert cost == pytest.approx(4.0)

    def test_openai_model(self):
        cost = _estimate_cost("gpt-4o-mini", 500, 200)
        # (500 * 0.15 + 200 * 0.60) / 1_000_000 = 0.000195
        assert cost == pytest.approx(0.000195)

    def test_zero_tokens(self):
        cost = _estimate_cost("claude-3-5-haiku-20241022", 0, 0)
        assert cost == 0.0


class TestTriageCostTracker:
    """Tests for TriageCostTracker."""

    def test_record_creates_log_file(self, tmp_path: Path):
        tracker = TriageCostTracker(storage_dir=tmp_path)
        tracker.record("claude-3-5-haiku-20241022", 100, 50, "test query", "test-skill")
        assert (tmp_path / "ai_triage_log.jsonl").exists()

    def test_record_returns_triage_call_record(self, tmp_path: Path):
        tracker = TriageCostTracker(storage_dir=tmp_path)
        record = tracker.record("gpt-4o", 200, 100, "hello", None)
        assert isinstance(record, TriageCallRecord)
        assert record.model == "gpt-4o"
        assert record.input_tokens == 200
        assert record.output_tokens == 100
        assert record.total_tokens == 300
        assert record.estimated_cost_usd > 0
        assert record.query == "hello"
        assert record.selected_skill is None

    def test_multiple_records_appended(self, tmp_path: Path):
        tracker = TriageCostTracker(storage_dir=tmp_path)
        tracker.record("claude-3-5-haiku-20241022", 10, 5, "q1", "s1")
        tracker.record("claude-3-5-haiku-20241022", 20, 10, "q2", "s2")
        content = (tmp_path / "ai_triage_log.jsonl").read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2

    def test_get_monthly_cost_empty(self, tmp_path: Path):
        tracker = TriageCostTracker(storage_dir=tmp_path)
        assert tracker.get_monthly_cost() == 0.0

    def test_get_monthly_cost_sums_records(self, tmp_path: Path):
        tracker = TriageCostTracker(storage_dir=tmp_path)
        tracker.record("claude-3-5-haiku-20241022", 1000, 500, "q1", "s1")
        tracker.record("claude-3-5-haiku-20241022", 2000, 1000, "q2", "s2")
        cost = tracker.get_monthly_cost()
        # (3000 * 0.80 + 1500 * 4.00) / 1_000_000 = 0.0084
        assert cost == pytest.approx(0.0084)

    def test_log_file_handles_io_error_gracefully(self, tmp_path: Path, monkeypatch):
        tracker = TriageCostTracker(storage_dir=tmp_path)
        # Make the log path a directory to force IO error
        (tmp_path / "ai_triage_log.jsonl").mkdir()
        # Should not raise
        record = tracker.record("test-model", 10, 10, "q", None)
        assert record.total_tokens == 20
