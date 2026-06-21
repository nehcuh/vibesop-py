"""VibeSOP version information.

Single source of truth: pyproject.toml [project.version].
This module reads the version via importlib.metadata at import time.

Version Format: MAJOR.MINOR.PATCH
- MAJOR: Incompatible API changes
- MINOR: Backwards-compatible functionality additions
- PATCH: Backwards-compatible bug fixes
"""

import importlib.metadata

__version__ = importlib.metadata.version("vibesop")

# Parsed version components (derived from __version__, for backward compat)
_parts = __version__.split(".")
MAJOR = int(_parts[0])
MINOR = int(_parts[1])
_patch_str = _parts[2].split("+")[0].split("a")[0].split("b")[0].split("rc")[0].split(".dev")[0]
PATCH = int(_patch_str)
VERSION_SUFFIX = ""
DEV_VERSION = False

# Preserve suffix/dev parsing for any code that imports these
_suffix = _parts[2] if len(_parts) > 2 else ""
for sep in ("a", "b", "rc"):
    if sep in _suffix:
        VERSION_SUFFIX = _suffix[_suffix.index(sep) :]  # pyright: ignore[reportConstantRedefinition]
        break
if ".dev" in _suffix:
    DEV_VERSION = True  # pyright: ignore[reportConstantRedefinition]
