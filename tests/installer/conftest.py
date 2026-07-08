"""conftest for installer tests — isolate the pack-lock store.

Every installer test runs with ``PackLockStore.LOCKS_DIR`` redirected to a tmp
dir, so install_pack's lock writes never touch the real ``~/.config/skills/``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_pack_locks(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibesop.core.skills import pack_lock

    monkeypatch.setattr(
        pack_lock.PackLockStore, "LOCKS_DIR", tmp_path / "pack-locks"
    )
