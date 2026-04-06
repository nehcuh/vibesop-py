"""Tiered verification for ralph loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VerificationTier(str, Enum):
    SELF_REVIEW = "self_review"
    ARCHITECTURE_CHECK = "architecture_check"
    FULL_REVIEW = "full_review"


@dataclass
class VerificationResult:
    """Result of a verification check."""

    passed: bool
    tier: VerificationTier
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.passed and not self.errors


def determine_tier(lines_changed: int) -> VerificationTier:
    """Determine verification tier based on change size."""
    if lines_changed < 50:
        return VerificationTier.SELF_REVIEW
    if lines_changed < 200:
        return VerificationTier.ARCHITECTURE_CHECK
    return VerificationTier.FULL_REVIEW


def run_verification(
    tier: VerificationTier,
    project_root: str = ".",
) -> VerificationResult:
    """Run verification checks at the given tier.

    All tiers run: tests, build, lint.
    Higher tiers add: type checking, architecture review.
    """
    import subprocess

    checks: dict[str, bool] = {}
    errors: list[str] = []
    warnings: list[str] = []

    # All tiers: run tests
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "tests/", "-x", "-q", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=120,
        )
        checks["tests"] = result.returncode == 0
        if not checks["tests"]:
            errors.append(f"Tests failed: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        checks["tests"] = False
        errors.append("Tests timed out")

    # All tiers: run lint
    try:
        result = subprocess.run(
            ["uv", "run", "ruff", "check", "src/"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=60,
        )
        checks["lint"] = result.returncode == 0
        if not checks["lint"]:
            warnings.append(f"Lint issues: {result.stdout[:300]}")
    except subprocess.TimeoutExpired:
        checks["lint"] = False
        warnings.append("Lint timed out")

    # Higher tiers: type check
    if tier in (VerificationTier.ARCHITECTURE_CHECK, VerificationTier.FULL_REVIEW):
        try:
            result = subprocess.run(
                ["uv", "run", "basedpyright", "src/"],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=120,
            )
            checks["type_check"] = result.returncode == 0
            if not checks["type_check"]:
                errors.append(f"Type errors: {result.stderr[:500]}")
        except subprocess.TimeoutExpired:
            checks["type_check"] = False
            errors.append("Type check timed out")

    passed = all(checks.values())
    return VerificationResult(
        passed=passed,
        tier=tier,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )
