"""Tests for explicit override layer."""

import pytest

from vibesop.core.routing.explicit_layer import check_explicit_override


@pytest.fixture
def candidates():
    return [
        {"id": "systematic-debugging", "namespace": "builtin"},
        {"id": "gstack/qa", "namespace": "gstack"},
        {"id": "omx/deep-interview", "namespace": "omx"},
        {"id": "omx/ralph", "namespace": "omx"},
    ]


def test_explicit_prefix_override(candidates):
    """!skill_id should override routing."""
    skill_id, cleaned = check_explicit_override("!systematic-debugging help me debug", candidates)
    assert skill_id == "systematic-debugging"
    assert cleaned == "help me debug"


def test_explicit_prefix_with_namespace(candidates):
    """!omx/deep-interview should work with namespace."""
    skill_id, cleaned = check_explicit_override("!omx/deep-interview build app", candidates)
    assert skill_id == "omx/deep-interview"
    assert cleaned == "build app"


def test_use_verb_override(candidates):
    """'use <skill>' should trigger override."""
    skill_id, _cleaned = check_explicit_override("use omx/ralph to implement this", candidates)
    assert skill_id == "omx/ralph"


def test_run_verb_override(candidates):
    """'run <skill>' should trigger override."""
    skill_id, _cleaned = check_explicit_override("run gstack/qa on my site", candidates)
    assert skill_id == "gstack/qa"


def test_execute_verb_override(candidates):
    """'execute <skill>' should trigger override."""
    skill_id, _cleaned = check_explicit_override("execute systematic-debugging", candidates)
    assert skill_id == "systematic-debugging"


def test_try_verb_override(candidates):
    """'try <skill>' should trigger override."""
    skill_id, _cleaned = check_explicit_override("try omx/deep-interview", candidates)
    assert skill_id == "omx/deep-interview"


def test_invalid_skill_no_override(candidates):
    """Non-existent skill should not trigger override."""
    skill_id, cleaned = check_explicit_override("!nonexistent-skill test", candidates)
    assert skill_id is None
    assert cleaned is None


def test_no_explicit_pattern(candidates):
    """Query without explicit patterns should return None."""
    skill_id, cleaned = check_explicit_override("help me debug this error", candidates)
    assert skill_id is None
    assert cleaned is None
