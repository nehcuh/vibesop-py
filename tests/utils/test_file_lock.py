"""Tests for the cross-platform file lock utility (P0-3 regression coverage).

Three layers (gate44 restructure — the whole-module-class skipif used to
hide the msvcrt branch from Windows entirely, which is exactly how the
P0-3 breakage shipped unnoticed):

1. ``TestCrossProcessLock`` — platform-neutral behaviour (self-reacquire,
   lock-file creation, release-on-exception, second-handle contention).
   Runs the REAL lock primitive on each platform: fcntl on POSIX, msvcrt
   on Windows. Locks are per-handle (flock: per open file description;
   msvcrt: per CRT handle), so a second in-process handle genuinely
   contends — no subprocess needed.
2. ``TestPosixFlockSemantics`` — fcntl-specific semantics (external
   blocker via raw flock, shared-lock composition). Skipped on Windows
   where msvcrt cannot express them.
3. ``TestMsvcrtDispatch`` — runs on POSIX only: fcntl is stubbed out and
   a fake ``msvcrt`` module injected, exercising the Windows dispatch
   path (mode constants, spin timeout, CouldNotLock mapping,
   lseek-before-unlock). The fake is NOT a real lock — it verifies our
   dispatch logic, never Windows kernel semantics.
"""

from __future__ import annotations

import errno
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from vibesop.utils.file_lock import CouldNotLock, cross_process_lock


class TestCrossProcessLock:
    def test_exclusive_self_held_no_block(self, tmp_path: Path) -> None:
        """Acquiring + releasing inside one thread is a no-op-ish happy path."""
        lock = tmp_path / "x.lock"
        with cross_process_lock(lock):
            pass  # should not raise
        # Re-acquire immediately after release — should still work.
        with cross_process_lock(lock):
            pass

    def test_second_handle_blocks_until_release(self, tmp_path: Path) -> None:
        """A held lock must block a second acquirer, then let it through on release.

        Uses cross_process_lock itself as the blocker (a second handle in
        another thread) so the assertion runs against the real platform
        primitive — flock on POSIX, msvcrt on Windows.
        """
        lock = tmp_path / "contend.lock"
        release = threading.Event()
        acquired = threading.Event()

        def holder() -> None:
            with cross_process_lock(lock):
                release.wait(timeout=5.0)

        t = threading.Thread(target=holder)
        t.start()
        try:
            # While held, a non-blocking acquire must refuse, not pass.
            deadline = time.monotonic() + 2.0
            refused = False
            while time.monotonic() < deadline:
                try:
                    with cross_process_lock(lock, blocking=False):
                        pass
                except CouldNotLock:
                    refused = True
                    break
                # The holder thread may not have acquired yet — retry.
                time.sleep(0.02)
            assert refused, "non-blocking acquire passed while lock was held"

            # A blocking acquire in a third thread completes after release.
            def waiter() -> None:
                with cross_process_lock(lock):
                    acquired.set()

            w = threading.Thread(target=waiter)
            w.start()
            assert not acquired.wait(timeout=0.3), "blocking acquire passed while lock was held"
            release.set()
            assert acquired.wait(timeout=2.0), "blocking acquire didn't complete after release"
            w.join()
        finally:
            release.set()
            t.join()

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


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX flock semantics (external blocker, shared composition)"
)
class TestPosixFlockSemantics:
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
        """Two SH locks on the same path can coexist (POSIX only — msvcrt
        cannot express shared locks and degenerates to exclusive)."""
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


class TestSiblingLockRegressions:
    """Minimal repro of the gate44 cluster-A failure modes.

    On Windows these ran red before the sibling-lock fix: locking the DATA
    file (a) blocked a second append handle's first write on an empty file
    (msvcrt byte-0 region lock) and (b) blocked AtomicWriter's os.replace
    onto the held handle. With a sibling lock file both operations must
    succeed while the lock is held. Windows CI is the real judge; on POSIX
    these double as no-regression checks for the fcntl path.
    """

    def test_append_to_empty_file_under_sibling_lock(self, tmp_path: Path) -> None:
        from vibesop.utils.file_lock import cross_process_lock as cpl

        data = tmp_path / "spans.jsonl"
        data.touch()
        lock = data.with_name(data.name + ".lock")
        with cpl(lock):
            with data.open("a", encoding="utf-8") as f:
                f.write('{"ok": true}\n')
        assert data.read_text(encoding="utf-8") == '{"ok": true}\n'

    def test_atomic_replace_under_sibling_lock(self, tmp_path: Path) -> None:
        from vibesop.utils.atomic_writer import AtomicWriter
        from vibesop.utils.file_lock import cross_process_lock as cpl

        data = tmp_path / "state.json"
        data.write_text('{"v": 1}', encoding="utf-8")
        lock = data.with_name(data.name + ".lock")
        with cpl(lock):
            with AtomicWriter().atomic_open(data, "w") as f:
                f.write('{"v": 2}')
        assert data.read_text(encoding="utf-8") == '{"v": 2}'


@pytest.mark.skipif(
    sys.platform == "win32", reason="fakes the Windows path; pointless on real Windows"
)
class TestMsvcrtDispatch:
    """Exercise the msvcrt dispatch branch on POSIX with a fake module.

    fcntl is disabled (sys.modules["fcntl"] = None makes ``import fcntl``
    raise ImportError) and a recording fake msvcrt injected. Asserts OUR
    dispatch logic only — mode constants, spin budget, CouldNotLock
    mapping, lseek-before-unlock. Never asserts kernel lock semantics.
    """

    @staticmethod
    def _install_fake(msvcrt_fake: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "msvcrt", msvcrt_fake)
        monkeypatch.setitem(sys.modules, "fcntl", None)

    def test_exclusive_uses_nblk_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[int, int, int]] = []

        fake = SimpleNamespace(
            LK_NBLCK=0x02,
            LK_NBRLCK=0x10,
            LK_UNLCK=0x00,
            locking=lambda fd, mode, nbytes: calls.append((fd, mode, nbytes)),
        )
        self._install_fake(fake, monkeypatch)

        lock = tmp_path / "dispatch.lock"
        with cross_process_lock(lock, blocking=False):
            assert len(calls) == 1
            _fd, mode, nbytes = calls[0]
            assert mode == fake.LK_NBLCK, "exclusive acquire must use LK_NBLCK"
            assert nbytes == 1

    def test_shared_uses_nbrlk_mode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[int, int, int]] = []

        fake = SimpleNamespace(
            LK_NBLCK=0x02,
            LK_NBRLCK=0x10,
            LK_UNLCK=0x00,
            locking=lambda fd, mode, nbytes: calls.append((fd, mode, nbytes)),
        )
        self._install_fake(fake, monkeypatch)

        lock = tmp_path / "shared-dispatch.lock"
        with cross_process_lock(lock, shared=True, blocking=False):
            assert calls and calls[0][1] == fake.LK_NBRLCK, "shared acquire must use LK_NBRLCK"

    def test_nonblocking_held_maps_to_couldnotlock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(fd: int, mode: int, nbytes: int) -> None:
            raise PermissionError(errno.EACCES, "locked by another handle")

        fake = SimpleNamespace(LK_NBLCK=0x02, LK_NBRLCK=0x10, LK_UNLCK=0x00, locking=refuse)
        self._install_fake(fake, monkeypatch)

        lock = tmp_path / "refused.lock"
        with pytest.raises(CouldNotLock):
            with cross_process_lock(lock, blocking=False):
                pass

    def test_blocking_spin_times_out_with_oserror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(fd: int, mode: int, nbytes: int) -> None:
            raise PermissionError(errno.EACCES, "locked by another handle")

        fake = SimpleNamespace(LK_NBLCK=0x02, LK_NBRLCK=0x10, LK_UNLCK=0x00, locking=refuse)
        self._install_fake(fake, monkeypatch)

        lock = tmp_path / "spin.lock"
        with pytest.raises(OSError, match="timed out acquiring Windows lock"):
            with cross_process_lock(
                lock, blocking=True, spin_interval_s=0.001, max_spin_attempts=3
            ):
                pass

    def test_release_lseeks_to_zero_before_unlock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_release must reposition on the locked byte before LK_UNLCK —
        msvcrt unlocks the byte at the current file position."""
        calls: list[tuple[int, int, int]] = []
        real_lseek = os.lseek

        def spy_lseek(fd: int, pos: int, whence: int) -> int:
            calls.append(("lseek", fd, pos, whence))  # type: ignore[arg-type]
            return real_lseek(fd, pos, whence)

        fake = SimpleNamespace(
            LK_NBLCK=0x02,
            LK_NBRLCK=0x10,
            LK_UNLCK=0x00,
            locking=lambda fd, mode, nbytes: calls.append(("locking", fd, mode, nbytes)),  # type: ignore[arg-type]
        )
        self._install_fake(fake, monkeypatch)
        monkeypatch.setattr(os, "lseek", spy_lseek)

        lock = tmp_path / "release.lock"
        with cross_process_lock(lock, blocking=False):
            unlock_calls = [c for c in calls if c[0] == "locking" and c[2] == fake.LK_UNLCK]
            assert not unlock_calls

        unlock_calls = [c for c in calls if c[0] == "locking" and c[2] == fake.LK_UNLCK]
        assert len(unlock_calls) == 1, "release must issue exactly one LK_UNLCK"
        # The call immediately preceding LK_UNLCK must be lseek(0, SEEK_SET).
        locking_idx = calls.index(unlock_calls[0])
        assert locking_idx >= 1
        prev = calls[locking_idx - 1]
        assert prev[0] == "lseek" and prev[2] == 0 and prev[3] == os.SEEK_SET, (
            "release must lseek(0, SEEK_SET) immediately before LK_UNLCK"
        )
