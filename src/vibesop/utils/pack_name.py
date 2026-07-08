"""Pack-name sanitization helpers.

Pack names are used to build filesystem paths (install target directory, lock
file, etc.). Reject any name that could escape the intended parent directory.
"""

from __future__ import annotations

from pathlib import Path


def sanitize_pack_name(name: str) -> str:
    """Return *name* if it is a safe, flat pack identifier.

    Raises:
        ValueError: If the name is empty, a relative path component (``..``),
            contains path separators, starts with a dot, or normalizes to
            anything other than itself.
    """
    if not name or name in (".", ".."):
        raise ValueError(f"invalid pack name: {name!r}")
    if "/" in name or "\\" in name or name.startswith(".") or "\x00" in name:
        raise ValueError(f"invalid pack name: {name!r}")

    parsed = Path(name)
    if parsed.name != name or len(parsed.parts) != 1:
        raise ValueError(f"invalid pack name: {name!r}")
    return name
