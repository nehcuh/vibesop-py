"""Tests for ultrawork engine."""

import pytest

from vibesop.core.pipeline.ultrawork import TaskTier, UltraworkEngine, UltraworkResult


def test_add_tasks():
    engine = UltraworkEngine("test-1")
    engine.add_task("t1", "Simple task", TaskTier.LOW)
    engine.add_task("t2", "Normal task", TaskTier.STANDARD)
    engine.add_task("t3", "Complex task", TaskTier.THOROUGH)

    assert engine.result.total == 3
    assert engine.result.tier_counts == {"low": 1, "standard": 1, "thorough": 1}


def test_complete_and_fail_tasks():
    engine = UltraworkEngine("test-2")
    engine.add_task("t1", "Task 1")
    engine.add_task("t2", "Task 2")

    engine.complete_task("t1", {"output": "done"})
    engine.fail_task("t2", "Something went wrong")

    assert engine.result.completed == 1
    assert engine.result.failed == 1
    assert engine.result.success is False


def test_success_when_no_failures():
    engine = UltraworkEngine("test-3")
    engine.add_task("t1", "Task 1")
    engine.add_task("t2", "Task 2")

    engine.complete_task("t1", {})
    engine.complete_task("t2", {})

    assert engine.result.success is True


def test_finalize():
    engine = UltraworkEngine("test-4")
    engine.add_task("t1", "Task 1")
    result = engine.finalize()

    assert result.completed_at is not None
    assert result.session_id == "test-4"


def test_to_dict():
    engine = UltraworkEngine("test-5")
    engine.add_task("t1", "Task 1", TaskTier.LOW)
    engine.complete_task("t1", {"key": "value"})
    result = engine.finalize()

    d = result.to_dict()
    assert d["session_id"] == "test-5"
    assert d["total_tasks"] == 1
    assert d["completed"] == 1
    assert d["failed"] == 0
    assert d["success"] is True
    assert d["tiers"]["low"] == 1


def test_save_result(tmp_path):
    engine = UltraworkEngine("test-6")
    engine.add_task("t1", "Task 1")
    engine.complete_task("t1", {})
    result = engine.finalize()

    filepath = result.save(tmp_path)
    assert filepath.exists()
    assert "ultrawork_test-6" in filepath.name
