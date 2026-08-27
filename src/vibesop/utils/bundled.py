"""Locate data files bundled into the wheel via hatch force-include.

Wheel installs (pipx / uv tool / pip) do not ship the repo checkout, so
``<project_root>/core/...`` only exists in a dev clone. Bundled copies live
inside the package (``vibesop/builtin_skills``, ``vibesop/builtin_data/core``)
and are the fallback for every core-data reader.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

__all__ = [
    "bundled_core_file",
    "bundled_path",
    "is_vibesop_checkout",
    "resolve_builtin_skills_dir",
]


def bundled_path(*parts: str) -> Path:
    """Path under the installed ``vibesop`` package (wheel force-include target)."""
    import vibesop

    return Path(vibesop.__file__).parent.joinpath(*parts)


def is_vibesop_checkout(root: Path) -> bool:
    """True iff ``root`` is a VibeSOP source tree (not an arbitrary core/skills)."""
    pyproject = root / "pyproject.toml"
    skills = root / "core" / "skills"
    if not pyproject.is_file() or not skills.is_dir():
        return False
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return False
    name = data.get("project", {}).get("name")
    if not isinstance(name, str):
        return False
    return canonicalize_name(name) == "vibesop"


def _file_derived_checkout() -> Path:
    import vibesop

    return Path(vibesop.__file__).parent.parent.parent


def resolve_builtin_skills_dir(project_root: Path | None = None) -> Path:
    """First *existing* builtin skills dir: identified checkout, then wheel.

    Order:
    1. ``project_root/core/skills`` if ``project_root`` is a VibeSOP checkout
    2. wheel ``vibesop/builtin_skills``
    3. ``__file__``-derived checkout ``core/skills`` if that tree is VibeSOP

    A foreign ``cwd/core/skills`` (no ``[project].name = "vibesop"``) never
    wins. Returns the wheel path even when missing if nothing else exists.
    """
    if project_root is not None and is_vibesop_checkout(project_root):
        checkout = project_root / "core" / "skills"
        if checkout.is_dir():
            return checkout
    wheel = bundled_path("builtin_skills")
    if wheel.is_dir():
        return wheel
    derived = _file_derived_checkout()
    if is_vibesop_checkout(derived):
        checkout = derived / "core" / "skills"
        if checkout.is_dir():
            return checkout
    return wheel


def bundled_core_file(name: str, project_root: Path | None = None) -> Path:
    """Resolve ``core/<name>`` (registry/policies), not builtin skills.

    Skills use :func:`resolve_builtin_skills_dir`. Registry YAML is a data
    file: any existing ``project_root/core/<name>`` wins so tests and a
    checkout overlay keep working. Identity gating here would hide a
    planted ``registry.yaml`` on a scratch project_root.
    """
    if project_root is not None:
        repo_copy = project_root / "core" / name
        if repo_copy.exists():
            return repo_copy
    return bundled_path("builtin_data", "core", name)
