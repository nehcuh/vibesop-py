"""Unit tests for update_checker — passive pack/registry update detection.

All network paths are mocked: ``remote_head_sha`` (git ls-remote) is patched
at the module attribute so ``check_pack_updates`` never leaves the machine.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vibesop.core.skills import update_checker
from vibesop.core.skills.pack_lock import PackLock, PackLockStore
from vibesop.core.skills.update_checker import (
    CACHE_FILENAME,
    PackUpdateStatus,
    cached_pack_updates,
    check_pack_updates,
    registry_age_days,
    remote_head_sha,
)

SHA_A = "a" * 40
SHA_B = "b" * 40


def _lock(name: str, sha: str = SHA_A, url: str | None = None) -> PackLock:
    return PackLock(
        pack_name=name,
        # `url if url is not None` — "" is a valid test input (missing source)
        source_url=url if url is not None else f"https://github.com/u/{name}",
        commit_sha=sha,
        content_sha256="content",
        installed_at="2026-09-01T00:00:00+00:00",
    )


def _make_store(tmp_path: Path, *locks: PackLock) -> PackLockStore:
    store = PackLockStore(locks_dir=tmp_path)
    for lock in locks:
        store.write(lock)
    return store


def _write_cache(tmp_path: Path, packs: dict[str, PackUpdateStatus], age: timedelta) -> None:
    payload = {
        "checked_at": (datetime.now(UTC) - age).isoformat(),
        "packs": {name: s.to_dict() for name, s in packs.items()},
    }
    (tmp_path / CACHE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


class TestRemoteHeadSha:
    def test_parses_sha_from_ls_remote_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout=f"{SHA_B}\tHEAD\n", stderr="")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed)
        assert remote_head_sha("https://github.com/u/p") == SHA_B

    def test_tree_url_normalized_to_clone_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen["cmd"] = cmd
            seen["shell"] = kwargs.get("shell", False)
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{SHA_B}\tHEAD\n", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        remote_head_sha("https://github.com/u/p/tree/main/sub")
        cmd = seen["cmd"]
        assert isinstance(cmd, list)
        assert "https://github.com/u/p.git" in cmd
        assert seen["shell"] is False  # argv form — no shell injection surface

    @pytest.mark.parametrize(
        "exc",
        [
            subprocess.CalledProcessError(128, "git"),
            subprocess.TimeoutExpired("git", 8),
            FileNotFoundError("git"),
            OSError("network down"),
        ],
    )
    def test_failures_return_empty_string(
        self, monkeypatch: pytest.MonkeyPatch, exc: Exception
    ) -> None:
        def boom(*a: object, **k: object) -> None:
            raise exc

        monkeypatch.setattr(subprocess, "run", boom)
        assert remote_head_sha("https://github.com/u/p") == ""

    def test_blank_stdout_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout="  \n", stderr="")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed)
        assert remote_head_sha("https://github.com/u/p") == ""


class TestCheckPackUpdates:
    def test_no_locks_returns_empty(self, tmp_path: Path) -> None:
        assert check_pack_updates(store=PackLockStore(locks_dir=tmp_path)) == []

    def test_three_verdict_states(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _make_store(
            tmp_path,
            _lock("current", sha=SHA_A),
            _lock("behind", sha=SHA_B),
            _lock("nosha", sha=""),
            _lock("offline", sha=SHA_A, url="https://github.com/u/offline"),
        )

        def fake_remote(url: str, timeout: int = 8) -> str:
            if url.endswith("/offline"):
                return ""  # simulate network failure
            return SHA_A

        monkeypatch.setattr(update_checker, "remote_head_sha", fake_remote)
        states = {s.pack_name: s.state for s in check_pack_updates(store=store)}
        assert states == {
            "current": "up_to_date",
            "behind": "update_available",
            "nosha": "unknown",
            "offline": "unknown",
        }

    def test_cache_written_and_second_call_avoids_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(tmp_path, _lock("demo", sha=SHA_B))
        calls: list[str] = []

        def fake_remote(url: str, timeout: int = 8) -> str:
            calls.append(url)
            return SHA_A

        monkeypatch.setattr(update_checker, "remote_head_sha", fake_remote)
        first = check_pack_updates(store=store)
        assert first[0].state == "update_available"
        assert (tmp_path / CACHE_FILENAME).exists()

        second = check_pack_updates(store=store)
        assert second[0].state == "update_available"
        assert len(calls) == 1  # second call served from cache

    def test_refresh_bypasses_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _make_store(tmp_path, _lock("demo"))
        calls: list[str] = []

        def fake_remote(url: str, timeout: int = 8) -> str:
            calls.append(url)
            return SHA_A

        monkeypatch.setattr(update_checker, "remote_head_sha", fake_remote)
        check_pack_updates(store=store)
        check_pack_updates(store=store, refresh=True)
        assert len(calls) == 2

    def test_expired_ttl_rechecks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _make_store(tmp_path, _lock("demo"))
        _write_cache(
            tmp_path,
            {"demo": PackUpdateStatus("demo", "u", SHA_A, SHA_A, "up_to_date", "")},
            age=timedelta(hours=25),
        )
        calls: list[str] = []

        def fake_remote(url: str, timeout: int = 8) -> str:
            calls.append(url)
            return SHA_B

        monkeypatch.setattr(update_checker, "remote_head_sha", fake_remote)
        result = check_pack_updates(store=store)
        assert len(calls) == 1  # stale cache ignored
        assert result[0].state == "update_available"

    def test_corrupt_cache_degrades_to_fresh_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(tmp_path, _lock("demo"))
        (tmp_path / CACHE_FILENAME).write_text("{broken json", encoding="utf-8")
        monkeypatch.setattr(update_checker, "remote_head_sha", lambda url, timeout=8: SHA_A)

        result = check_pack_updates(store=store)
        assert result[0].state == "up_to_date"  # corrupt cache replaced, not fatal

    def test_lock_changed_after_cache_is_unknown_without_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pack reinstalled (--upgrade) after the snapshot → no stale verdict,
        and no network hit inside the fresh-cache window."""
        store = _make_store(tmp_path, _lock("demo", sha=SHA_B))
        _write_cache(
            tmp_path,
            {"demo": PackUpdateStatus("demo", "u", SHA_A, SHA_A, "up_to_date", "")},
            age=timedelta(minutes=5),
        )

        def boom(url: str, timeout: int = 8) -> str:
            raise AssertionError("fresh-cache path must not touch the network")

        monkeypatch.setattr(update_checker, "remote_head_sha", boom)
        result = check_pack_updates(store=store)
        assert result[0].state == "unknown"
        assert result[0].installed_sha == SHA_B

    def test_lock_without_source_url_is_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(tmp_path, _lock("demo", url=""))

        def boom(url: str, timeout: int = 8) -> str:
            raise AssertionError("empty source_url must skip ls-remote")

        monkeypatch.setattr(update_checker, "remote_head_sha", boom)
        result = check_pack_updates(store=store)
        assert result[0].state == "unknown"


class TestCachedPackUpdates:
    def test_missing_cache_returns_empty(self, tmp_path: Path) -> None:
        assert cached_pack_updates(PackLockStore(locks_dir=tmp_path)) == []

    def test_corrupt_cache_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / CACHE_FILENAME).write_text("{broken", encoding="utf-8")
        assert cached_pack_updates(PackLockStore(locks_dir=tmp_path)) == []

    def test_never_touches_network(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_cache(
            tmp_path,
            {"demo": PackUpdateStatus("demo", "u", SHA_B, SHA_A, "update_available", "")},
            age=timedelta(days=100),  # even an expired cache is returned as-is
        )

        def boom(url: str, timeout: int = 8) -> str:
            raise AssertionError("cached_pack_updates must be network-free")

        monkeypatch.setattr(update_checker, "remote_head_sha", boom)
        result = cached_pack_updates(PackLockStore(locks_dir=tmp_path))
        assert len(result) == 1
        assert result[0].state == "update_available"


class TestRegistryAgeDays:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert registry_age_days(tmp_path) is None

    def test_empty_updated_at_returns_none(self, tmp_path: Path) -> None:
        """Pre-fix registries wrote updated_at="" — age is unknowable, not 0."""
        local = tmp_path / ".vibe" / "featured-skills.json"
        local.parent.mkdir(parents=True)
        local.write_text(json.dumps({"updated_at": "", "skills": []}), encoding="utf-8")
        assert registry_age_days(tmp_path) is None

    def test_recent_registry_age_near_zero(self, tmp_path: Path) -> None:
        local = tmp_path / ".vibe" / "featured-skills.json"
        local.parent.mkdir(parents=True)
        local.write_text(
            json.dumps({"updated_at": datetime.now(UTC).isoformat(), "skills": []}),
            encoding="utf-8",
        )
        age = registry_age_days(tmp_path)
        assert age is not None and age < 0.01

    def test_old_registry_reports_age(self, tmp_path: Path) -> None:
        local = tmp_path / ".vibe" / "featured-skills.json"
        local.parent.mkdir(parents=True)
        stale = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        local.write_text(json.dumps({"updated_at": stale, "skills": []}), encoding="utf-8")
        age = registry_age_days(tmp_path)
        assert age is not None and 39 < age < 41

    def test_naive_timestamp_treated_as_utc(self, tmp_path: Path) -> None:
        local = tmp_path / ".vibe" / "featured-skills.json"
        local.parent.mkdir(parents=True)
        naive = (datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None).isoformat()
        local.write_text(json.dumps({"updated_at": naive, "skills": []}), encoding="utf-8")
        age = registry_age_days(tmp_path)
        assert age is not None and 1 < age < 3

    def test_corrupt_json_returns_none(self, tmp_path: Path) -> None:
        local = tmp_path / ".vibe" / "featured-skills.json"
        local.parent.mkdir(parents=True)
        local.write_text("{not json", encoding="utf-8")
        assert registry_age_days(tmp_path) is None


class TestStatusRoundTrip:
    def test_to_dict_from_dict_round_trip(self) -> None:
        status = PackUpdateStatus("demo", "https://github.com/u/demo", SHA_A, SHA_B, "x", "t")
        restored = PackUpdateStatus.from_dict(status.to_dict())
        assert restored == status

    def test_from_dict_defaults_are_safe(self) -> None:
        restored = PackUpdateStatus.from_dict({})
        assert restored.state == "unknown"
        assert restored.pack_name == ""
