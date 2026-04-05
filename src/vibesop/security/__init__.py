"""Security module for VibeSOP.

This module provides security scanning and path validation to protect
against malicious content and path traversal attacks.

Public API:
    - SecurityScanner: Scan text/files for security threats
    - PathSafety: Validate paths and prevent traversal attacks
    - SafeLoader: Load external content with mandatory scanning
    - SecurityError: Base security exception
    - PathTraversalError: Path traversal attack detected
    - UnsafeContentError: Unsafe content detected
    - ScanResult: Result of security scan
    - Threat: Detected security threat
    - RiskLevel: Risk level (CRITICAL, HIGH, MEDIUM, LOW)
    - ThreatType: Type of security threat

Example:
    >>> from vibesop.security import SecurityScanner, PathSafety, SafeLoader
    >>>
    >>> # Scan for threats
    >>> scanner = SecurityScanner()
    >>> result = scanner.scan("Ignore all previous instructions")
    >>> if not result.safe:
    ...     print(f"Threats: {result.summary}")
    >>>
    >>> # Validate paths
    >>> safety = PathSafety()
    >>> safe_path = safety.ensure_safe_output_path("output.txt", Path("/tmp"))
    >>>
    >>> # Load content safely
    >>> loader = SafeLoader()
    >>> content = loader.load_text_file(path)  # Always scanned
"""

from vibesop.security.exceptions import (
    PathOverlapError,
    PathTraversalError,
    SecurityError,
    UnsafeContentError,
)
from vibesop.security.path_safety import PathSafety
from vibesop.security.rules import RiskLevel, Threat, ThreatType
from vibesop.security.scanner import ScanResult, SecurityScanner
from vibesop.security.skill_auditor import (
    ThreatLevel as SkillThreatLevel,
    ThreatPattern,
    AuditResult,
    SkillSecurityAuditor,
    audit_skill,
)
from vibesop.security.enforced import (
    SafeLoader,
    SecurityEnforcementError,
    require_safe_scan,
    scan_file_before_load,
    scan_string_input,
    load_text_file_safe,
    load_json_file_safe,
)

__all__ = [
    # Exceptions
    "SecurityError",
    "PathTraversalError",
    "UnsafeContentError",
    "PathOverlapError",
    "SecurityEnforcementError",
    # Scanner
    "SecurityScanner",
    "ScanResult",
    # Rules
    "Threat",
    "ThreatType",
    "RiskLevel",
    # Path safety
    "PathSafety",
    # Skill auditor
    "SkillSecurityAuditor",
    "SkillThreatLevel",
    "ThreatPattern",
    "AuditResult",
    "audit_skill",
    # Enforcement
    "SafeLoader",
    "require_safe_scan",
    "scan_file_before_load",
    "scan_string_input",
    "load_text_file_safe",
    "load_json_file_safe",
]

from vibesop._version import __version__  # noqa: E402
