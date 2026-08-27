"""Locate data files bundled into the wheel via hatch force-include.

Wheel installs (pipx / uv tool / pip) do not ship the repo checkout, so
``<project_root>/core/...`` only exists in a dev clone. Bundled copies live
inside the package (``vibesop/builtin_skills``, ``vibesop/builtin_data/core``)
and are the fallback for every core-data reader.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["bundled_core_file", "bundled_path"]


def bundled_path(*parts: str) -> Path:
    """Path under the installed ``vibesop`` package (wheel force-include target)."""
    import vibesop

    return Path(vibesop.__file__).parent.joinpath(*parts)


def bundled_core_file(name: str, project_root: Path | None = None) -> Path:
    """Resolve ``core/<name>``: repo checkout wins, wheel bundle is the fallback."""
    if project_root is not None:
        repo_copy = project_root / "core" / name
        if repo_copy.exists():
            return repo_copy
    return bundled_path("builtin_data", "core", name)
