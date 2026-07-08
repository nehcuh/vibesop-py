"""F-02 integrity gate tests — install_pack verifies against the pack lock.

Mocks the install dependencies (RepoAnalyzer/InstallPlanner/capture_rev/
calculate_checksum) so the lock-verify logic is tested without real git/network.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.exceptions import PackIntegrityError
from vibesop.core.skills.pack_lock import PackLock, PackLockStore
from vibesop.installer.pack_installer import PackInstaller


@contextlib.contextmanager
def install_deps(commit_sha: str, content_sha256: str, target_path: Path):
    """Patch the install heavy deps with controlled commit/content values."""
    with (
        patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls,
        patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls,
        patch("vibesop.installer.analyzer.capture_rev", return_value=commit_sha),
        patch(
            "vibesop.utils.marker_files.MarkerFileManager.calculate_checksum",
            return_value=content_sha256,
        ),
    ):
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = MagicMock(
            errors=[], skill_files=[Path("skills/test/SKILL.md")]
        )
        mock_analyzer.git_clone.return_value = True
        mock_cls.return_value = mock_analyzer
        mock_plan = MagicMock()
        mock_plan.target_path = target_path
        planner_cls.return_value.plan.return_value = mock_plan
        yield mock_analyzer


def test_fresh_install_writes_lock(tmp_path: Path) -> None:
    installer = PackInstaller(external_paths=[tmp_path])
    target = tmp_path / "fresh-pack"
    target.mkdir(parents=True, exist_ok=True)
    with install_deps("commit-1", "hash-1", target):
        success, _ = installer.install_pack("fresh-pack", "https://example.com/fresh-pack")
    assert success is True
    lock = PackLockStore().get("fresh-pack")
    assert lock is not None
    assert lock.commit_sha == "commit-1"
    assert lock.content_sha256 == "hash-1"


def test_same_commit_no_rejection(tmp_path: Path) -> None:
    installer = PackInstaller(external_paths=[tmp_path])
    target = tmp_path / "same-pack"
    target.mkdir(parents=True, exist_ok=True)
    PackLockStore().write(
        PackLock("same-pack", "https://example.com", "commit-1", "hash-1", "2026-01-01")
    )
    with install_deps("commit-1", "hash-1", target):
        success, _ = installer.install_pack("same-pack", "https://example.com/same-pack")
    assert success is True


def test_force_push_rejected_without_upgrade(tmp_path: Path) -> None:
    installer = PackInstaller(external_paths=[tmp_path])
    target = tmp_path / "changed-pack"
    target.mkdir(parents=True, exist_ok=True)
    PackLockStore().write(
        PackLock("changed-pack", "https://example.com", "commit-A", "hash-A", "2026-01-01")
    )
    with install_deps("commit-B", "hash-A", target):
        with pytest.raises(PackIntegrityError, match="changed since"):
            installer.install_pack("changed-pack", "https://example.com/changed-pack")


def test_content_tamper_rejected_even_if_commit_matches(tmp_path: Path) -> None:
    installer = PackInstaller(external_paths=[tmp_path])
    target = tmp_path / "tampered-pack"
    target.mkdir(parents=True, exist_ok=True)
    PackLockStore().write(
        PackLock("tampered-pack", "https://example.com", "commit-X", "hash-clean", "2026-01-01")
    )
    # Same commit, but content differs (tree tampered) — content hash catches it.
    with install_deps("commit-X", "hash-tampered", target):
        with pytest.raises(PackIntegrityError, match="changed since"):
            installer.install_pack("tampered-pack", "https://example.com/tampered-pack")


def test_upgrade_accepts_changed_pack_and_updates_lock(tmp_path: Path) -> None:
    installer = PackInstaller(external_paths=[tmp_path])
    target = tmp_path / "upgrade-pack"
    target.mkdir(parents=True, exist_ok=True)
    PackLockStore().write(
        PackLock("upgrade-pack", "https://example.com", "commit-A", "hash-A", "2026-01-01")
    )
    with install_deps("commit-B", "hash-B", target):
        success, _ = installer.install_pack(
            "upgrade-pack", "https://example.com/upgrade-pack", upgrade=True
        )
    assert success is True
    lock = PackLockStore().get("upgrade-pack")
    assert lock is not None
    assert lock.commit_sha == "commit-B"  # lock updated to the new commit
