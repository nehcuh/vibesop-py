"""Empirical symlink capability probing.

Windows requires SeCreateSymbolicLinkPrivilege (Developer Mode or an
elevated process) to create symlinks; when unavailable, VibeSOP falls
back to copying skill directories. Capability is probed empirically —
never inferred from the platform — because the privilege varies per
machine and transient failures (e.g. Defender scanning the probe path)
are possible.

Cache discipline (adversarial review M5): only positive results are
cached. A transient ``False`` must never be cached, otherwise one
unlucky probe would disable symlinks for the rest of the process.
Tests that mock symlink creation must call :func:`clear_cache` in
setup so stale positive cache entries cannot leak across tests.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories confirmed to support directory symlinks. Only True is
# ever stored; failures are re-probed on the next call.
_probe_cache: dict[str, bool] = {}


def can_create_dir_symlink(directory: Path) -> bool:
    """Probe whether directory symlinks can be created inside *directory*.

    Creates *directory* when missing, then creates a dot-prefixed probe
    symlink and removes it again. The result is cached per directory —
    but only on success (see module docstring).

    Args:
        directory: Directory in which to attempt the probe symlink.

    Returns:
        True when a directory symlink was created and cleaned up
        successfully; False on any OSError (e.g. WinError 1314,
        privilege not held).
    """
    key = os.path.normcase(str(directory))
    if _probe_cache.get(key):
        return True

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.debug("symlink probe: cannot create directory %s: %s", directory, e)
        return False

    # uuid suffix avoids collision with stale residue from a crashed process
    # reusing the same pid (FileExistsError would permanently read as False).
    probe = directory / f".vibesop-symlink-probe-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        probe.symlink_to(directory, target_is_directory=True)
    except OSError as e:
        logger.debug("symlink probe failed under %s: %s", directory, e)
        return False
    try:
        _probe_cache[key] = True
        return True
    finally:
        try:
            probe.unlink()
        except OSError as e:
            # Residue is dot-prefixed and harmless; log for traceability.
            logger.debug("failed to remove symlink probe %s: %s", probe, e)


def clear_cache() -> None:
    """Reset the probe cache (for tests that mock symlink creation)."""
    _probe_cache.clear()
