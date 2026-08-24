"""W5.2 Task 1.3 — _get_candidate_store(scope) helper.

Verifies the helper routes to the correct storage dir based on scope.
Critical: global path must NOT be under ExternalSkillLoader.EXTERNAL_PATHS
(W4 未审不注入 invariant — drafts outside discovery roots).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from vibesop.cli.commands import skill_commands
from vibesop.core.skills.external_loader import ExternalSkillLoader


class TestGetCandidateStoreScope:
    def test_get_candidate_store_project_scope_uses_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """scope='project' → storage dir under cwd."""
        monkeypatch.chdir(tmp_path)
        store = skill_commands._get_candidate_store(scope="project")
        assert store._dir == tmp_path / ".vibe" / "observability"
        assert store._path == tmp_path / ".vibe" / "observability" / "cluster_candidates.jsonl"

    def test_get_candidate_store_global_scope_uses_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """scope='global' → storage dir under ~/.vibe/observability."""
        monkeypatch.setattr(
            skill_commands,
            "_GLOBAL_OBSERVABILITY_DIR",
            tmp_path / "fake_home" / ".vibe" / "observability",
        )
        store = skill_commands._get_candidate_store(scope="global")
        assert store._dir == tmp_path / "fake_home" / ".vibe" / "observability"
        assert store._path.name == "cluster_candidates.jsonl"

    def test_get_candidate_store_default_scope_is_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default scope (no arg) is project — backward compat with W4 callers."""
        monkeypatch.chdir(tmp_path)
        store_default = skill_commands._get_candidate_store()
        store_project = skill_commands._get_candidate_store(scope="project")
        assert store_default._dir == store_project._dir


class TestGlobalStoreNotInDiscoveryPaths:
    def test_global_store_path_is_not_in_external_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P0-1 regression: global drafts MUST NOT land in ExternalSkillLoader paths.

        ``~/.vibe/skills/`` IS in EXTERNAL_PATHS — drafts there would be
        auto-discovered, reopening the W4 未审不注入 bug. The global
        observability dir (``~/.vibe/observability/``) is the safe sibling.
        """
        fake_global = tmp_path / "fake_home" / ".vibe" / "observability"
        monkeypatch.setattr(skill_commands, "_GLOBAL_OBSERVABILITY_DIR", fake_global)

        store = skill_commands._get_candidate_store(scope="global")
        store_dir = store._dir

        # Assert no EXTERNAL_PATH is a prefix of (or equal to) store_dir.
        for external_path in ExternalSkillLoader.EXTERNAL_PATHS:
            # store_dir must not be inside external_path...
            assert external_path not in store_dir.parents, (
                f"Global store dir {store_dir} is under EXTERNAL_PATH {external_path} "
                f"— drafts would be auto-discovered, reopening W4 P0."
            )
            # ...and external_path must not be inside store_dir (reverse).
            assert store_dir not in external_path.parents, (
                f"EXTERNAL_PATH {external_path} is under global store dir {store_dir} "
                f"— discovery would walk through observability data."
            )
