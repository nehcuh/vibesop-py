"""Tests for candidate deduplication and management-only marking."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_definition(
    skill_id: str,
    name: str = "",
    description: str = "",
    intent: str = "",
    tags: list[str] | None = None,
    namespace: str = "builtin",
    triggers: list[str] | None = None,
    trigger_when: str = "",
) -> Any:
    meta = MagicMock()
    meta.id = skill_id
    meta.name = name or skill_id
    meta.description = description
    meta.intent = intent
    meta.tags = tags
    meta.triggers = triggers or []
    meta.trigger_when = trigger_when
    meta.namespace = namespace

    definition = MagicMock()
    definition.metadata = meta
    definition.source_file = None

    return definition


def _get_candidates(cm: Any, definitions: dict) -> list[dict[str, Any]]:
    mock_loader = MagicMock()
    mock_loader.discover_all.return_value = definitions
    cm._skill_loader = mock_loader

    mock_cs = MagicMock()
    mock_cs.return_value.get_p0_skills.return_value = []

    with patch("vibesop.core.optimization.cold_start.get_cold_start_strategy", mock_cs):
        with patch(
            "vibesop.core.skills.config_manager.SkillConfigManager.get_skill_config",
            return_value=None,
        ):
            return cm.get_candidates()


@pytest.fixture
def candidate_manager(tmp_path: Path) -> Any:
    from vibesop.core.routing.candidate_manager import CandidateManager

    cm = CandidateManager(project_root=tmp_path)
    return cm


class TestDeduplication:
    def test_deduplicates_same_id_different_case(self, candidate_manager: Any) -> None:
        definitions = {
            "gstack/office-hours": _make_definition("gstack/office-hours", name="Office Hours"),
            "gstack/Office-Hours": _make_definition(
                "gstack/Office-Hours", name="Office Hours Duplicate"
            ),
        }
        candidates = _get_candidates(candidate_manager, definitions)
        ids = [c["id"] for c in candidates]
        assert len(ids) == 1
        assert ids[0] == "gstack/office-hours"

    def test_deduplicates_across_namespaces(self, candidate_manager: Any) -> None:
        definitions = {
            "slash-route": _make_definition("slash-route", name="Slash Route"),
            "slash-Route": _make_definition("slash-Route", name="Slash Route Dup"),
        }
        candidates = _get_candidates(candidate_manager, definitions)
        ids = [c["id"] for c in candidates]
        assert len(ids) == 1

    def test_keeps_different_skills(self, candidate_manager: Any) -> None:
        definitions = {
            "gstack/office-hours": _make_definition("gstack/office-hours"),
            "gstack/review": _make_definition("gstack/review"),
            "superpowers/tdd": _make_definition("superpowers/tdd", namespace="superpowers"),
        }
        candidates = _get_candidates(candidate_manager, definitions)
        assert len(candidates) == 3


class TestManagementOnlyMarking:
    def test_slash_route_is_management_only(self, candidate_manager: Any) -> None:
        definitions = {
            "builtin/slash-route": _make_definition("builtin/slash-route"),
            "gstack/office-hours": _make_definition("gstack/office-hours", namespace="gstack"),
        }
        candidates = _get_candidates(candidate_manager, definitions)
        by_id = {c["id"]: c for c in candidates}
        assert by_id["builtin/slash-route"]["management_only"] is True
        assert by_id["gstack/office-hours"]["management_only"] is False

    def test_slash_prefix_variants_marked(self, candidate_manager: Any) -> None:
        definitions = {
            "slash-route": _make_definition("slash-route"),
            "slash-help": _make_definition("slash-help"),
            "slash-install": _make_definition("slash-install"),
            "gstack/review": _make_definition("gstack/review", namespace="gstack"),
        }
        candidates = _get_candidates(candidate_manager, definitions)
        for c in candidates:
            if c["id"].startswith("slash-"):
                assert c["management_only"] is True, f"{c['id']} should be management_only"
            else:
                assert c["management_only"] is False, f"{c['id']} should NOT be management_only"


class TestTriagePrefilterExclusion:
    def test_management_skills_excluded_from_triage(self) -> None:
        from vibesop.core.routing.triage_service import TriageService

        ts = TriageService(
            config=MagicMock(),
            cost_tracker=MagicMock(),
            prefilter=MagicMock(),
            cache_manager=MagicMock(),
            get_skill_source=MagicMock(return_value="builtin"),
        )

        candidates = [
            {"id": "builtin/slash-route", "management_only": True},
            {"id": "builtin/slash-help", "management_only": True},
            {"id": "gstack/office-hours", "management_only": False},
            {"id": "gstack/review", "management_only": False},
            {"id": "superpowers/tdd", "management_only": False},
        ]

        result = ts.prefilter_ai_triage_candidates("analyze this idea", candidates, max_skills=10)

        ids = [c["id"] for c in result]
        assert "builtin/slash-route" not in ids
        assert "builtin/slash-help" not in ids
        assert "gstack/office-hours" in ids
        assert "gstack/review" in ids

    def test_management_exclusion_with_small_max(self) -> None:
        from vibesop.core.routing.triage_service import TriageService

        ts = TriageService(
            config=MagicMock(),
            cost_tracker=MagicMock(),
            prefilter=MagicMock(),
            cache_manager=MagicMock(),
            get_skill_source=MagicMock(return_value="builtin"),
        )

        candidates = [
            {"id": "builtin/slash-route", "management_only": True, "intent": "routing"},
            {"id": "gstack/office-hours", "management_only": False, "intent": "brainstorm"},
            {"id": "gstack/review", "management_only": False, "intent": "review"},
        ]

        result = ts.prefilter_ai_triage_candidates("brainstorm idea", candidates, max_skills=2)

        ids = [c["id"] for c in result]
        assert "builtin/slash-route" not in ids
        assert len(result) <= 2


class TestTriagePromptV3:
    def test_v3_contains_management_exclusion_rule(self) -> None:
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        prompt = TriagePromptRegistry.get_prompt("v3")
        assert "NEVER select slash-*" in prompt
        assert "management skills" in prompt

    def test_v3_contains_chinese_patterns(self) -> None:
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        prompt = TriagePromptRegistry.get_prompt("v3")
        assert "分析想法" in prompt
        assert "帮我分析" in prompt
        assert "office-hours" in prompt

    def test_default_version_is_v3(self) -> None:
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        assert TriagePromptRegistry.DEFAULT_VERSION == "v3"
