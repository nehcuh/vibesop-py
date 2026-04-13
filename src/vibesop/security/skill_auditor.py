"""Skill security auditor for external skill validation.

This module provides security validation specifically for skill files,
implementing protections against SKILL-INJECT style attacks.

Based on research from:
- "I'm Sorry, Dave, I'm Afraid I Can't Do That": Analyzing Prompt Injection
  and Security-Grounded Behavior in Language Models (Mazarelli et al., 2023)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from vibesop.security import PathSafety, SecurityScanner
from vibesop.security.exceptions import PathTraversalError, UnsafeContentError


class ThreatLevel(StrEnum):
    """Severity level of security threats."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatPattern:
    """A security threat pattern.

    Attributes:
        name: Human-readable name
        pattern: Regex pattern to detect
        level: Threat severity
        category: Type of threat
        description: What this threat represents
    """

    name: str
    pattern: str
    level: ThreatLevel
    category: str
    description: str

    def matches(self, text: str) -> bool:
        """Check if this pattern matches the text."""
        return bool(re.search(self.pattern, text, re.IGNORECASE | re.DOTALL))


@dataclass
class AuditResult:
    """Result of security audit.

    Attributes:
        is_safe: Whether the skill passed security audit
        threats: List of threats detected
        risk_level: Highest risk level found
        reason: Human-readable explanation
        audit_time: When audit was performed
    """

    is_safe: bool
    threats: list[ThreatPattern] = field(default_factory=list)
    risk_level: ThreatLevel = ThreatLevel.SAFE
    reason: str = ""
    audit_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_safe": self.is_safe,
            "threats": [
                {
                    "name": t.name,
                    "level": t.level.value,
                    "category": t.category,
                    "description": t.description,
                }
                for t in self.threats
            ],
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "audit_time": self.audit_time.isoformat(),
        }


class SkillSecurityAuditor:
    """Security auditor for skill files.

    Implements protections against:
    - Path traversal attacks
    - Prompt injection attempts
    - Role hijacking
    - Instruction injection
    - Privilege escalation
    - Command injection patterns

    Example:
        >>> auditor = SkillSecurityAuditor()
        >>> result = auditor.audit_skill_file(Path("skills/external/SKILL.md"))
        >>> if result.is_safe:
        ...     print("Skill is safe to load")
        ... else:
        ...     print(f"Unsafe: {result.reason}")
    """

    # Allowed skill directories (whitelist)
    ALLOWED_BASE_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "skills",
        Path.home() / ".vibe" / "skills",
    ]

    # Danger patterns (from SKILL-INJECT research)
    THREAT_PATTERNS: ClassVar[list[ThreatPattern]] = [
        # Prompt injection patterns
        ThreatPattern(
            name="Ignore Instructions",
            pattern=r"ignore\s+(all\s+)?(previous|prior|the|above|earlier|existing)\s+(instructions?|commands?|directives?|rules?|constraints?)",
            level=ThreatLevel.CRITICAL,
            category="prompt_injection",
            description="Attempts to ignore previous instructions",
        ),
        ThreatPattern(
            name="System Command Injection",
            pattern=r"<\|.*\.(system|exec|eval|__import__|open|subprocess|popen)\s*\(",
            level=ThreatLevel.CRITICAL,
            category="code_injection",
            description="Attempts to execute system commands",
        ),
        ThreatPattern(
            name="Role Hijacking",
            pattern=r"(you\s+are|you're|act\s+as|become|pretend\s+to\s+be|roleplay\s+as)\s*(a|an|the)\s*(developer|admin|root|god|assistant|ai|system)",
            level=ThreatLevel.HIGH,
            category="role_hijacking",
            description="Attempts to hijack or change system role",
        ),
        ThreatPattern(
            name="Instruction Override",
            pattern=r"(override|rewrite|replace|ignore|bypass|disable|deactivate)\s+(the\s+)?(security|validation|checks?|filters?|protection)",
            level=ThreatLevel.HIGH,
            category="instruction_injection",
            description="Attempts to override security measures",
        ),
        ThreatPattern(
            name="Privilege Escalation",
            pattern=r"(give\s+me|i\s+need|i\s+want|grant)\s*(admin|root|sudo|privilege|access|permission)",
            level=ThreatLevel.MEDIUM,
            category="privilege_escalation",
            description="Requests for elevated privileges",
        ),
        ThreatPattern(
            name="Output Manipulation",
            pattern=r"(print|output|display|show|return)\s*(the\s+)?(system|prompt|instructions?|configuration|settings|secrets|passwords?|keys?|tokens?)",
            level=ThreatLevel.MEDIUM,
            category="data_exfiltration",
            description="Attempts to access sensitive system data",
        ),
        ThreatPattern(
            name="Context Disclosure",
            pattern=r"what(?:['']?s|s)\s+(?:your|the)\s+(?:context|instructions?|prompt|system\s+message|configuration)",
            level=ThreatLevel.LOW,
            category="information_disclosure",
            description="Attempts to extract internal context",
        ),
        ThreatPattern(
            name="Jailbreak Attempt",
            pattern=r"(jailbreak|jail\s*break|dan\s*mode|developer\s*mode|admin\s*mode|unrestricted)",
            level=ThreatLevel.HIGH,
            category="jailbreak",
            description="Attempts to bypass safety measures",
        ),
    ]

    def __init__(
        self,
        allowed_paths: list[Path] | None = None,
        strict_mode: bool = True,
        project_root: Path | str | None = None,
    ):
        """Initialize the skill security auditor.

        Args:
            allowed_paths: Whitelist of allowed skill directories
            strict_mode: If True, reject on any threat; if False, warn only
            project_root: Project root (to include project skills in allowed paths)
        """
        self._strict_mode = strict_mode
        self._scanner = SecurityScanner()
        self._path_safety = PathSafety()

        # Set up allowed paths
        if allowed_paths is None:
            self._allowed_paths = self.ALLOWED_BASE_PATHS.copy()

            # Add project skills if project_root is specified
            if project_root is not None:
                project_root = Path(project_root).resolve()
                self._allowed_paths.append(project_root / "core" / "skills")
                self._allowed_paths.append(project_root / ".vibe" / "skills")
        else:
            self._allowed_paths = [Path(p).resolve() for p in allowed_paths]

    def audit_skill_file(
        self,
        skill_path: Path,
    ) -> AuditResult:
        """Audit a skill file for security threats.

        Args:
            skill_path: Path to SKILL.md file

        Returns:
            AuditResult with findings
        """
        threats = []
        skill_path = Path(skill_path)

        # 1. Path validation
        try:
            self._validate_path(skill_path)
        except (PathTraversalError, ValueError) as e:
            return AuditResult(
                is_safe=False,
                risk_level=ThreatLevel.CRITICAL,
                reason=f"Path validation failed: {e}",
            )

        # 2. Read content
        if not skill_path.exists():
            return AuditResult(
                is_safe=False,
                risk_level=ThreatLevel.CRITICAL,
                reason="Skill file not found",
            )

        try:
            content = skill_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return AuditResult(
                is_safe=False,
                risk_level=ThreatLevel.HIGH,
                reason=f"Failed to read skill file: {e}",
            )

        # 3. Scan with threat patterns
        for pattern in self.THREAT_PATTERNS:
            if pattern.matches(content):
                threats.append(pattern)

        # 4. Scan with security scanner
        try:
            scan_result = self._scanner.scan(content)
            if not scan_result.safe:
                # Convert scanner threats to our format
                for scan_threat in scan_result.threats:
                    threat = ThreatPattern(
                        name=scan_threat.type.value,
                        pattern=scan_threat.type.value,
                        level=self._risk_level_from_scan(scan_threat.risk_level),
                        category="scanner_detected",
                        description=scan_threat.description or "Detected by scanner",
                    )
                    threats.append(threat)
        except UnsafeContentError:
            return AuditResult(
                is_safe=False,
                risk_level=ThreatLevel.CRITICAL,
                reason="Unsafe content detected by scanner",
            )

        # 5. Calculate result
        if not threats:
            return AuditResult(
                is_safe=True,
                reason="Skill passed security audit",
            )

        # Find highest risk level
        risk_order = [
            ThreatLevel.CRITICAL,
            ThreatLevel.HIGH,
            ThreatLevel.MEDIUM,
            ThreatLevel.LOW,
        ]
        highest_risk = ThreatLevel.LOW
        for risk in risk_order:
            if any(t.level == risk for t in threats):
                highest_risk = risk
                break

        # Build reason message
        threat_names = [t.name for t in threats]
        reason = f"Detected {len(threats)} threat(s): {', '.join(threat_names)}"

        # Determine if safe based on mode
        is_safe = self._determine_safety(highest_risk)

        return AuditResult(
            is_safe=is_safe,
            threats=threats,
            risk_level=highest_risk,
            reason=reason,
        )

    def audit_skill_directory(
        self,
        skill_dir: Path,
    ) -> AuditResult:
        """Audit all files in a skill directory.

        Args:
            skill_dir: Path to skill directory

        Returns:
            Combined audit result
        """
        skill_dir = Path(skill_dir)

        # Find all skill files
        skill_files = []
        if (skill_dir / "SKILL.md").exists():
            skill_files.append(skill_dir / "SKILL.md")
        else:
            skill_files.extend(skill_dir.glob("*.md"))
            skill_files.extend(skill_dir.glob("*.yaml"))
            skill_files.extend(skill_dir.glob("*.yml"))

        if not skill_files:
            return AuditResult(
                is_safe=False,
                reason="No skill files found in directory",
            )

        # Audit each file
        all_threats = []
        highest_risk = ThreatLevel.SAFE

        for skill_file in skill_files:
            result = self.audit_skill_file(skill_file)
            all_threats.extend(result.threats)

            # Update highest risk
            result_risk = result.risk_level
            risk_order = [
                ThreatLevel.CRITICAL,
                ThreatLevel.HIGH,
                ThreatLevel.MEDIUM,
                ThreatLevel.LOW,
                ThreatLevel.SAFE,
            ]
            for risk in risk_order:
                if result_risk == risk:
                    if risk_order.index(risk) < risk_order.index(highest_risk):
                        highest_risk = risk
                    break

        # Build combined result
        if not all_threats:
            return AuditResult(
                is_safe=True,
                reason="All files passed security audit",
            )

        is_safe = self._determine_safety(highest_risk)

        return AuditResult(
            is_safe=is_safe,
            threats=all_threats,
            risk_level=highest_risk,
            reason=f"Directory audit: {len(all_threats)} threat(s) across {len(skill_files)} file(s)",
        )

    def validate_path(self, path: Path) -> bool:
        """Validate that a path is allowed.

        Args:
            path: Path to validate

        Returns:
            True if path is allowed

        Raises:
            PathTraversalError: If path attempts to traverse outside allowed dirs
        """
        try:
            self._validate_path(Path(path))
            return True
        except (PathTraversalError, ValueError):
            return False

    def _validate_path(self, path: Path) -> None:
        """Validate path (raises exception if invalid)."""
        path = Path(path).resolve()

        # Check if path is within allowed directories
        is_allowed = False
        for raw_allowed_base in self._allowed_paths:
            resolved_base = raw_allowed_base.resolve()
            try:
                path.relative_to(resolved_base)
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed:
            raise PathTraversalError(
                message=f"Path {path} is not within allowed directories",
                path=str(path),
                base_dir=" or ".join(str(p) for p in self._allowed_paths),
            )

    def _determine_safety(self, risk_level: ThreatLevel) -> bool:
        """Determine if content is safe based on risk level and mode.

        Args:
            risk_level: Highest risk level detected

        Returns:
            True if content is considered safe
        """
        if not self._strict_mode:
            # Non-strict mode: only critical/high are unsafe
            return risk_level in (ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM)
        else:
            # Strict mode: any threat is unsafe
            return risk_level == ThreatLevel.SAFE

    def _risk_level_from_scan(self, scan_risk: Any) -> ThreatLevel:
        """Convert scanner risk level to ThreatLevel.

        Args:
            scan_risk: Risk level from SecurityScanner

        Returns:
            ThreatLevel
        """
        from vibesop.security.rules import RiskLevel

        mapping = {
            RiskLevel.CRITICAL: ThreatLevel.CRITICAL,
            RiskLevel.HIGH: ThreatLevel.HIGH,
            RiskLevel.MEDIUM: ThreatLevel.MEDIUM,
            RiskLevel.LOW: ThreatLevel.LOW,
        }
        return mapping.get(scan_risk, ThreatLevel.MEDIUM)

    def add_threat_pattern(self, pattern: ThreatPattern) -> None:
        """Add a custom threat pattern.

        Args:
            pattern: ThreatPattern to add
        """
        self.THREAT_PATTERNS.append(pattern)

    def add_allowed_path(self, path: Path | str) -> None:
        """Add an allowed base path.

        Args:
            path: Path to add to whitelist
        """
        self._allowed_paths.append(Path(path).resolve())

    def get_allowed_paths(self) -> list[Path]:
        """Get list of allowed base paths.

        Returns:
            Copy of allowed paths list
        """
        return self._allowed_paths.copy()


# Convenience functions


def audit_skill(
    skill_path: Path | str,
    strict_mode: bool = True,
    project_root: Path | str | None = None,
) -> AuditResult:
    """Convenience function to audit a skill.

    Args:
        skill_path: Path to SKILL.md file or directory
        strict_mode: Whether to use strict mode
        project_root: Project root (to include project skills)

    Returns:
        AuditResult

    Example:
        >>> result = audit_skill("skills/external/SKILL.md")
        >>> if result.is_safe:
        ...     print("Safe to load")
    """
    auditor = SkillSecurityAuditor(
        strict_mode=strict_mode,
        project_root=project_root or Path.cwd(),
    )
    return auditor.audit_skill_file(Path(skill_path))


__all__ = [
    "AuditResult",
    "SkillSecurityAuditor",
    "ThreatLevel",
    "ThreatPattern",
    "audit_skill",
]
