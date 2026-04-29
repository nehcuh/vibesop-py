"""Tests for vibesop.core.conversation module."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from vibesop.core.conversation import ConversationContext, ConversationTurn

if TYPE_CHECKING:
    from pathlib import Path


class TestConversationTurn:
    """Test ConversationTurn dataclass."""

    def test_to_dict(self) -> None:
        turn = ConversationTurn(
            query="review my code",
            skill_id="gstack/review",
            timestamp=1234567890.0,
            intent="code_review",
        )
        data = turn.to_dict()
        assert data["query"] == "review my code"
        assert data["skill_id"] == "gstack/review"
        assert data["timestamp"] == 1234567890.0
        assert data["intent"] == "code_review"

    def test_from_dict(self) -> None:
        data = {
            "query": "debug error",
            "skill_id": "superpowers/debug",
            "timestamp": 1234567890.0,
        }
        turn = ConversationTurn.from_dict(data)
        assert turn.query == "debug error"
        assert turn.skill_id == "superpowers/debug"
        assert turn.intent is None

    def test_roundtrip(self) -> None:
        original = ConversationTurn(
            query="test",
            skill_id="a/b",
            timestamp=1.0,
        )
        restored = ConversationTurn.from_dict(original.to_dict())
        assert restored.query == original.query
        assert restored.skill_id == original.skill_id


class TestConversationContext:
    """Test ConversationContext persistence and logic."""

    def test_init_generates_id(self) -> None:
        ctx = ConversationContext()
        assert ctx.conversation_id
        assert len(ctx.conversation_id) == 8

    def test_init_with_custom_id(self) -> None:
        ctx = ConversationContext(conversation_id="my-conv")
        assert ctx.conversation_id == "my-conv"

    def test_add_turn_and_get_history(self, tmp_path: Path) -> None:
        ctx = ConversationContext(
            conversation_id="test",
            storage_dir=tmp_path,
        )
        ctx.add_turn("query1", skill_id="a/b")
        ctx.add_turn("query2", skill_id="c/d")

        history = ctx.get_history()
        assert len(history) == 2
        assert history[0].query == "query1"
        assert history[1].query == "query2"
        assert history[1].skill_id == "c/d"

    def test_get_last_turn(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        assert ctx.get_last_turn() is None

        ctx.add_turn("q1", skill_id="a")
        last = ctx.get_last_turn()
        assert last is not None
        assert last.query == "q1"
        assert last.skill_id == "a"

    def test_get_last_skill(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        assert ctx.get_last_skill() is None

        ctx.add_turn("q1", skill_id="x/y")
        assert ctx.get_last_skill() == "x/y"

    def test_history_truncation(self, tmp_path: Path) -> None:
        ctx = ConversationContext(
            storage_dir=tmp_path,
            max_history=3,
        )
        for i in range(5):
            ctx.add_turn(f"q{i}", skill_id=f"s{i}")

        history = ctx.get_history()
        assert len(history) == 3
        assert history[0].query == "q2"
        assert history[-1].query == "q4"

    def test_persistence(self, tmp_path: Path) -> None:
        ctx = ConversationContext(
            conversation_id="persist-test",
            storage_dir=tmp_path,
        )
        ctx.add_turn("hello", skill_id="greet")

        # Load in a new instance
        ctx2 = ConversationContext(
            conversation_id="persist-test",
            storage_dir=tmp_path,
        )
        history = ctx2.get_history()
        assert len(history) == 1
        assert history[0].query == "hello"
        assert history[0].skill_id == "greet"

    # ------------------------------------------------------------------
    # Follow-up detection
    # ------------------------------------------------------------------

    def test_is_follow_up_continuation(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review code", skill_id="review")

        is_follow, ftype = ctx.is_follow_up("continue")
        assert is_follow is True
        assert ftype == "continuation"

    def test_is_follow_up_retry(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("debug", skill_id="debug")

        is_follow, ftype = ctx.is_follow_up("try again")
        assert is_follow is True
        assert ftype == "retry"

    def test_is_follow_up_alternative(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("analyze", skill_id="analyze")

        is_follow, ftype = ctx.is_follow_up("another way")
        assert is_follow is True
        assert ftype == "alternative"

    def test_is_follow_up_clarification(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review", skill_id="review")

        is_follow, ftype = ctx.is_follow_up("what do you mean")
        assert is_follow is True
        assert ftype == "clarification"

    def test_is_follow_up_chinese(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review code", skill_id="review")

        is_follow, ftype = ctx.is_follow_up("继续")
        assert is_follow is True
        assert ftype == "continuation"

    def test_is_not_follow_up(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review", skill_id="review")

        is_follow, ftype = ctx.is_follow_up("completely new topic about deployment")
        assert is_follow is False
        assert ftype is None

    def test_follow_up_timeout(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        ctx = ConversationContext(
            storage_dir=tmp_path,
            follow_up_timeout=0.1,
        )
        ctx.add_turn("review", skill_id="review")

        # Simulate time passing without real sleep
        with patch("time.time", return_value=time.time() + 0.2):
            is_follow, ftype = ctx.is_follow_up("continue")
            assert is_follow is False
            assert ftype is None

    def test_follow_up_empty_query(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review", skill_id="review")

        is_follow, _ftype = ctx.is_follow_up("")
        assert is_follow is False

    def test_follow_up_pronoun_reference(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review code", skill_id="review")

        is_follow, ftype = ctx.is_follow_up("do it")
        assert is_follow is True
        assert ftype == "pronoun_reference"

    def test_follow_up_pronoun_relaxed_length(self, tmp_path: Path) -> None:
        """Pronoun detection now works for queries up to 15 words."""
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review code", skill_id="review")

        is_follow, ftype = ctx.is_follow_up("can you do it for me please")
        assert is_follow is True
        assert ftype == "pronoun_reference"

    def test_follow_up_semantic_similarity(self, tmp_path: Path) -> None:
        """Topically similar queries are detected as semantic continuation."""
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("debug database connection error", skill_id="debug")

        is_follow, ftype = ctx.is_follow_up("database connection keeps failing")
        assert is_follow is True
        assert ftype == "semantic_continuation"

    def test_not_follow_up_semantically_different(self, tmp_path: Path) -> None:
        """Unrelated queries are not follow-ups even with history."""
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("debug database connection error", skill_id="debug")

        is_follow, ftype = ctx.is_follow_up("deploy to production")
        assert is_follow is False
        assert ftype is None

    def test_build_contextual_query_semantic(self, tmp_path: Path) -> None:
        """Semantic follow-ups inject only missing context terms."""
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("debug database connection", skill_id="debug")

        enriched = ctx.build_contextual_query("database connection keeps failing")
        assert enriched is not None
        # "database" and "connection" already present in current query;
        # only "debug" is injected from history.
        assert enriched == "database connection keeps failing debug"

    # ------------------------------------------------------------------
    # Contextual query building
    # ------------------------------------------------------------------

    def test_build_contextual_query_continuation(self, tmp_path: Path) -> None:
        """Continuation follow-ups inject only missing context terms."""
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review my code", skill_id="review")

        enriched = ctx.build_contextual_query("continue")
        assert enriched is not None
        # "continue" is the current query; missing terms from history are
        # "code", "my", "review" (sorted alphabetically).
        assert enriched == "continue code my review"

    def test_build_contextual_query_not_follow_up(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("review", skill_id="review")

        enriched = ctx.build_contextual_query("deploy to production")
        assert enriched is None

    def test_build_contextual_query_no_history(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        enriched = ctx.build_contextual_query("continue")
        assert enriched is None

    # ------------------------------------------------------------------
    # Routing hints
    # ------------------------------------------------------------------

    def test_get_routing_hints(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("q1", skill_id="a")

        hints = ctx.get_routing_hints()
        assert hints["previous_skill"] == "a"
        assert hints["previous_query"] == "q1"

    def test_get_routing_hints_sticky_skill(self, tmp_path: Path) -> None:
        ctx = ConversationContext(storage_dir=tmp_path)
        ctx.add_turn("q1", skill_id="debug")
        ctx.add_turn("q2", skill_id="debug")
        ctx.add_turn("q3", skill_id="debug")

        hints = ctx.get_routing_hints()
        assert hints["sticky_skill"] == "debug"

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def test_cleanup_expired(self, tmp_path: Path) -> None:
        storage = tmp_path / "conversations"
        storage.mkdir()

        # Create an old file
        old_file = storage / "old.json"
        old_file.write_text('{"turns": []}')

        # Create a recent file
        recent_file = storage / "recent.json"
        recent_file.write_text('{"turns": []}')

        removed = ConversationContext.cleanup_expired(
            storage_dir=storage,
            max_age=0.0,  # Everything is "expired"
        )
        assert removed == 2
        assert not old_file.exists()
        assert not recent_file.exists()
