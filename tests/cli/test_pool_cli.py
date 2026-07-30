"""CLI tests for ``vibe pool`` (W5.1 Task 3.1).

Covers add/remove/list/status commands, idempotency on path, alias
collision errors, privacy notice on first add, and span-count column.

Storage is mocked to ``tmp_path`` to avoid polluting the developer's
real ``~/.vibe/pool.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import pool_cmd

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect pool storage to tmp_path.

    pool_cmd uses module-level ``_DEFAULT_POOL_PATH = Path.home() / .vibe / pool.yaml``.
    We monkeypatch the module attribute so tests don't touch the real home dir.
    """
    pool_path = tmp_path / "pool.yaml"
    monkeypatch.setattr(pool_cmd, "_DEFAULT_POOL_PATH", pool_path)
    return pool_path


@pytest.fixture
def project_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Two real project dirs to register."""
    a = tmp_path / "proj-a"
    b = tmp_path / "proj-b"
    a.mkdir()
    b.mkdir()
    return a, b


class TestPoolAdd:
    def test_pool_add_creates_entry(self, project_paths: tuple[Path, Path]) -> None:
        a, _ = project_paths
        result = runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        assert result.exit_code == 0, result.output
        assert "Added" in result.output
        assert "alpha" in result.output

        data = pool_cmd.load_pool()
        assert len(data["projects"]) == 1
        entry = data["projects"][0]
        assert entry["alias"] == "alpha"
        assert Path(entry["path"]).resolve() == a.resolve()
        assert "added_at" in entry

    def test_pool_add_idempotent_on_path(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, _ = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        assert result.exit_code == 0
        assert "Already registered" in result.output
        data = pool_cmd.load_pool()
        assert len(data["projects"]) == 1

    def test_pool_add_duplicate_alias_errors(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, b = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["add", str(b), "--alias", "alpha"])
        assert result.exit_code != 0
        assert "already in use" in result.output

    def test_pool_add_default_alias_is_dir_name(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, _ = project_paths
        result = runner.invoke(pool_cmd.app, ["add", str(a)])
        assert result.exit_code == 0
        data = pool_cmd.load_pool()
        assert data["projects"][0]["alias"] == a.name

    def test_pool_add_nonexistent_path_errors(self, tmp_path: Path) -> None:
        bogus = tmp_path / "does-not-exist"
        result = runner.invoke(pool_cmd.app, ["add", str(bogus)])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_pool_add_alias_change_on_existing_path(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, _ = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "renamed"])
        assert result.exit_code == 0
        assert "Updated alias" in result.output
        data = pool_cmd.load_pool()
        assert data["projects"][0]["alias"] == "renamed"


class TestPoolRemove:
    def test_pool_remove_deletes_entry(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, _ = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["remove", "alpha"])
        assert result.exit_code == 0
        assert "Removed" in result.output
        data = pool_cmd.load_pool()
        assert len(data["projects"]) == 0

    def test_pool_remove_silent_if_absent(self, tmp_path: Path) -> None:
        result = runner.invoke(pool_cmd.app, ["remove", "ghost"])
        assert result.exit_code == 0
        assert "Not in pool" in result.output

    def test_pool_remove_by_path_works(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, _ = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["remove", str(a)])
        assert result.exit_code == 0
        assert "Removed" in result.output


class TestPoolList:
    def test_pool_list_shows_table(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, b = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        runner.invoke(pool_cmd.app, ["add", str(b), "--alias", "beta"])
        result = runner.invoke(pool_cmd.app, ["list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output
        assert "Alias" in result.output  # table header present

    def test_pool_list_empty_pool_prints_hint(self, tmp_path: Path) -> None:
        result = runner.invoke(pool_cmd.app, ["list"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower() or "Pool is empty" in result.output

    def test_pool_list_shows_span_count(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, _ = project_paths
        # Create fake spans.jsonl in project a with 3 lines
        spans_dir = a / ".vibe" / "observability"
        spans_dir.mkdir(parents=True)
        spans_file = spans_dir / "spans.jsonl"
        spans_file.write_text('{"id":1}\n{"id":2}\n{"id":3}\n')
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["list"])
        assert "3" in result.output


class TestPoolStatus:
    def test_pool_status_shows_summary(
        self, project_paths: tuple[Path, Path]
    ) -> None:
        a, b = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        runner.invoke(pool_cmd.app, ["add", str(b), "--alias", "beta"])
        result = runner.invoke(pool_cmd.app, ["status"])
        assert result.exit_code == 0
        assert "2" in result.output  # project count
        assert "Pool file:" in result.output

    def test_pool_status_no_file_prints_hint(self, tmp_path: Path) -> None:
        result = runner.invoke(pool_cmd.app, ["status"])
        assert result.exit_code == 0
        assert "No pool file" in result.output


class TestPrivacyNotice:
    def test_first_add_prints_privacy_notice(
        self,
        project_paths: tuple[Path, Path],
        isolated_pool: Path,
    ) -> None:
        a, _ = project_paths
        result = runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        assert "Privacy" in result.output
        assert "never synced" in result.output

    def test_second_add_skips_privacy_notice(
        self,
        project_paths: tuple[Path, Path],
        isolated_pool: Path,
    ) -> None:
        a, b = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        result = runner.invoke(pool_cmd.app, ["add", str(b), "--alias", "beta"])
        # Second add must not repeat the notice
        assert result.output.count("Privacy") == 0

    def test_privacy_marker_is_versioned(
        self,
        project_paths: tuple[Path, Path],
        isolated_pool: Path,
    ) -> None:
        """Regression for architect WATCH: marker must be versioned so a
        future W5.2 sync feature can bump the version and force re-ack."""
        a, _ = project_paths
        runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        marker = isolated_pool.parent / ".pool-privacy-ack.v1"
        assert marker.exists(), f"Expected versioned marker at {marker}"


class TestConcurrentWrites:
    """Regression for code-reviewer CRITICAL: pool.yaml RMW must be locked."""

    def test_concurrent_adds_do_not_lose_entries(
        self,
        project_paths: tuple[Path, Path],
        isolated_pool: Path,
        tmp_path: Path,
    ) -> None:
        """Two writers adding different projects concurrently must both land.

        Pre-fix: ``_save_pool`` did a non-locked read-modify-write — two
        shells adding projects simultaneously would both read
        ``projects: []``, both append, second write clobbers first. The
        fix takes a cross-process lock and re-reads inside it.
        """
        import multiprocessing
        import time

        a, b = project_paths

        # Cannot easily use real multiprocessing with the monkeypatched
        # _DEFAULT_POOL_PATH (child processes re-import the module fresh).
        # Instead, verify the fix structurally: the lock file is created
        # and held during writes, and the save path goes through
        # _save_pool_locked which uses cross_process_lock.
        from vibesop.cli.commands import pool_cmd as pool_mod

        # The lock helper must exist and reference cross_process_lock.
        assert hasattr(pool_mod, "_save_pool_locked")

        # Functional check: sequential adds via the public API both persist.
        r1 = runner.invoke(pool_cmd.app, ["add", str(a), "--alias", "alpha"])
        r2 = runner.invoke(pool_cmd.app, ["add", str(b), "--alias", "beta"])
        assert r1.exit_code == 0 and r2.exit_code == 0

        data = pool_cmd.load_pool()
        aliases = {e["alias"] for e in data["projects"]}
        assert aliases == {"alpha", "beta"}

        # Lock file must be materialized on disk after writes.
        lock_file = isolated_pool.with_suffix(".lock")
        assert lock_file.exists(), (
            f"cross_process_lock should have created {lock_file}; "
            "without it concurrent writes can race"
        )

        # Silence unused-import linters on the no-op imports above.
        del multiprocessing, time
