"""VibeSOP-Py Intelligent Keyword Trigger System.

This module provides automatic keyword detection and intent recognition
for triggering workflows and skills based on natural language input.

Example:
    >>> from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS
    >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    >>> match = detector.detect_best("扫描安全漏洞")
    >>> print(match.pattern_id)  # "security/scan"
    >>> print(match.confidence)  # 0.95
"""

from vibesop.triggers.models import (
    TriggerPattern,
    PatternMatch,
    PatternCategory,
)
from vibesop.triggers.detector import KeywordDetector
from vibesop.triggers.patterns import DEFAULT_PATTERNS
from vibesop.triggers.activator import SkillActivator, auto_activate

__all__ = [
    "TriggerPattern",
    "PatternMatch",
    "PatternCategory",
    "KeywordDetector",
    "DEFAULT_PATTERNS",
    "SkillActivator",
    "auto_activate",
]

# Version info
__version__ = "2.0.0"
