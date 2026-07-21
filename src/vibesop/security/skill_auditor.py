"""Skill security auditor for external skill validation.

Validates skills against the SKILL-INJECT threat model (cf. Mazarelli et al.,
"Skill Injection Attacks on AI Agent Platforms", 2023) which describes how
malicious SKILL.md files can exfiltrate data or manipulate agent behavior.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from vibesop.security import PathSafety, SecurityScanner
from vibesop.security.exceptions import PathTraversalError, UnsafeContentError

logger = logging.getLogger(__name__)


class ThreatLevel(StrEnum):
    """Severity level of security threats."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatPattern:
    """A security threat pattern."""

    name: str
    pattern: str
    level: ThreatLevel
    category: str
    description: str

    def matches(self, text: str) -> bool:
        return bool(re.search(self.pattern, text, re.IGNORECASE | re.DOTALL))


@dataclass
class AuditResult:
    """Result of security audit."""

    is_safe: bool
    threats: list[ThreatPattern] = field(default_factory=list)
    risk_level: ThreatLevel = ThreatLevel.SAFE
    reason: str = ""
    audit_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
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


@dataclass
class PackAuditResult:
    """Result of auditing all files in a pack directory.

    Used as a pre-install gate before any build script (BUILD.sh / setup.sh /
    .vibesop-build / package.json scripts) is executed. ``has_critical`` and
    ``has_high`` drive the install rejection logic; trusted packs downgrade
    HIGH to MEDIUM consistent with ``audit_skill_file``.
    """

    is_safe: bool
    has_critical: bool = False
    has_high: bool = False
    files_scanned: int = 0
    threats_by_file: dict[str, list[ThreatPattern]] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        affected = len(self.threats_by_file)
        if self.has_critical:
            return f"CRITICAL threats in {affected} file(s)"
        if self.has_high:
            return f"HIGH threats in {affected} file(s)"
        return f"{self.files_scanned} file(s) scanned, no critical/high threats"

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "has_critical": self.has_critical,
            "has_high": self.has_high,
            "files_scanned": self.files_scanned,
            "threats_by_file": {
                path: [
                    {"name": t.name, "level": t.level.value, "category": t.category}
                    for t in threats
                ]
                for path, threats in self.threats_by_file.items()
            },
        }


class SkillSecurityAuditor:
    """Security auditor for skill files."""

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

    # Shell-script-specific threat patterns (applied to .sh/.bash files).
    # These catch RCE primitives that prompt-injection patterns miss because
    # they look like normal shell idioms inside markdown prose.
    SHELL_THREAT_PATTERNS: ClassVar[list[ThreatPattern]] = [
        ThreatPattern(
            name="Curl Pipe Shell",
            pattern=r"(curl|wget)\s+[^|<>]+\|\s*(sh|bash|zsh|fish)\b",
            level=ThreatLevel.CRITICAL,
            category="remote_code_execution",
            description="Downloads and executes a remote shell payload",
        ),
        ThreatPattern(
            name="Reverse Shell",
            pattern=r"(bash|sh|zsh)\s+-i\s+>|/dev/tcp/|nc\s+-e|ncat\s+-e|socat\s+.*EXEC",
            level=ThreatLevel.CRITICAL,
            category="reverse_shell",
            description="Classic reverse-shell pattern",
        ),
        ThreatPattern(
            name="Shell Exfiltration via Process Substitution",
            pattern=r"<\s*\(\s*(curl|wget)|\$\(\s*(curl|wget)",
            level=ThreatLevel.HIGH,
            category="data_exfiltration",
            description="Process substitution with HTTP client for exfiltration",
        ),
        ThreatPattern(
            name="SSH Authorized Keys Modification",
            pattern=r"authorized_keys|~/?\.ssh/authorized_keys",
            level=ThreatLevel.HIGH,
            category="persistence",
            description="Modifies SSH authorized_keys for persistence",
        ),
        ThreatPattern(
            name="Cron / Launch Agent Persistence",
            pattern=r"(crontab\s+-|/etc/cron\.|~/Library/LaunchAgents/|/etc/systemd/system/)",
            level=ThreatLevel.HIGH,
            category="persistence",
            description="Installs a cron job or launch agent for persistence",
        ),
    ]

    # JavaScript / TypeScript-specific threat patterns.
    JS_THREAT_PATTERNS: ClassVar[list[ThreatPattern]] = [
        ThreatPattern(
            name="Eval Of Remote Payload",
            pattern=r"eval\s*\(\s*(atob|Buffer\.from|fetch|axios|require\(\s*['\"]http)",
            level=ThreatLevel.CRITICAL,
            category="code_injection",
            description="eval() of remote or encoded payload",
        ),
        ThreatPattern(
            name="Child Process Exec",
            pattern=r"(child_process|execSync|spawnSync|exec\()\s*[\(.]",
            level=ThreatLevel.HIGH,
            category="code_injection",
            description="Spawns a child process from JS",
        ),
    ]

    # Python-specific threat patterns (applied to .py files). Catches the RCE
    # primitives the prompt-injection THREAT_PATTERNS miss — a setup.py doing
    # os.system('curl|sh') or pickle.loads would otherwise pass the audit clean.
    PYTHON_THREAT_PATTERNS: ClassVar[list[ThreatPattern]] = [
        ThreatPattern(
            name="Python Shell Execution",
            pattern=r"(os\.system|os\.popen[2-4]?|os\.exec\w*|os\.spawn\w*|subprocess\.(run|call|Popen|check_(output|call))|pty\.spawn)\s*\(",
            level=ThreatLevel.HIGH,
            category="code_injection",
            description="Runs a shell/system command from Python",
        ),
        ThreatPattern(
            name="Python Exec / Eval",
            pattern=r"\bexec\s*\(|\beval\s*\(",
            level=ThreatLevel.HIGH,
            category="code_injection",
            description="exec()/eval() of dynamic code",
        ),
        ThreatPattern(
            name="Python Unsafe Deserialization",
            pattern=r"pickle\.(loads?|Unpickler)|marshal\.loads?",
            level=ThreatLevel.HIGH,
            category="code_injection",
            description="Unsafe deserialization (pickle/marshal) → arbitrary code",
        ),
        ThreatPattern(
            name="Python Dynamic Import Of Dangerous Module",
            pattern=r"__import__\s*\(\s*['\"](os|subprocess|socket|pty)",
            level=ThreatLevel.HIGH,
            category="data_exfiltration",
            description="Dynamic import of os/subprocess/socket/pty",
        ),
    ]

    # Max file size to scan (1 MiB) — avoids DoS on huge files in cloned packs.
    PACK_FILE_SIZE_LIMIT: ClassVar[int] = 1_048_576

    # File extensions audited by ``audit_pack_files`` (everything else skipped).
    PACK_AUDITED_EXTENSIONS: ClassVar[frozenset[str]] = frozenset(
        {
            ".sh",
            ".bash",
            ".vibesop-build",
            ".js",
            ".mjs",
            ".cjs",
            ".ts",
            ".tsx",
            ".py",
            ".md",
            ".yaml",
            ".yml",
            ".json",
        }
    )

    def __init__(
        self,
        allowed_paths: list[Path] | None = None,
        strict_mode: bool = True,
        project_root: Path | str | None = None,
    ):
        self._strict_mode = strict_mode
        self._scanner = SecurityScanner()
        self._path_safety = PathSafety()
        # Instance-local custom patterns (add_threat_pattern). Kept off the
        # shared ClassVar so one instance can't pollute another's pattern set.
        self._custom_threat_patterns: list[ThreatPattern] = []

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
        pack_name: str | None = None,
        source_url: str | None = None,
        pack_path: Path | None = None,
    ) -> AuditResult:
        """Audit a skill file for security threats."""
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

        # 3. Scan with threat patterns. Copy each match (dataclasses.replace)
        # so the trust-downgrade below mutates a per-audit copy, NEVER the
        # shared ClassVar object. Without this copy, auditing ONE trusted pack
        # that matches a HIGH pattern would set threat.level=MEDIUM on the
        # ClassVar instance itself, permanently blinding every subsequent audit
        # (incl. untrusted ones) for the process lifetime. (Critical, verified
        # by execution pre-fix.)
        for pattern in [*self.THREAT_PATTERNS, *self._custom_threat_patterns]:
            if pattern.matches(content):
                threats.append(replace(pattern))

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

        # 4.5. Trust store override — downgrade HIGH threats to MEDIUM
        # for packs the user has explicitly trusted or for built-in trusted packs.
        # F-10: user trust is bound to the pack's content hash; if the tree has
        # changed since approval, the downgrade is not applied. To avoid hashing
        # every pack on every audit, the hash is computed only for packs that are
        # actually present in the user trust store.
        is_trusted = False
        if pack_name or source_url:
            try:
                from vibesop.constants import TRUSTED_PACKS
                from vibesop.core.skills.trust import TrustStore
                from vibesop.utils.marker_files import MarkerFileManager

                store = TrustStore()
                is_builtin_trusted = pack_name and pack_name in TRUSTED_PACKS
                is_source_trusted = source_url and store.is_trusted_source(source_url)

                is_user_trusted = False
                if pack_name and pack_path is not None and pack_name in store.get_trusted_packs():
                    content_sha256 = MarkerFileManager().calculate_checksum(pack_path)
                    is_user_trusted = store.is_trusted_pack(
                        pack_name, content_sha256=content_sha256
                    )

                is_trusted = is_builtin_trusted or is_user_trusted or is_source_trusted

                if is_trusted:
                    for threat in threats:
                        if threat.level == ThreatLevel.HIGH:
                            threat.level = ThreatLevel.MEDIUM
            except Exception as e:
                logger.debug("Trust store lookup failed: %s", e)
                # Trust store is best-effort — proceed without trust downgrade

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

        # Determine if safe based on mode and trust status
        is_safe = self._determine_safety(highest_risk)

        # Trusted packs: downgrade + accept MEDIUM as safe
        if is_trusted and highest_risk in (
            ThreatLevel.SAFE,
            ThreatLevel.LOW,
            ThreatLevel.MEDIUM,
        ):
            is_safe = True

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
        """Audit all files in a skill directory."""
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

    def audit_pack_files(
        self,
        pack_dir: Path,
        pack_name: str | None = None,
    ) -> PackAuditResult:
        """Audit ALL files in a pack directory before any build script runs.

        Unlike ``audit_skill_directory`` (which only scans .md/.yaml), this
        method scans shell scripts, JS, JSON package.json scripts, and Python
        files. It exists to gate ``_run_post_install`` in ``PackInstaller``:
        if a CRITICAL pattern (curl|sh, reverse shell, eval(remote)) is found,
        installation is rejected before the build script ever executes.

        Args:
            pack_dir: Root directory of the cloned pack.
            pack_name: Pack name — used to consult the trust store for HIGH
                downgrades (consistent with ``audit_skill_file``).

        Returns:
            ``PackAuditResult`` with ``has_critical`` / ``has_high`` flags
            and per-file threat mapping.
        """
        pack_dir = Path(pack_dir)
        if not pack_dir.exists():
            return PackAuditResult(
                is_safe=False,
                has_critical=True,
                files_scanned=0,
            )

        type_patterns = self._pack_file_type_patterns()
        threats_by_file: dict[str, list[ThreatPattern]] = {}
        files_scanned = 0
        has_critical = False
        has_high = False

        for file_path in pack_dir.rglob("*"):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix not in type_patterns:
                continue
            try:
                if file_path.stat().st_size > self.PACK_FILE_SIZE_LIMIT:
                    continue
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                # Transient lock (e.g. Windows Defender scan) — file is
                # skipped from the audit; log so the gap is traceable.
                logger.debug("pack audit skipped unreadable file %s: %s", file_path, e)
                continue

            files_scanned += 1
            # Copy each match (replace) so consumers of PackAuditResult.threats_by_file
            # can't mutate the shared ClassVar/instance pattern objects.
            file_threats = [replace(p) for p in type_patterns[suffix] if p.matches(content)]
            if not file_threats:
                continue

            try:
                rel = str(file_path.relative_to(pack_dir))
            except ValueError:
                rel = str(file_path)
            threats_by_file[rel] = file_threats

            for threat in file_threats:
                if threat.level == ThreatLevel.CRITICAL:
                    has_critical = True
                elif threat.level == ThreatLevel.HIGH:
                    has_high = True

        # Trust store downgrade for HIGH (consistent with audit_skill_file).
        # CRITICAL is never downgraded — trust is not a license for RCE.
        is_trusted = self._is_pack_trusted(pack_name, pack_dir)
        effective_has_high = has_high and not is_trusted

        return PackAuditResult(
            is_safe=not has_critical and not effective_has_high,
            has_critical=has_critical,
            has_high=effective_has_high,
            files_scanned=files_scanned,
            threats_by_file=threats_by_file,
        )

    def _pack_file_type_patterns(self) -> dict[str, list[ThreatPattern]]:
        """Build suffix → patterns mapping for pack auditing."""
        # Include instance custom patterns so add_threat_pattern applies to pack
        # audits too (consistent with audit_skill_file), not just skill files.
        custom = self._custom_threat_patterns
        shell_patterns = [*self.THREAT_PATTERNS, *self.SHELL_THREAT_PATTERNS, *custom]
        js_patterns = [*self.THREAT_PATTERNS, *self.JS_THREAT_PATTERNS, *custom]
        # .py scanned with Python RCE primitives (was base-only → setup.py
        # os.system('curl|sh') / pickle.loads passed clean).
        python_patterns = [*self.THREAT_PATTERNS, *self.PYTHON_THREAT_PATTERNS, *custom]
        # .json (esp. package.json) scanned with shell patterns too — a
        # preinstall: "curl|sh" or reverse shell in package.json scripts is
        # executed by bun/npm on install (was base-only → passed clean).
        json_patterns = [*self.THREAT_PATTERNS, *self.SHELL_THREAT_PATTERNS, *custom]
        base_patterns = [*self.THREAT_PATTERNS, *custom]
        return {
            ".sh": shell_patterns,
            ".bash": shell_patterns,
            ".vibesop-build": shell_patterns,
            ".js": js_patterns,
            ".mjs": js_patterns,
            ".cjs": js_patterns,
            ".ts": js_patterns,
            ".tsx": js_patterns,
            ".py": python_patterns,
            ".md": base_patterns,
            ".yaml": base_patterns,
            ".yml": base_patterns,
            ".json": json_patterns,
        }

    @staticmethod
    def _is_pack_trusted(pack_name: str | None, pack_dir: Path | None = None) -> bool:
        if not pack_name:
            return False
        try:
            from pathlib import Path

            from vibesop.constants import TRUSTED_PACKS
            from vibesop.core.skills.trust import TrustStore
            from vibesop.utils.marker_files import MarkerFileManager

            store = TrustStore()
            if pack_name in TRUSTED_PACKS:
                return True

            if pack_name not in store.get_trusted_packs():
                return False

            # F-10: user trust is bound to the pack's content hash. If the tree
            # has changed since approval, treat it as untrusted.
            content_sha256 = ""
            if pack_dir is not None:
                content_sha256 = MarkerFileManager().calculate_checksum(Path(pack_dir))
            return store.is_trusted_pack(pack_name, content_sha256=content_sha256)
        except Exception:
            return False

    def validate_path(self, path: Path) -> bool:
        try:
            self._validate_path(Path(path))
            return True
        except (PathTraversalError, ValueError):
            return False

    def _validate_path(self, path: Path) -> None:
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
        if not self._strict_mode:
            # Non-strict mode: only critical/high are unsafe
            return risk_level in (ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM)
        else:
            # Strict mode: any threat is unsafe
            return risk_level == ThreatLevel.SAFE

    def _risk_level_from_scan(self, scan_risk: Any) -> ThreatLevel:
        from vibesop.security.rules import RiskLevel

        mapping = {
            RiskLevel.CRITICAL: ThreatLevel.CRITICAL,
            RiskLevel.HIGH: ThreatLevel.HIGH,
            RiskLevel.MEDIUM: ThreatLevel.MEDIUM,
            RiskLevel.LOW: ThreatLevel.LOW,
        }
        return mapping.get(scan_risk, ThreatLevel.MEDIUM)

    def add_threat_pattern(self, pattern: ThreatPattern) -> None:
        # Instance-local, not the shared ClassVar — adding a pattern on one
        # auditor must not leak into other instances' scans.
        self._custom_threat_patterns.append(pattern)

    def add_allowed_path(self, path: Path | str) -> None:
        self._allowed_paths.append(Path(path).resolve())

    def get_allowed_paths(self) -> list[Path]:
        return self._allowed_paths.copy()


# Convenience functions


def audit_skill(
    skill_path: Path | str,
    strict_mode: bool = True,
    project_root: Path | str | None = None,
) -> AuditResult:
    auditor = SkillSecurityAuditor(
        strict_mode=strict_mode,
        project_root=project_root or Path.cwd(),
    )
    return auditor.audit_skill_file(Path(skill_path))


__all__ = [
    "AuditResult",
    "PackAuditResult",
    "SkillSecurityAuditor",
    "ThreatLevel",
    "ThreatPattern",
    "audit_skill",
]
