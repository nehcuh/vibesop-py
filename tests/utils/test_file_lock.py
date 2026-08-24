"""Tests for the cross-platform file lock utility (P0-3 regression coverage).

POSIX-only here — the Windows ``msvcrt`` branch is exercised by CI on
Windows runners. macOS/Linux tests cover the fcntl path and the shared /
exclusive / blocking / non-blocking matrix.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from vibesop.utils.file_lock import CouldNotLock, cross_process_lock


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock semantics")
class TestCrossProcessLock:
    def test_exclusive_self_held_no_block(self, tmp_path: Path) -> None:
        """Acquiring + releasing inside one thread is a no-op-ish happy path."""
        lock = tmp_path / "x.lock"
        with cross_process_lock(lock):
            pass  # should not raise
        # Re-acquire immediately after release — should still work.
        with cross_process_lock(lock):
            pass

    def test_external_ex_blocks_second_acquirer(self, tmp_path: Path) -> None:
        """Two threads contending for EX on the same path serialise."""
        import fcntl

        lock = tmp_path / "ex.lock"
        blocker = lock.open("a+")
        fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)

        completed = threading.Event()

        def try_acquire():
            with cross_process_lock(lock):
                completed.set()

        t = threading.Thread(target=try_acquire)
        t.start()
        # Should still be blocked.
        assert not completed.wait(timeout=0.3), "second acquirer not blocked by external EX"

        fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
        blocker.close()
        assert completed.wait(timeout=2.0), "second acquirer didn't complete after release"

    def test_non_blocking_raises_when_held(self, tmp_path: Path) -> None:
        """blocking=False with a held lock must raise CouldNotLock, not hang."""
        import fcntl

        lock = tmp_path / "nb.lock"
        blocker = lock.open("a+")
        fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)

        try:
            with pytest.raises(CouldNotLock):
                with cross_process_lock(lock, blocking=False):
                    pass
        finally:
            fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
            blocker.close()

    def test_shared_locks_compose(self, tmp_path: Path) -> None:
        """Two SH locks on the same path can coexist."""
        lock = tmp_path / "sh.lock"
        with cross_process_lock(lock, shared=True):
            with cross_process_lock(lock, shared=True):
                pass  # both acquired — would deadlock if SH were actually EX

    def test_shared_blocks_exclusive(self, tmp_path: Path) -> None:
        """An external SH holder must block our EX acquirer."""
        import fcntl

        lock = tmp_path / "mix.lock"
        blocker = lock.open("a+")
        fcntl.flock(blocker.fileno(), fcntl.LOCK_SH)

        completed = threading.Event()

        def try_ex():
            with cross_process_lock(lock):  # EX
                completed.set()

        t = threading.Thread(target=try_ex)
        t.start()
        assert not completed.wait(timeout=0.3), "EX acquirer not blocked by external SH"

        fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
        blocker.close()
        assert completed.wait(timeout=2.0), "EX acquirer didn't complete after SH release"

    def test_lock_file_created_if_missing(self, tmp_path: Path) -> None:
        """Caller shouldn't have to pre-create the lock file."""
        lock = tmp_path / "nested" / "deep" / "lock"
        with cross_process_lock(lock):
            assert lock.exists()

    def test_lock_released_on_exception_inside_block(self, tmp_path: Path) -> None:
        """If the body raises, the lock must still release (try/finally)."""
        lock = tmp_path / "exc.lock"

        class Boom(Exception):
            pass

        with pytest.raises(Boom):
            with cross_process_lock(lock):
                raise Boom("body failed")

        # Acquire again from the same thread — would block forever if not released.
        done = threading.Event()

        def reacquire():
            with cross_process_lock(lock, blocking=False):
                done.set()

        t = threading.Thread(target=reacquire)
        t.start()
        assert done.wait(timeout=1.0), "lock not released after body exception"
        t.join()
