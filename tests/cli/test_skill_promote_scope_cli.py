"""W5.2 Task 3.1 + 3.2 — promote --scope flag + cross-project warning.

Verifies:
- ``--scope project`` (default): draft lands in cwd/.vibe/observability/skill_drafts/.
- ``--scope global``: draft lands in ~/.vibe/observability/skill_drafts/.
- Cross-project candidate lookup pulls from the global store when not
  present in the project store.
- Global drafts path is NOT under ExternalSkillLoader.EXTERNAL_PATHS
  (P0-1 regression: drafts must not be auto-discovered).
- Cross-project + project scope → loud warning printed (permissive
  policy per brief v2 §7a A2).
- Cross-project + global scope → mild info line.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import skill_commands
from vibesop.cli.main import app
from vibesop.core.observability.skill_promote import (
    ClusterCandidate,
    ClusterCandidateStore,
)
from vibesop.core.skills.external_loader import ExternalSkillLoader


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        skill_commands,
        "_GLOBAL_OBSERVABILITY_DIR",
        tmp_path / "fake_home" / ".vibe" / "observability",
    )
    return tmp_path


def _make_candidate(
    *,
    cluster_id: str,
    queries: list[str],
    project_distribution: dict[str, int],
    span_count: int = 3,
    gold_rate: float = 0.8,
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=[f"t-{cluster_id}-{i}" for i in range(len(queries))],
        queries=queries,
        span_count=span_count,
        gold_rate=gold_rate,
        gold_task_ids=[f"t-{cluster_id}-0"],
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        project_distribution=project_distribution,
    )


@pytest.fixture
def dual_store(tmp_path: Path) -> tuple[ClusterCandidateStore, ClusterCandidateStore]:
    project_store = ClusterCandidateStore(storage_dir=tmp_path / ".vibe" / "observability")
    global_store = ClusterCandidateStore(
        storage_dir=tmp_path / "fake_home" / ".vibe" / "observability"
    )
    return project_store, global_store


def _patch_dual(
    project_store: ClusterCandidateStore, global_store: ClusterCandidateStore
):
    """Patch _get_candidate_store so scope='project'/'global' return paired stores."""
    cm = patch.object(skill_commands, "_get_candidate_store")

    def fake_get(scope: str = "project") -> ClusterCandidateStore:
        return global_store if scope == "global" else project_store

    return cm, fake_get


class TestPromoteScopeFlag:
    def test_promote_scope_project_writes_to_cwd_drafts(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
        isolated_paths: Path,
    ) -> None:
        """Default scope → draft under <cwd>/.vibe/observability/skill_drafts/."""
        project_store, _ = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="local-1",
                queries=["local task"],
                project_distribution={str(isolated_paths.resolve()): 3},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(app, ["skill", "promote", "local-1"])

        assert result.exit_code == 0, result.stdout
        # Draft must land in cwd, NOT home.
        cwd_draft = isolated_paths / ".vibe" / "observability" / "skill_drafts"
        home_draft = isolated_paths / "fake_home" / ".vibe" / "observability" / "skill_drafts"
        assert any(cwd_draft.rglob("SKILL.md")), "expected draft in cwd observability"
        assert not any(home_draft.rglob("SKILL.md")), "draft should NOT be in home"

    def test_promote_scope_global_writes_to_home_drafts(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
        isolated_paths: Path,
    ) -> None:
        """--scope global → draft under ~/.vibe/observability/skill_drafts/."""
        project_store, _ = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="any-1",
                queries=["any task"],
                project_distribution={str(isolated_paths.resolve()): 3},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(app, ["skill", "promote", "any-1", "--scope", "global"])

        assert result.exit_code == 0, result.stdout
        home_draft = isolated_paths / "fake_home" / ".vibe" / "observability" / "skill_drafts"
        cwd_draft = isolated_paths / ".vibe" / "observability" / "skill_drafts"
        assert any(home_draft.rglob("SKILL.md")), "expected draft in home observability"
        assert not any(cwd_draft.rglob("SKILL.md")), "draft should NOT be in cwd"

    def test_promote_scope_global_path_is_not_in_external_paths(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
        isolated_paths: Path,
    ) -> None:
        """P0-1 regression: global drafts MUST NOT be under EXTERNAL_PATHS.

        ``~/.vibe/skills/`` IS auto-discovered; drafts there reopen the
        W4 未审不注入 bug. ``~/.vibe/observability/skill_drafts/`` is the
        safe sibling (observability tree is for instrumented data, not
        skill files loaded by the loader).
        """
        project_store, _ = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="safe-1",
                queries=["safe task"],
                project_distribution={str(isolated_paths.resolve()): 3},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(app, ["skill", "promote", "safe-1", "--scope", "global"])

        assert result.exit_code == 0, result.stdout

        # Find the drafted SKILL.md
        home_draft_root = isolated_paths / "fake_home" / ".vibe" / "observability" / "skill_drafts"
        skill_files = list(home_draft_root.rglob("SKILL.md"))
        assert skill_files, "expected at least one draft"
        drafted = skill_files[0]

        # Assert no EXTERNAL_PATH contains the draft.
        for external_path in ExternalSkillLoader.EXTERNAL_PATHS:
            assert external_path not in drafted.parents, (
                f"Draft {drafted} is under EXTERNAL_PATH {external_path} — "
                f"W4 未审不注入 regression."
            )

    def test_promote_loads_candidate_from_correct_store(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """Cross-project candidate in global store is found when project store is empty."""
        _project_store, global_store = dual_store
        global_store.upsert(
            _make_candidate(
                cluster_id="xp-only-1",
                queries=["cross task"],
                project_distribution={"/users/me/a": 2, "/users/me/b": 1},
            )
        )
        # Project store is EMPTY for this cluster_id.

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(app, ["skill", "promote", "xp-only-1", "--scope", "global"])

        assert result.exit_code == 0, result.stdout
        # Global store's row should be flipped to "promoted"
        promoted = global_store.get("xp-only-1")
        assert promoted is not None
        assert promoted.status == "promoted"


class TestCrossProjectWarning:
    def test_promote_cross_project_to_project_scope_emits_warning(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """Cross-project + project scope → loud yellow warning on stdout."""
        project_store, _ = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="xp-local-1",
                queries=["cross task"],
                project_distribution={"/users/me/a": 2, "/users/me/b": 1},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(
                app, ["skill", "promote", "xp-local-1", "--scope", "project"]
            )

        assert result.exit_code == 0, result.stdout
        assert "Cross-project cluster" in result.stdout
        assert "multiple projects" in result.stdout.lower()

    def test_promote_cross_project_to_global_scope_emits_info(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """Cross-project + global scope → mild info line, no warning."""
        project_store, _ = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="xp-global-1",
                queries=["cross task"],
                project_distribution={"/users/me/a": 2, "/users/me/b": 1},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(
                app, ["skill", "promote", "xp-global-1", "--scope", "global"]
            )

        assert result.exit_code == 0, result.stdout
        assert "Cross-project cluster" in result.stdout
        assert "global drafts" in result.stdout.lower()


class TestScopeAuthoritativeStoreSelection:
    """omx-code-review ARCHITECT #2 — --scope must be authoritative.

    Bug being fixed: prior logic picked "more heterogeneous" record even
    when the user explicitly passed ``--scope project``. If the cluster
    existed in both stores, the global store got flipped while the draft
    landed in project drafts — status inconsistency visible to other pool
    members who never opted in.

    Fix: try requested scope's store first; fall back to the other store
    only when the cluster is absent (with a visible hint).
    """

    def test_scope_project_with_cluster_in_both_stores_flips_project_store(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
        isolated_paths: Path,
    ) -> None:
        """--scope project + cluster in both stores → project store flipped.

        Project store has the smaller (single-project) record. Old code
        would have flipped the global store here. Now project wins because
        the user explicitly said --scope project.
        """
        project_store, global_store = dual_store
        # Project store has the smaller record.
        project_store.upsert(
            _make_candidate(
                cluster_id="dup-1",
                queries=["shared task"],
                project_distribution={str(isolated_paths.resolve()): 2},
            )
        )
        # Global store has the more-heterogeneous record.
        global_store.upsert(
            _make_candidate(
                cluster_id="dup-1",
                queries=["shared task"],
                project_distribution={"/users/me/a": 4, "/users/me/b": 3},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(
                app, ["skill", "promote", "dup-1", "--scope", "project"]
            )

        assert result.exit_code == 0, result.stdout
        # Project store's row should be promoted (status=promoted).
        proj_row = project_store.get("dup-1")
        assert proj_row is not None
        assert proj_row.status == "promoted"
        # Global store's row should be UNTOUCHED.
        glob_row = global_store.get("dup-1")
        assert glob_row is not None
        assert glob_row.status == "pending"

    def test_scope_global_with_cluster_only_in_project_store_redirects_with_hint(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """--scope global + cluster only in project store → redirect + hint.

        No regression: the cluster gets promoted (via fallback), but the
        user sees a dim hint explaining the redirect.
        """
        project_store, _global_store = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="only-proj-1",
                queries=["local task"],
                project_distribution={"/users/me/a": 3},
            )
        )

        cm, fake_get = _patch_dual(*dual_store)
        with cm as mock_get:
            mock_get.side_effect = fake_get
            result = cli_runner.invoke(
                app, ["skill", "promote", "only-proj-1", "--scope", "global"]
            )

        assert result.exit_code == 0, result.stdout
        # Hint mentions the redirect.
        assert "found in project store" in result.stdout.lower()
        # Project store's row IS flipped (fallback path).
        proj_row = project_store.get("only-proj-1")
        assert proj_row is not None
        assert proj_row.status == "promoted"
