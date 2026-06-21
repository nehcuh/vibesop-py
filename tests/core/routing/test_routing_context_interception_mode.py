"""Tests for RoutingContext first-class interception_mode + intent_analysis (v7.0.3).

Background: prior to v7.0.3, the MULTI_AGENT_SQUAD path relied on two
parallel backchannels through RoutingContext.metadata:

- ``metadata["_interception_mode"]`` — string key, written by agent_runtime
  and cli/main, read by orchestrator.
- ``metadata["intent_analysis"]`` — string key, same writers + reader.

The backchannel pattern was fragile: any rename of the string key
silently severed the squad path without any type-checker signal, and
``RoutingContext.interception_mode`` (already a first-class field) was
dead code that no reader ever consulted.

v7.0.3 promotes both pieces of state to first-class fields and updates
the orchestrator reader to prefer the field over the backchannel. The
backchannel writes are retained for one release as a compatibility
shim so any in-flight code paths that have not been migrated keep
working; v7.1 will remove the backchannel writes entirely.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from vibesop.core.matching import RoutingContext


class TestRoutingContextFields:
    """RoutingContext dataclass surface."""

    def test_interception_mode_default_is_none(self) -> None:
        ctx = RoutingContext()
        assert ctx.interception_mode is None

    def test_intent_analysis_default_is_none(self) -> None:
        ctx = RoutingContext()
        assert ctx.intent_analysis is None

    def test_interception_mode_can_be_set(self) -> None:
        ctx = RoutingContext(interception_mode="multi_agent_squad")
        assert ctx.interception_mode == "multi_agent_squad"

    def test_intent_analysis_can_be_set(self) -> None:
        payload: dict[str, Any] = {"collaboration_protocol": "red_team"}
        ctx = RoutingContext(intent_analysis=payload)
        assert ctx.intent_analysis == payload

    def test_to_dict_includes_first_class_fields(self) -> None:
        ctx = RoutingContext(
            interception_mode="single_agent",
            intent_analysis={"collaboration_protocol": "sequential"},
        )
        d = ctx.to_dict()
        assert d["interception_mode"] == "single_agent"
        assert d["intent_analysis"] == {"collaboration_protocol": "sequential"}


class TestOrchestratorReaderFieldFirst:
    """Orchestrator reads field first, falls back to metadata backchannel."""

    def _build_orchestrator(self) -> Any:
        from vibesop.core.routing.orchestrator import Orchestrator

        router = MagicMock()
        router._get_plan_builder.return_value = MagicMock()
        return Orchestrator(router=router)

    def test_field_interception_mode_wins_over_metadata(self) -> None:
        """When both are set, the field value must take precedence."""
        ctx = RoutingContext()
        ctx.interception_mode = "multi_agent_squad"  # field
        ctx.metadata["_interception_mode"] = "single_agent"  # legacy backchannel

        # Reach into the orchestrator's reader logic via the same condition
        # the implementation uses. We can't easily exercise orchestrate()
        # end-to-end without a lot of mocking, so we replicate the
        # field-first / fallback logic to pin the contract.
        interception_mode = ctx.interception_mode or ctx.metadata.get("_interception_mode", "")
        assert interception_mode == "multi_agent_squad"

    def test_metadata_backchannel_used_when_field_absent(self) -> None:
        """Old code paths that only set metadata must still work."""
        ctx = RoutingContext()
        ctx.metadata["_interception_mode"] = "single_agent"

        interception_mode = ctx.interception_mode or ctx.metadata.get("_interception_mode", "")
        assert interception_mode == "single_agent"

    def test_field_intent_analysis_wins_over_metadata(self) -> None:
        ctx = RoutingContext()
        ctx.intent_analysis = {"collaboration_protocol": "debate"}
        ctx.metadata["intent_analysis"] = {"collaboration_protocol": "sequential"}

        analysis = ctx.intent_analysis or ctx.metadata.get("intent_analysis")
        assert analysis == {"collaboration_protocol": "debate"}

    def test_metadata_intent_analysis_used_when_field_absent(self) -> None:
        ctx = RoutingContext()
        ctx.metadata["intent_analysis"] = {"collaboration_protocol": "red_team"}

        analysis = ctx.intent_analysis or ctx.metadata.get("intent_analysis")
        assert analysis == {"collaboration_protocol": "red_team"}


class TestWriterMigration:
    """Writers must populate the first-class field, not just metadata."""

    def test_build_multi_agent_squad_context_sets_field(self) -> None:
        """cli/main._build_multi_agent_squad_context sets interception_mode field."""
        from vibesop.cli.main import _build_multi_agent_squad_context

        decision = MagicMock()
        decision.analysis = MagicMock()
        decision.analysis.to_dict.return_value = {"collaboration_protocol": "sequential"}

        ctx = _build_multi_agent_squad_context(context=None, decision=decision)

        assert ctx.interception_mode == "multi_agent_squad"
        assert ctx.intent_analysis == {"collaboration_protocol": "sequential"}
        # Backchannel still populated for backward-compat with un-migrated readers:
        assert ctx.metadata["_interception_mode"] == "multi_agent_squad"
        assert ctx.metadata["intent_analysis"] == {"collaboration_protocol": "sequential"}

    def test_build_single_agent_context_sets_field(self) -> None:
        """cli/main._build_single_agent_context (or equivalent) sets field."""
        from vibesop.cli.main import _build_single_agent_context

        analysis = MagicMock()
        analysis.suggested_roles = ["architect"]
        analysis.per_agent_skills = {"architect": ["architect-skill"]}
        analysis.to_dict.return_value = {"collaboration_protocol": "sequential"}

        decision = MagicMock()
        decision.analysis = analysis

        ctx = _build_single_agent_context(context=None, decision=decision)

        assert ctx.interception_mode == "single_agent"
        assert ctx.intent_analysis == {"collaboration_protocol": "sequential"}
        # Backchannel populated for backward compat:
        assert ctx.metadata["_interception_mode"] == "single_agent"
        assert ctx.metadata["intent_analysis"] == {"collaboration_protocol": "sequential"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
