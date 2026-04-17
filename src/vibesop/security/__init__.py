"""Security module for VibeSOP.

This module provides security scanning and path validation to protect
against malicious content and path traversal attacks.

Public API:
    - SecurityScanner: Scan text/files for security threats
    - PathSafety: Validate paths and prevent traversal attacks
    - SecurityError: Base security exception
    - PathTraversalError: Path traversal attack detected
    - UnsafeContentError: Unsafe content detected
    - ScanResult: Result of security scan
    - Threat: Detected security threat
    - RiskLevel: Risk level (CRITICAL, HIGH, MEDIUM, LOW)
    - ThreatType: Type of security threat

Example:
    >>> from vibesop.security import SecurityScanner, PathSafety
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
    AuditResult,
    SkillSecurityAuditor,
    ThreatPattern,
    audit_skill,
)
from vibesop.security.skill_auditor import (
    ThreatLevel as SkillThreatLevel,
)

__all__ = [
    "AuditResult",
    "PathOverlapError",
    # Path safety
    "PathSafety",
    "PathTraversalError",
    "RiskLevel",
    "ScanResult",
    "SecurityError",
    # Scanner
    "SecurityScanner",
    # Skill auditor
    "SkillSecurityAuditor",
    "SkillThreatLevel",
    # Rules
    "Threat",
    "ThreatPattern",
    "ThreatType",
    "UnsafeContentError",
    "audit_skill",
]

from vibesop._version import __version__
