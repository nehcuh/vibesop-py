"""AgentRuntime session_id seeding — gates W5.1 Task 1.2.

Verifies that ``AgentRuntime.handle_query`` no longer defaults to the literal
``"default"`` session_id (which bypassed process_identity and emitted
unattributed spans). Now mints a UUID at entry when None and seeds
process_identity so descendant spans via TraceContext inherit it.
"""

from __future__ import annotations

import uuid

import pytest

from vibesop.agent.runtime.agent_runtime import AgentRuntime
from vibesop.core.observability.process_identity import (
    get_process_session_id,
)


@pytest.fixture(autouse=True)
def _reset_process_session() -> pytest.MonkeyPatch:
    """Reset module-level session_id between tests so they don't leak."""
    import vibesop.core.observability.process_identity as pi

    original = pi._process_session_id
    pi._process_session_id = None
    yield
    pi._process_session_id = original


class TestSessionSeeding:
    def test_handle_query_mints_session_id_when_none(self) -> None:
        assert get_process_session_id() is None
        runtime = AgentRuntime()
        runtime.handle_query("review my code")

        sid = get_process_session_id()
        assert sid is not None
        # Must be a valid UUID string
        uuid.UUID(sid)

    def test_handle_query_uses_explicit_session_id(self) -> None:
        runtime = AgentRuntime()
        runtime.handle_query("review my code", session_id="caller-provided-sid")

        assert get_process_session_id() == "caller-provided-sid"

    def test_handle_query_seeds_process_identity_for_descendants(self) -> None:
        runtime = AgentRuntime()
        runtime.handle_query("review my code")

        sid = get_process_session_id()
        assert sid is not None

        # Second call with no session_id must NOT re-seed — process identity
        # is sticky per-process (matches CLI pattern at main.py:734). Per-call
        # re-seeding would orphan async spans onto whichever UUID was last
        # written (architect review BLOCK).
        first_sid = sid
        runtime.handle_query("another query")
        second_sid = get_process_session_id()
        assert second_sid == first_sid, "process identity must be sticky once seeded"

    def test_handle_query_for_hook_mints_session_id(self) -> None:
        assert get_process_session_id() is None
        runtime = AgentRuntime()
        runtime.handle_query_for_hook("review my code", platform="claude-code")

        sid = get_process_session_id()
        assert sid is not None
        uuid.UUID(sid)

    def test_session_id_appears_in_emit_via_explicit_value(self, tmp_path) -> None:
        """When caller passes explicit session_id, it propagates to the trace span.

        Verifies the explicit-kwarg-wins path: a hook wrapper correlating spans
        across boundaries relies on this.
        """
        runtime = AgentRuntime(project_root=tmp_path)
        runtime.handle_query("review my code", session_id="correlation-sid")

        assert get_process_session_id() == "correlation-sid"
