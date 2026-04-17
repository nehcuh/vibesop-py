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
}


# ============================================
# Routing Configuration
# ============================================
class RoutingThresholds:
    """Confidence thresholds for skill routing."""

    # AI routing confidence threshold
    AI_TRIAGE_CONFIDENCE = 0.6

    # Semantic matching thresholds
    SEMANTIC_SIMILARITY_MIN = 0.4
    SEMANTIC_SIMILARITY_THRESHOLD = 0.5
    FUZZY_SIMILARITY_THRESHOLD = 0.7

    # Maximum number of alternative skills to suggest
    MAX_ALTERNATIVE_SKILLS = 3


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
# LLM Configuration
# ============================================
class LLMSettings:
    """LLM provider configuration."""

    # Maximum retries for API calls
    MAX_RETRIES = 3

    # Request timeout in seconds
    TIMEOUT = 30.0

    # Temperature for generation (0.0 to 1.0)
    DEFAULT_TEMPERATURE = 0.3

    # Maximum tokens for responses
    MAX_TOKENS = 300

    # Minimum required confidence for auto-selection
    AUTO_SELECTION_THRESHOLD = 0.6


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
# Security Configuration
# ============================================
class SecuritySettings:
    """Security and validation settings."""

    # Maximum recursion depth for path validation
    MAX_PATH_DEPTH = 20

    # Path traversal protection enabled
    PREVENT_TRAVERSAL = True

    # Content scanning enabled
    ENABLE_SCANNING = True

    # Maximum content length for scanning
    MAX_SCAN_CONTENT_LENGTH = 1_000_000


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


# ============================================
# Template Configuration
# ============================================
class TemplateSettings:
    """Jinja2 template configuration."""

    # Template autoescape setting
    AUTOESCAPE = False

    # Trim whitespace
    TRIM_BLOCKS = True
    LSTRIP_BLOCKS = True


# ============================================
# HTTP/Network Configuration
# ============================================
class NetworkSettings:
    """Network and HTTP configuration."""

    # Connection timeout in seconds
    CONNECTION_TIMEOUT = 10.0

    # Read timeout in seconds
    READ_TIMEOUT = 30.0

    # Maximum number of connections
    MAX_CONNECTIONS = 100

    # Keep-alive timeout
    KEEPALIVE_EXPIRY = 5.0
