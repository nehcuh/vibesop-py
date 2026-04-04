"""Shared fixtures for trigger tests."""

import pytest
from vibesop.triggers.models import TriggerPattern, PatternCategory


@pytest.fixture
def sample_security_pattern():
    """Create a sample security trigger pattern."""
    return TriggerPattern(
        pattern_id="security/scan",
        name="Security Scan",
        description="Detects security scanning requests",
        category=PatternCategory.SECURITY,
        keywords=["扫描", "scan", "检查", "安全", "漏洞"],
        regex_patterns=[
            r"扫描.*安全",
            r"安全.*检查",
            r"scan.*vulnerability"
        ],
        skill_id="/security/scan",
        workflow_id="security-review",
        priority=100,
        confidence_threshold=0.6,
        examples=[
            "扫描安全漏洞",
            "检查安全问题",
            "scan for vulnerabilities"
        ]
    )


@pytest.fixture
def sample_config_pattern():
    """Create a sample configuration trigger pattern."""
    return TriggerPattern(
        pattern_id="config/deploy",
        name="Config Deploy",
        description="Detects config deployment requests",
        category=PatternCategory.CONFIG,
        keywords=["部署", "deploy", "配置", "config"],
        regex_patterns=[
            r"部署.*配置",
            r"配置.*部署"
        ],
        skill_id="/config/deploy",
        workflow_id="config-deploy",
        priority=90,
        confidence_threshold=0.7,
        examples=[
            "部署配置",
            "deploy config"
        ]
    )


@pytest.fixture
def sample_dev_pattern():
    """Create a sample development trigger pattern."""
    return TriggerPattern(
        pattern_id="dev/test",
        name="Run Tests",
        description="Detects test execution requests",
        category=PatternCategory.DEV,
        keywords=["测试", "test", "运行", "run"],
        regex_patterns=[
            r"运行.*测试",
            r"test.*run"
        ],
        skill_id="/dev/test",
        priority=80,
        confidence_threshold=0.5,
        examples=[
            "运行测试",
            "run tests"
        ]
    )
