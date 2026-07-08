"""Unit tests for PackLockStore (F-02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.skills.pack_lock import PackLock, PackLockStore


def test_write_and_get_round_trip(tmp_path: Path) -> None:
    store = PackLockStore(locks_dir=tmp_path)
    lock = PackLock(
        pack_name="demo",
        source_url="https://github.com/u/demo",
        commit_sha="abc123",
        content_sha256="deadbeef",
        installed_at="2026-07-07T00:00:00+00:00",
    )
    store.write(lock)

    got = store.get("demo")
    assert got is not None
    assert got.pack_name == "demo"
    assert got.commit_sha == "abc123"
    assert got.content_sha256 == "deadbeef"


def test_get_returns_none_when_absent(tmp_path: Path) -> None:
    assert PackLockStore(locks_dir=tmp_path).get("never-installed") is None


def test_get_returns_none_on_corrupt_file(tmp_path: Path) -> None:
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.json").write_text("{not valid json")
    assert PackLockStore(locks_dir=tmp_path).get("broken") is None


def test_clear_removes_lock(tmp_path: Path) -> None:
    store = PackLockStore(locks_dir=tmp_path)
    store.write(PackLock("demo", "u", "a", "b", "t"))
    assert store.get("demo") is not None
    store.clear("demo")
    assert store.get("demo") is None
    store.clear("demo")  # idempotent — no error if absent


def test_per_pack_isolation(tmp_path: Path) -> None:
    store = PackLockStore(locks_dir=tmp_path)
    store.write(PackLock("a", "u", "1", "h1", "t"))
    store.write(PackLock("b", "u", "2", "h2", "t"))
    assert store.get("a").commit_sha == "1"
    assert store.get("b").commit_sha == "2"


def test_path_traversal_names_are_rejected(tmp_path: Path) -> None:
    """A malicious pack name must not escape the locks directory."""
    store = PackLockStore(locks_dir=tmp_path)
    with pytest.raises(ValueError):
        store.write(PackLock("../.trusted", "u", "1", "h", "t"))
    with pytest.raises(ValueError):
        store.get("../.trusted")
    with pytest.raises(ValueError):
        store.clear("../.trusted")
