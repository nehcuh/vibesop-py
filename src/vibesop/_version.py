"""VibeSOP version information.

This file contains the version information for VibeSOP.
It is the single source of truth for the version number.

Version Format: MAJOR.MINOR.PATCH
- MAJOR: Incompatible API changes
- MINOR: Backwards-compatible functionality additions
- PATCH: Backwards-compatible bug fixes
"""

# Version components
MAJOR = 5
MINOR = 3
PATCH = 0

# Version metadata
VERSION_SUFFIX = ""  # e.g., "a1", "b1", "rc1", "" for stable
DEV_VERSION = False  # Set to True for development versions

# Full version string with optional suffix
if VERSION_SUFFIX:
    __version__ = f"{MAJOR}.{MINOR}.{PATCH}{VERSION_SUFFIX}"
elif DEV_VERSION:
    __version__ = f"{MAJOR}.{MINOR}.{PATCH}.dev"
else:
    __version__ = f"{MAJOR}.{MINOR}.{PATCH}"
