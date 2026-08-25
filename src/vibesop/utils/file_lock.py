"""Cross-platform advisory file locking.

POSIX uses ``fcntl.flock`` (BSD-style whole-file lock). Windows has no
``fcntl``; we fall back to ``msvcrt.locking`` on a single byte. Callers
that previously did ``try: import fcntl; except ImportError: <no-op>`` left
Windows entirely unlocked — under concurrent writes that meant torn JSONL
lines and silent data corruption (deep-diagnosis-2026-07-24 P0-3).

The lock is *advisory*: every participant must cooperate via this helper.
A non-cooperating process can still corrupt the file. The point is to keep
two cooperating VibeSOP processes (e.g. launchd tick + interactive CLI)
from racing each other on the same JSONL / JSON state file.

Lock semantics:
    - Exclusive (default) — blocks other exclusive AND shared acquirers.
    - Shared (``shared=True``) — blocks exclusive, allows concurrent shared
      on POSIX. **Best-effort on Windows**: ``msvcrt`` has no shared lock,
      so ``shared=True`` degenerates to exclusive there (conservative but
      safe — do not write tests asserting two shared acquirers coexist
      under the msvcrt branch).
    - Blocking (default) — waits until acquired.
    - Non-blocking (``blocking=False``) — raises ``CouldNotLock`` if held.

Lock-file naming contract (gate44):
    - ALWAYS pass a sibling lock file, never the data file itself. Locking
      the data file breaks on Windows (msvcrt byte-range lock vs a second
      append handle; ``os.replace`` onto a held handle) and on POSIX an
      atomic rename inside the critical section swaps the inode out from
      under the lock.
    - New code derives the lock path as ``path.with_name(path.name + ".lock")``
      (``x.jsonl`` → ``x.jsonl.lock``). Do NOT use ``with_suffix(".lock")``
      (``x.jsonl``/``x.json`` in one dir would collide on ``x.lock``).
    - Existing call sites using other shapes (``with_suffix(".lock")``,
      explicit stem names) MUST NOT be renamed without a migration: the
      on-disk lock file is the lock's identity — renaming it lets two
      processes hold "the" lock simultaneously during a rolling upgrade.
    - Lock files are opened ``a+`` and never unlinked by this helper. Do
      not "clean up" ``*.lock`` files while the app may be running.

Usage::

    from vibesop.utils.file_lock import cross_process_lock

    with cross_process_lock(lock_path):
        ...  # exclusive access to data file
"""

from __future__ import annotations

import errno
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class CouldNotLock(OSError):
    """Raised when a non-blocking lock acquire finds the lock held."""


_LOCK_BYTE = 0  # msvcrt locks a byte range starting at the current position
_LOCK_NBYTES = 1  # only one byte needs to be locked


@contextmanager
def cross_process_lock(
    lock_path: Path,
    *,
    shared: bool = False,
    blocking: bool = True,
    spin_interval_s: float = 0.05,
    max_spin_attempts: int = 200,  # ~10s at 50ms intervals
) -> Generator[None, None, None]:
    """Acquire an advisory lock on ``lock_path`` for the duration of the block.

    Args:
        lock_path: Path whose existence + lock-byte will gate concurrency.
            The file is created if missing. Use a sibling ``.lock`` file
            rather than the data file so atomic rename inside the critical
            section does not release the lock.
        shared: ``True`` for LOCK_SH (multiple readers); ``False`` (default)
            for LOCK_EX (exclusive).
        blocking: ``True`` (default) to wait until acquired; ``False`` to
            raise ``CouldNotLock`` immediately if the lock is held.
        spin_interval_s: Sleep between retries on Windows (msvcrt) blocking
            acquire. POSIX ``flock`` blocks in-kernel so this is unused.
        max_spin_attempts: Upper bound on Windows spin iterations before
            giving up (approx ``spin_interval_s * max_spin_attempts`` seconds).

    Raises:
        CouldNotLock: Non-blocking acquire found the lock held.
        OSError: Underlying IO error creating / opening the lock file.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # ``a+`` mode doesn't truncate the file (a thing ``w`` would do) and is
    # writable on Windows. The lock file's *contents* are irrelevant — only
    # its inode + flock/locking state matters.
    f = lock_path.open("a+", encoding="utf-8")
    try:
        _acquire(
            f.fileno(),
            shared=shared,
            blocking=blocking,
            spin_interval_s=spin_interval_s,
            max_spin_attempts=max_spin_attempts,
        )
        try:
            yield
        finally:
            _release(f.fileno())
    finally:
        f.close()


def _acquire(
    fd: int,
    *,
    shared: bool,
    blocking: bool,
    spin_interval_s: float,
    max_spin_attempts: int,
) -> None:
    """Dispatch to fcntl (POSIX) or msvcrt (Windows)."""
    try:
        import fcntl
    except ImportError:
        _acquire_msvcrt(
            fd,
            shared=shared,
            blocking=blocking,
            spin_interval_s=spin_interval_s,
            max_spin_attempts=max_spin_attempts,
        )
        return

    op = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    if not blocking:
        op |= fcntl.LOCK_NB
    try:
        fcntl.flock(fd, op)
    except OSError as e:
        # LOCK_NB + held lock raises errno=EAGAIN/EWOULDBLOCK on POSIX.
        if not blocking and e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
            raise CouldNotLock(str(e)) from e
        raise


def _release(fd: int) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        # msvcrt requires the file position to be on the locked byte.
        import os

        os.lseek(fd, _LOCK_BYTE, 0)  # SEEK_SET
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_NBYTES)
        except OSError as e:
            # Already released or fd closed — nothing useful to do.
            logger.debug("msvcrt unlock failed (fd=%s): %s", fd, e)
        return

    fcntl.flock(fd, fcntl.LOCK_UN)


def _acquire_msvcrt(
    fd: int,
    *,
    shared: bool,
    blocking: bool,
    spin_interval_s: float,
    max_spin_attempts: int,
) -> None:
    """Windows path: ``msvcrt.locking`` on one byte at offset 0."""
    import msvcrt
    import os

    # Non-blocking modes — we implement blocking ourselves via a bounded spin
    # so the caller controls the timeout (msvcrt.LK_LOCK spins internally for
    # 10s before failing, which is harder to reason about).
    mode_nonblocking = msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK

    os.lseek(fd, _LOCK_BYTE, 0)  # position on the byte we'll lock

    if not blocking:
        try:
            msvcrt.locking(fd, mode_nonblocking, _LOCK_NBYTES)
            return
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EDEADLK):
                raise CouldNotLock(str(e)) from e
            raise

    # Blocking path: spin on the non-blocking mode ourselves so we have a
    # bounded retry budget. Re-lseek each iteration: a failed _locking call
    # may leave the file position moved, and locking from the wrong offset
    # would silently lock (and later unlock) a different byte.
    last_err: OSError | None = None
    for _ in range(max_spin_attempts):
        os.lseek(fd, _LOCK_BYTE, 0)  # SEEK_SET
        try:
            msvcrt.locking(fd, mode_nonblocking, _LOCK_NBYTES)
            return
        except OSError as e:
            last_err = e
            if e.errno not in (errno.EACCES, errno.EDEADLK):
                raise
            time.sleep(spin_interval_s)
    raise OSError(
        f"timed out acquiring Windows lock after {max_spin_attempts} attempts: {last_err}"
    )


__all__ = ["CouldNotLock", "cross_process_lock"]
