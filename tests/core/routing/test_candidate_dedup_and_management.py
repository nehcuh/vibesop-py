"""Tests for candidate deduplication and management-only marking."""

from __future__ import annotations

import json
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

    def test_skips_definition_whose_source_file_is_missing(
        self, candidate_manager: Any, tmp_path: Path
    ) -> None:
        ghost = _make_definition("ghost-skill")
        ghost.source_file = tmp_path / "nope" / "SKILL.md"
        live = _make_definition("live-skill")
        live_path = tmp_path / "live" / "SKILL.md"
        live_path.parent.mkdir()
        live_path.write_text("# live\n", encoding="utf-8")
        live.source_file = live_path
        candidates = _get_candidates(candidate_manager, {"ghost-skill": ghost, "live-skill": live})
        assert [c["id"] for c in candidates] == ["live-skill"]

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
        from vibesop.core.matching.strategies import is_management_skill_id

        definitions = {
            "slash-route": _make_definition("slash-route"),
            "slash-help": _make_definition("slash-help"),
            "slash-install": _make_definition("slash-install"),
            "Slash-Analyze": _make_definition("Slash-Analyze"),
            "builtin-slash-list": _make_definition("builtin-slash-list"),
            "gstack/review": _make_definition("gstack/review", namespace="gstack"),
        }
        candidates = _get_candidates(candidate_manager, definitions)
        for c in candidates:
            # The oracle is the shared recognizer, not a hand-rolled prefix
            # check — the two had drifted before (20260831 review B-F7/A-F7).
            if is_management_skill_id(c["id"]):
                assert c["management_only"] is True, f"{c['id']} should be management_only"
            else:
                assert c["management_only"] is False, f"{c['id']} should NOT be management_only"


class TestPinSearchPaths:
    """Hermetic-universe seam (gate45 P1): pin_search_paths pins discovery."""

    @staticmethod
    def _write_skill(root: Path, skill_id: str, name: str) -> Path:
        skill_dir = root / skill_id.replace("/", "-")
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"id: {skill_id}\n"
            f"name: {name}\n"
            f"description: {name} fixture skill\n"
            "tags: [test]\n"
            "version: 1.0.0\n"
            "intent: test fixture\n"
            "namespace: bench\n"
            "type: prompt\n"
            "---\n"
            "# test\n",
            encoding="utf-8",
        )
        return skill_dir.parent

    def test_empty_pin_is_rejected(self, tmp_path: Path) -> None:
        from vibesop.core.routing.candidate_manager import CandidateManager

        cm = CandidateManager(project_root=tmp_path)
        with pytest.raises(ValueError, match="empty pin"):
            cm.pin_search_paths([])

    def test_pins_universe_and_never_persists_disk_cache(self, tmp_path: Path) -> None:
        from vibesop.core.routing.candidate_manager import CandidateManager

        universe = tmp_path / "universe"
        universe.mkdir()
        self._write_skill(universe, "bench/alpha", "alpha")
        self._write_skill(universe, "bench/beta", "beta")

        cm = CandidateManager(project_root=tmp_path)
        cm.pin_search_paths([universe])

        # get_cached_candidates is the real read path (router/eval use it);
        # get_candidates alone never touches the disk cache, so asserting
        # only on it would pin nothing (review MINOR-2: the earlier version
        # stayed green with the bypass flag mutated off).
        candidates = cm.get_cached_candidates()
        ids = {c["id"] for c in candidates}
        # Exactly the pinned universe — no project/user/external discovery,
        # no defaults leaking through the append path.
        assert ids == {"bench/alpha", "bench/beta"}

        # Write side: a pinned pool is never persisted.
        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        assert not cache_path.exists()

    def test_disk_cache_with_matching_hash_is_ignored_on_read_path(self, tmp_path: Path) -> None:
        from vibesop.core.routing.candidate_manager import CandidateManager

        universe = tmp_path / "universe"
        universe.mkdir()
        self._write_skill(universe, "bench/alpha", "alpha")

        cm = CandidateManager(project_root=tmp_path)
        cm.pin_search_paths([universe])

        # Plant a stale cache whose paths_hash REALLY matches the pinned
        # universe — exactly what a leftover from a pre-pin run looks like.
        # Without the bypass flag the reload path serves the ghost
        # (mutation-verified by review).
        real_hash = cm._compute_paths_hash([universe])
        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text(
            json.dumps({"paths_hash": real_hash, "candidates": [{"id": "stale/ghost"}]}),
            encoding="utf-8",
        )

        ids = {c["id"] for c in cm.get_cached_candidates()}
        assert "stale/ghost" not in ids
        assert ids == {"bench/alpha"}


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
