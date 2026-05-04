"""VibeSOP constants.

This module contains all constant values used throughout VibeSOP,
including version information, routing thresholds, cache settings, and LLM configuration.
"""

# ============================================
# Version Information
# ============================================
MANIFEST_VERSION = "1.0.0"
PYTHON_MIN_VERSION = (3, 12)

# ============================================
# Trusted Skill Packs
# ============================================
TRUSTED_PACKS: dict[str, str] = {
    "superpowers": "https://github.com/obra/superpowers",
    "gstack": "https://github.com/garrytan/gstack",
    "omx": "https://github.com/Yeachan-Heo/oh-my-codex",
}


# ============================================
# Cache Configuration
# ============================================
class CacheSettings:
    """Cache configuration settings."""

    # Default TTL (time-to-live) in seconds
    DEFAULT_TTL = 86400  # 24 hours

    # Maximum cache size
    MAX_CACHE_SIZE = 1000

    # Cache directory
    DEFAULT_CACHE_DIR = ".vibe/cache"


# ============================================
# File System Configuration
# ============================================
class FileSystemSettings:
    """File system related settings."""

    # Default encoding for text files
    DEFAULT_ENCODING = "utf-8"

    # Fallback encoding for text files
    FALLBACK_ENCODING = "latin-1"

    # Maximum file size for scanning (10 MB)
    MAX_SCAN_FILE_SIZE = 10 * 1024 * 1024

    # Directory names
    CONFIG_DIR = ".vibe"
    CACHE_DIR = "cache"
    SKILLS_DIR = "skills"
    HOOKS_DIR = "hooks"


# ============================================
# Preference Learning Configuration
# ============================================
class PreferenceSettings:
    """Preference learning system settings."""

    # Number of days after which preference data decays
    DECAY_DAYS = 30

    # Minimum samples before preference score is reliable
    MIN_SAMPLES = 3

    # Weight decay rate per day
    DECAY_RATE = 0.95
