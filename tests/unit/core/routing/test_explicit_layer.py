"""Tests for explicit override layer (Layer 0)."""

from __future__ import annotations

from vibesop.core.routing.explicit_layer import check_explicit_override


class TestCheckExplicitOverride:
    """Test explicit skill override detection."""

    def test_prefix_override(self) -> None:
        """!skill_id prefix routes directly to the skill."""
        candidates = [{"id": "systematic-debugging"}, {"id": "review"}]
        skill_id, cleaned = check_explicit_override(
            "!systematic-debugging debug this error", candidates
        )
        assert skill_id == "systematic-debugging"
        assert cleaned == "debug this error"

    def test_prefix_override_invalid_skill(self) -> None:
        """!skill_id with unknown skill returns None."""
        candidates = [{"id": "review"}]
        skill_id, cleaned = check_explicit_override("!unknown-skill do something", candidates)
        assert skill_id is None
        assert cleaned is None

    def test_verb_use_override(self) -> None:
        """'use <skill_id>' triggers explicit override."""
        candidates = [{"id": "omx/ralph"}, {"id": "review"}]
        skill_id, cleaned = check_explicit_override("use omx/ralph to implement this", candidates)
        assert skill_id == "omx/ralph"
        assert cleaned == "use omx/ralph to implement this"

    def test_verb_run_override(self) -> None:
        """'run <skill_id>' triggers explicit override."""
        candidates = [{"id": "benchmark"}, {"id": "review"}]
        skill_id, _cleaned = check_explicit_override("Run benchmark on this code", candidates)
        assert skill_id == "benchmark"

    def test_verb_execute_override(self) -> None:
        """'execute <skill_id>' triggers explicit override."""
        candidates = [{"id": "deploy"}]
        skill_id, _ = check_explicit_override("execute deploy now", candidates)
        assert skill_id == "deploy"

    def test_verb_try_override(self) -> None:
        """'try <skill_id>' triggers explicit override."""
        candidates = [{"id": "tdd"}]
        skill_id, _ = check_explicit_override("try tdd for this feature", candidates)
        assert skill_id == "tdd"

    def test_verb_with_colon(self) -> None:
        """'use skill:<skill_id>' extracts skill after colon."""
        candidates = [{"id": "systematic-debugging"}]
        skill_id, _ = check_explicit_override("use skill:systematic-debugging", candidates)
        assert skill_id == "systematic-debugging"

    def test_verb_invalid_skill(self) -> None:
        """Verb pattern with unknown skill returns None."""
        candidates = [{"id": "review"}]
        skill_id, cleaned = check_explicit_override("use unknown-skill to do something", candidates)
        assert skill_id is None
        assert cleaned is None

    def test_no_explicit_override(self) -> None:
        """Plain query without prefix or verb returns None."""
        candidates = [{"id": "review"}]
        skill_id, cleaned = check_explicit_override("help me review this code", candidates)
        assert skill_id is None
        assert cleaned is None

    def test_empty_candidates(self) -> None:
        """Empty candidates list returns None for any query."""
        skill_id, cleaned = check_explicit_override("!systematic-debugging help", [])
        assert skill_id is None
        assert cleaned is None

    def test_prefix_with_multiple_spaces(self) -> None:
        """Prefix with extra spaces should still work."""
        candidates = [{"id": "debug"}]
        skill_id, cleaned = check_explicit_override("!debug    fix this error", candidates)
        assert skill_id == "debug"
        assert cleaned == "fix this error"
