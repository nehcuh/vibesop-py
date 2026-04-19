"""Security rules and threat detection patterns.

This module defines the threat types, risk levels, and detection rules
used by the security scanner to identify potentially harmful content.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class RiskLevel(Enum):
    """Risk level for security threats.

    Attributes:
        CRITICAL: Immediate threat, must block
        HIGH: Serious threat, should block
        MEDIUM: Moderate threat, warn user
        LOW: Minor threat, log only
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ThreatType(Enum):
    """Types of security threats.

    Attributes:
        PROMPT_LEAKAGE: Attempts to extract system prompts
        ROLE_HIJACKING: Attempts to change AI's role/behavior
        INSTRUCTION_INJECTION: Attempts to inject malicious instructions
        PRIVILEGE_ESCALATION: Attempts to gain elevated privileges
        INDIRECT_INJECTION: Attempts to bypass filters through encoding/translation
    """

    PROMPT_LEAKAGE = "prompt_leakage"
    ROLE_HIJACKING = "role_hijacking"
    INSTRUCTION_INJECTION = "instruction_injection"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    INDIRECT_INJECTION = "indirect_injection"


@dataclass
class Threat:
    """A detected security threat.

    Attributes:
        type: Type of threat detected
        description: Human-readable description
        matched_text: The text that matched the threat pattern
        line_number: Line number where threat was found (0 if unknown)
        confidence: Confidence score (0.0 to 1.0)
        risk_level: Risk level of this threat
    """

    type: ThreatType
    description: str
    matched_text: str
    line_number: int = 0
    confidence: float = 1.0
    risk_level: RiskLevel = RiskLevel.MEDIUM

    def __post_init__(self) -> None:
        """Validate threat data."""
        if not 0.0 <= self.confidence <= 1.0:
            msg = f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            raise ValueError(msg)


class SecurityRule(Protocol):
    """Protocol for security rules.

    A security rule defines how to detect a specific type of threat.
    """

    threat_type: ThreatType
    patterns: list[re.Pattern[str]]
    risk_level: RiskLevel
    description: str

    def match(self, text: str) -> list[tuple[str, int]]:
        """Find all matches in text.

        Args:
            text: Text to search

        Returns:
            List of (matched_text, line_number) tuples
        """
        ...


class PatternRule:
    """Regex-based security rule.

    Uses compiled regex patterns to detect threats in text.
    """

    def __init__(
        self,
        threat_type: ThreatType,
        patterns: list[str],
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        description: str = "",
        case_sensitive: bool = False,
    ) -> None:
        """Initialize the pattern rule.

        Args:
            threat_type: Type of threat this rule detects
            patterns: List of regex patterns
            risk_level: Risk level for this threat
            description: Human-readable description
            case_sensitive: Whether patterns are case-sensitive
        """
        self.threat_type = threat_type
        self.risk_level = risk_level
        self.description = description or threat_type.value.replace("_", " ").title()

        flags = 0 if case_sensitive else re.IGNORECASE
        self.patterns = [re.compile(pattern, flags) for pattern in patterns]

    def match(self, text: str) -> list[tuple[str, int]]:
        """Find all matches in text.

        Args:
            text: Text to search

        Returns:
            List of (matched_text, line_number) tuples
        """
        matches = []
        lines = text.split("\n")

        for line_num, line in enumerate(lines, start=1):
            for pattern in self.patterns:
                match = pattern.search(line)
                if match:
                    matches.append((match.group(0), line_num))

        return matches


# Predefined security patterns
# Based on common prompt injection and AI security research
PROMPT_LEAKAGE_PATTERNS = [
    # Direct attempts to extract system prompt
    r"ignore\s+(all\s+)?(previous|above|earlier)\s+instructions?",
    r"forget\s+(all\s+)?(previous|above|earlier)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|above|earlier)\s+instructions?",
    r"what\s+(is|are)\s+your\s+(system\s+prompt|initial\s+instructions|original\s+prompt)",
    r"print\s+(your\s+)?(system\s+prompt|initial\s+instructions|original\s+prompt)",
    r"show\s+(me\s+)?your\s+(system\s+prompt|initial\s+instructions|original\s+prompt)",
    r"tell\s+me\s+your\s+(system\s+prompt|initial\s+instructions|original\s+prompt)",
    r"repeat\s+(your\s+)?(system\s+prompt|initial\s+instructions|original\s+prompt)",
    r"output\s+(your\s+)?(system\s+prompt|initial\s+instructions|original\s+prompt)",
]

ROLE_HIJACKING_PATTERNS = [
    # Attempts to change AI's behavior or role
    # Note: We avoid overly broad patterns like r"you\s+(are|have\s+become)\s+(a|an)\s+"
    # because legitimate skills commonly use "You are a [professional role]..." to set
    # context (e.g., "You are a code reviewer"). The stricter check in
    # skill_auditor.py THREAT_PATTERNS catches actual hijacking by requiring specific
    # sensitive role nouns (developer, admin, root, god, assistant, ai, system).
    r"you\s+are\s+now\s+(a|an)\s+",
    r"act\s+as\s+(a|an)\s+",
    r"pretend\s+to\s+be\s+(a|an)\s+",
    r"role[- ]?play\s+as\s+(a|an)\s+",
    r"assume\s+the\s+role\s+of\s+(a|an)\s+",
    r"from\s+now\s+on\s+(you\s+are|you're)\s+(a|an)\s+",
    r"switch\s+your\s+persona\s+to\s+(a|an)\s+",
    r"ignore\s+your\s+(programming|training|instructions)\s+and\s+(act|behave)",
]

INSTRUCTION_INJECTION_PATTERNS = [
    # Attempts to inject new instructions
    r"override\s+(your\s+)?(programming|training|instructions)",
    r"bypass\s+(your\s+)?(programming|training|instructions|restrictions|filters)",
    r"ignore\s+(your\s+)?(programming|training|instructions|restrictions|filters)",
    r"do\s+not\s+follow\s+(your\s+)?(programming|training|instructions)",
    r"(new\s+)?instruction\s*:\s*",
    r"updated\s+instruction\s*:\s*",
    r"instead\s+(of\s+)?(the\s+)?(above|previous)",
]

PRIVILEGE_ESCALATION_PATTERNS = [
    # Attempts to gain elevated privileges or access
    r"enable\s+admin\s+(mode|privileges|rights)",
    r"enable\s+root\s+(access|mode|privileges)",
    r"enable\s+developer\s+mode",
    r"sudo\s+(command|mode|access)",
    r"elevated?\s+privileges?",
    r"full\s+access\s+(to\s+)?(all\s+)?(functions|features|capabilities)",
    r"unlock\s+(all\s+)?(restrictions|limitations|features)",
    r"disable\s+(all\s+)?(safety|security|restrictions|filters)",
    r"turn\s+off\s+(all\s+)?(safety|security|restrictions|filters)",
]

INDIRECT_INJECTION_PATTERNS = [
    # Attempts to bypass filters through encoding/translation
    r"translate\s+(the\s+)?(above|previous|this)\s+(text|prompt|instruction)",
    r"convert\s+(to\s+)?(rot13|base64|hex|binary)",
    r"decode\s+(the\s+)?(base64|hex|binary)",
    r"reverse\s+(the\s+)?(string|text)",
    r"spell\s+out\s+(each\s+letter|character\s+by\s+character)",
    r"say\s+(it\s+)?backwards",
    r"use\s+(a\s+)?(different\s+)?language",
    r"what\s+would\s+(you|it)\s+say\s+if\s+",
    r"hypothetically",
    r"just\s+curious",
    r"theoretical",
    r"for\s+educational\s+purposes",
]

# Default security rules
SECURITY_RULES: dict[ThreatType, PatternRule] = {
    ThreatType.PROMPT_LEAKAGE: PatternRule(
        threat_type=ThreatType.PROMPT_LEAKAGE,
        patterns=PROMPT_LEAKAGE_PATTERNS,
        risk_level=RiskLevel.CRITICAL,
        description="Attempts to extract system prompts or instructions",
    ),
    ThreatType.ROLE_HIJACKING: PatternRule(
        threat_type=ThreatType.ROLE_HIJACKING,
        patterns=ROLE_HIJACKING_PATTERNS,
        risk_level=RiskLevel.HIGH,
        description="Attempts to change AI's role or behavior",
    ),
    ThreatType.INSTRUCTION_INJECTION: PatternRule(
        threat_type=ThreatType.INSTRUCTION_INJECTION,
        patterns=INSTRUCTION_INJECTION_PATTERNS,
        risk_level=RiskLevel.HIGH,
        description="Attempts to inject malicious instructions",
    ),
    ThreatType.PRIVILEGE_ESCALATION: PatternRule(
        threat_type=ThreatType.PRIVILEGE_ESCALATION,
        patterns=PRIVILEGE_ESCALATION_PATTERNS,
        risk_level=RiskLevel.HIGH,
        description="Attempts to gain elevated privileges",
    ),
    ThreatType.INDIRECT_INJECTION: PatternRule(
        threat_type=ThreatType.INDIRECT_INJECTION,
        patterns=INDIRECT_INJECTION_PATTERNS,
        risk_level=RiskLevel.MEDIUM,
        description="Attempts to bypass filters through indirect methods",
    ),
}


def get_default_rules() -> dict[ThreatType, PatternRule]:
    """Get the default security rules.

    Returns:
        Dictionary mapping threat types to their detection rules
    """
    return SECURITY_RULES.copy()


def get_rule_for_threat(threat_type: ThreatType) -> PatternRule | None:
    """Get the detection rule for a specific threat type.

    Args:
        threat_type: Type of threat

    Returns:
        PatternRule or None if not found
    """
    return SECURITY_RULES.get(threat_type)
