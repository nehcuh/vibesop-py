"""Predefined trigger patterns for automatic intent detection.

This module provides a comprehensive library of trigger patterns
covering common development workflows and user intents.

Patterns are organized into 5 categories:
- Security: Security scanning, analysis, threat detection
- Config: Configuration management, deployment, validation
- Dev: Development tasks (build, test, debug, refactor)
- Docs: Documentation generation, formatting, updates
- Project: Project setup, migration, audit
"""

from vibesop.triggers.models import TriggerPattern, PatternCategory


# ============================================================================
# Security Patterns (5 patterns)
# ============================================================================

SECURITY_PATTERNS = [
    TriggerPattern(
        pattern_id="security/scan",
        name="Security Scan",
        description="Detects security scanning and vulnerability detection requests",
        category=PatternCategory.SECURITY,
        keywords=["scan", "scanning", "security", "vulnerability", "漏洞", "扫描"],
        regex_patterns=[
            r"scan.*security",
            r"security.*scan",
            r"扫描.*安全",
            r"安全.*扫描",
            r"vulnerability.*scan",
        ],
        skill_id="/security/scan",
        workflow_id="security-review",
        priority=100,
        confidence_threshold=0.6,
        examples=[
            "scan for security vulnerabilities",
            "扫描安全漏洞",
            "check for security issues",
            "security vulnerability scan",
        ]
    ),
    TriggerPattern(
        pattern_id="security/analyze",
        name="Security Analysis",
        description="Detects security analysis and threat assessment requests",
        category=PatternCategory.SECURITY,
        keywords=["analyze", "analysis", "threat", "assess", "评估", "分析", "威胁"],
        regex_patterns=[
            r"analyze.*security",
            r"security.*analysis",
            r"threat.*assessment",
            r"分析.*安全",
            r"威胁.*评估",
        ],
        skill_id="/security/analyze",
        priority=95,
        confidence_threshold=0.65,
        examples=[
            "analyze security threats",
            "分析安全威胁",
            "assess security risks",
            "threat analysis",
        ]
    ),
    TriggerPattern(
        pattern_id="security/audit",
        name="Security Audit",
        description="Detects security audit and compliance checking requests",
        category=PatternCategory.SECURITY,
        keywords=["audit", "compliance", "check", "review", "审计", "合规", "检查"],
        regex_patterns=[
            r"security.*audit",
            r"compliance.*check",
            r"安全.*审计",
            r"合规.*检查",
        ],
        skill_id="/security/audit",
        priority=90,
        confidence_threshold=0.7,
        examples=[
            "run security audit",
            "安全审计",
            "check compliance",
            "security compliance check",
        ]
    ),
    TriggerPattern(
        pattern_id="security/fix",
        name="Security Fix",
        description="Detects security fix and remediation requests",
        category=PatternCategory.SECURITY,
        keywords=["fix", "patch", "remediate", "repair", "修复", "补丁", "修补"],
        regex_patterns=[
            r"fix.*security",
            r"security.*fix",
            r"patch.*vulnerability",
            r"修复.*安全",
            r"安全.*补丁",
        ],
        skill_id="/security/fix",
        priority=85,
        confidence_threshold=0.6,
        examples=[
            "fix security vulnerabilities",
            "修复安全漏洞",
            "apply security patches",
            "remediate security issues",
        ]
    ),
    TriggerPattern(
        pattern_id="security/report",
        name="Security Report",
        description="Detects security report generation requests",
        category=PatternCategory.SECURITY,
        keywords=["report", "generate", "document", "summary", "报告", "生成", "文档"],
        regex_patterns=[
            r"security.*report",
            r"generate.*security.*report",
            r"安全.*报告",
            r"生成.*安全.*报告",
        ],
        skill_id="/security/report",
        priority=80,
        confidence_threshold=0.65,
        examples=[
            "generate security report",
            "生成安全报告",
            "create security summary",
            "security documentation",
        ]
    ),
]


# ============================================================================
# Config Patterns (5 patterns)
# ============================================================================

CONFIG_PATTERNS = [
    TriggerPattern(
        pattern_id="config/deploy",
        name="Config Deploy",
        description="Detects configuration deployment requests",
        category=PatternCategory.CONFIG,
        keywords=["deploy", "deployment", "apply", "push", "config", "配置", "部署", "应用", "推送"],
        regex_patterns=[
            r"deploy.*config",
            r"config.*deploy",
            r"apply.*config",
            r"部署.*配置",
            r"配置.*部署",
        ],
        skill_id="/config/deploy",
        workflow_id="config-deploy",
        priority=100,
        confidence_threshold=0.6,
        examples=[
            "deploy configuration",
            "部署配置",
            "apply config changes",
            "push configuration to production",
        ]
    ),
    TriggerPattern(
        pattern_id="config/validate",
        name="Config Validate",
        description="Detects configuration validation requests",
        category=PatternCategory.CONFIG,
        keywords=["validate", "validation", "check", "verify", "验证", "检查", "校验"],
        regex_patterns=[
            r"validate.*config",
            r"config.*validation",
            r"verify.*config",
            r"验证.*配置",
            r"配置.*验证",
        ],
        skill_id="/config/validate",
        priority=95,
        confidence_threshold=0.65,
        examples=[
            "validate configuration",
            "验证配置",
            "check configuration validity",
            "verify config syntax",
        ]
    ),
    TriggerPattern(
        pattern_id="config/render",
        name="Config Render",
        description="Detects configuration rendering requests",
        category=PatternCategory.CONFIG,
        keywords=["render", "generate", "template", "compile", "渲染", "生成", "编译"],
        regex_patterns=[
            r"render.*config",
            r"generate.*config.*from.*template",
            r"config.*template",
            r"渲染.*配置",
            r"配置.*模板",
        ],
        skill_id="/config/render",
        priority=90,
        confidence_threshold=0.65,
        examples=[
            "render configuration from template",
            "渲染配置",
            "generate config files",
            "compile configuration",
        ]
    ),
    TriggerPattern(
        pattern_id="config/diff",
        name="Config Diff",
        description="Detects configuration comparison requests",
        category=PatternCategory.CONFIG,
        keywords=["diff", "compare", "difference", "change", "差异", "比较", "对比"],
        regex_patterns=[
            r"config.*diff",
            r"compare.*config",
            r"diff.*configuration",
            r"配置.*差异",
            r"比较.*配置",
        ],
        skill_id="/config/diff",
        priority=85,
        confidence_threshold=0.6,
        examples=[
            "compare configurations",
            "比较配置",
            "show config differences",
            "diff config files",
        ]
    ),
    TriggerPattern(
        pattern_id="config/backup",
        name="Config Backup",
        description="Detects configuration backup requests",
        category=PatternCategory.CONFIG,
        keywords=["backup", "save", "archive", "snapshot", "备份", "保存", "归档"],
        regex_patterns=[
            r"backup.*config",
            r"save.*config",
            r"config.*backup",
            r"备份.*配置",
            r"配置.*备份",
        ],
        skill_id="/config/backup",
        priority=80,
        confidence_threshold=0.6,
        examples=[
            "backup configuration",
            "备份配置",
            "save config snapshot",
            "archive config files",
        ]
    ),
]


# ============================================================================
# Development Patterns (8 patterns)
# ============================================================================

DEV_PATTERNS = [
    TriggerPattern(
        pattern_id="dev/build",
        name="Build Project",
        description="Detects build and compilation requests",
        category=PatternCategory.DEV,
        keywords=["build", "compile", "make", "construct", "构建", "编译", "制造"],
        regex_patterns=[
            r"build.*project",
            r"compile.*code",
            r"make.*build",
            r"构建.*项目",
            r"编译.*代码",
        ],
        skill_id="/dev/build",
        priority=100,
        confidence_threshold=0.6,
        examples=[
            "build the project",
            "构建项目",
            "compile the code",
            "run build",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/test",
        name="Run Tests",
        description="Detects test execution requests",
        category=PatternCategory.DEV,
        keywords=["test", "testing", "run.*test", "execute.*test", "测试", "运行"],
        regex_patterns=[
            r"run.*tests?",
            r"execute.*tests?",
            r"test.*suite",
            r"运行.*测试",
            r"执行.*测试",
        ],
        skill_id="/dev/test",
        priority=100,
        confidence_threshold=0.5,
        examples=[
            "run tests",
            "运行测试",
            "execute test suite",
            "run unit tests",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/debug",
        name="Debug Code",
        description="Detects debugging and troubleshooting requests",
        category=PatternCategory.DEV,
        keywords=["debug", "debugging", "troubleshoot", "fix.*bug", "调试", "故障", "排错"],
        regex_patterns=[
            r"debug.*code",
            r"troubleshoot",
            r"fix.*bug",
            r"调试.*代码",
            r"排查.*故障",
        ],
        skill_id="/dev/debug",
        priority=95,
        confidence_threshold=0.6,
        examples=[
            "debug the code",
            "调试代码",
            "troubleshoot issue",
            "find and fix bugs",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/refactor",
        name="Refactor Code",
        description="Detects code refactoring requests",
        category=PatternCategory.DEV,
        keywords=["refactor", "restructure", "reorganize", "clean.*up", "重构", "重组", "清理"],
        regex_patterns=[
            r"refactor.*code",
            r"restructure.*code",
            r"clean.*up.*code",
            r"重构.*代码",
            r"重组.*代码",
        ],
        skill_id="/dev/refactor",
        priority=90,
        confidence_threshold=0.65,
        examples=[
            "refactor the code",
            "重构代码",
            "clean up code",
            "restructure project",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/lint",
        name="Lint Code",
        description="Detects code linting and quality check requests",
        category=PatternCategory.DEV,
        keywords=["lint", "linter", "quality", "check.*style", "检查", "代码质量", "风格"],
        regex_patterns=[
            r"run.*lint",
            r"lint.*code",
            r"check.*code.*quality",
            r"代码.*检查",
            r"代码.*质量",
        ],
        skill_id="/dev/lint",
        priority=85,
        confidence_threshold=0.6,
        examples=[
            "run linter",
            "lint the code",
            "check code quality",
            "run style checks",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/format",
        name="Format Code",
        description="Detects code formatting requests",
        category=PatternCategory.DEV,
        keywords=["format", "formatter", "style", "prettier", "格式化", "格式", "美化"],
        regex_patterns=[
            r"format.*code",
            r"apply.*formatter",
            r"代码.*格式化",
            r"格式.*代码",
        ],
        skill_id="/dev/format",
        priority=80,
        confidence_threshold=0.6,
        examples=[
            "format the code",
            "格式化代码",
            "apply code formatter",
            "prettify code",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/install",
        name="Install Dependencies",
        description="Detects dependency installation requests",
        category=PatternCategory.DEV,
        keywords=["install", "dependency", "dependencies", "package", "安装", "依赖", "包"],
        regex_patterns=[
            r"install.*dependencies?",
            r"install.*packages?",
            r"安装.*依赖",
            r"依赖.*安装",
        ],
        skill_id="/dev/install",
        priority=90,
        confidence_threshold=0.6,
        examples=[
            "install dependencies",
            "安装依赖",
            "install packages",
            "setup dependencies",
        ]
    ),
    TriggerPattern(
        pattern_id="dev/clean",
        name="Clean Build",
        description="Detects build cleanup requests",
        category=PatternCategory.DEV,
        keywords=["clean", "clear", "purge", "remove.*build", "清理", "清除", "删除"],
        regex_patterns=[
            r"clean.*build",
            r"clear.*cache",
            r"remove.*artifacts",
            r"清理.*构建",
            r"清除.*缓存",
        ],
        skill_id="/dev/clean",
        priority=75,
        confidence_threshold=0.6,
        examples=[
            "clean build artifacts",
            "清理构建",
            "clear cache",
            "remove build files",
        ]
    ),
]


# ============================================================================
# Documentation Patterns (6 patterns)
# ============================================================================

DOCS_PATTERNS = [
    TriggerPattern(
        pattern_id="docs/generate",
        name="Generate Documentation",
        description="Detects documentation generation requests",
        category=PatternCategory.DOCS,
        keywords=["generate", "create", "docs", "documentation", "document", "生成", "创建", "文档"],
        regex_patterns=[
            r"generate.*documentation",
            r"create.*documentation",
            r"document.*the.*code",
            r"生成.*文档",
            r"代码.*文档",
        ],
        skill_id="/docs/generate",
        priority=100,
        confidence_threshold=0.6,
        examples=[
            "generate documentation",
            "生成文档",
            "create docs from code",
            "document this project",
        ]
    ),
    TriggerPattern(
        pattern_id="docs/update",
        name="Update Documentation",
        description="Detects documentation update requests",
        category=PatternCategory.DOCS,
        keywords=["update.*docs", "refresh.*docs", "modify.*docs", "更新.*文档", "刷新.*文档"],
        regex_patterns=[
            r"update.*documentation",
            r"refresh.*docs",
            r"文档.*更新",
            r"更新.*文档",
        ],
        skill_id="/docs/update",
        priority=95,
        confidence_threshold=0.6,
        examples=[
            "update documentation",
            "更新文档",
            "refresh docs",
            "update outdated docs",
        ]
    ),
    TriggerPattern(
        pattern_id="docs/format",
        name="Format Documentation",
        description="Detects documentation formatting requests",
        category=PatternCategory.DOCS,
        keywords=["format.*docs", "style.*docs", "prettify.*docs", "格式化.*文档", "文档.*格式"],
        regex_patterns=[
            r"format.*documentation",
            r"apply.*doc.*format",
            r"文档.*格式化",
        ],
        skill_id="/docs/format",
        priority=85,
        confidence_threshold=0.6,
        examples=[
            "format documentation",
            "格式化文档",
            "apply doc formatting",
            "style the docs",
        ]
    ),
    TriggerPattern(
        pattern_id="docs/readme",
        name="Generate README",
        description="Detects README generation requests",
        category=PatternCategory.DOCS,
        keywords=["readme", "read.*me", "create.*readme", "generate.*readme"],
        regex_patterns=[
            r"generate.*readme",
            r"create.*readme",
            r"update.*readme",
        ],
        skill_id="/docs/readme",
        priority=90,
        confidence_threshold=0.65,
        examples=[
            "generate README",
            "create README file",
            "update README",
            "generate read me",
        ]
    ),
    TriggerPattern(
        pattern_id="docs/api",
        name="API Documentation",
        description="Detects API documentation requests",
        category=PatternCategory.DOCS,
        keywords=["api.*doc", "api.*reference", "swagger", "openapi", "API文档", "接口文档"],
        regex_patterns=[
            r"generate.*api.*docs",
            r"create.*api.*reference",
            r"API.*文档",
        ],
        skill_id="/docs/api",
        priority=85,
        confidence_threshold=0.7,
        examples=[
            "generate API documentation",
            "生成API文档",
            "create API reference",
            "generate swagger docs",
        ]
    ),
    TriggerPattern(
        pattern_id="docs/changelog",
        name="Generate Changelog",
        description="Detects changelog generation requests",
        category=PatternCategory.DOCS,
        keywords=["changelog", "change.*log", "release.*notes", "version.*history", "变更日志"],
        regex_patterns=[
            r"generate.*changelog",
            r"create.*changelog",
            r"update.*changelog",
            r"变更.*日志",
        ],
        skill_id="/docs/changelog",
        priority=80,
        confidence_threshold=0.65,
        examples=[
            "generate changelog",
            "生成变更日志",
            "create release notes",
            "update version history",
        ]
    ),
]


# ============================================================================
# Project Patterns (6 patterns)
# ============================================================================

PROJECT_PATTERNS = [
    TriggerPattern(
        pattern_id="project/init",
        name="Initialize Project",
        description="Detects project initialization requests",
        category=PatternCategory.PROJECT,
        keywords=["init", "initialize", "create.*project", "setup.*project", "初始化", "创建.*项目"],
        regex_patterns=[
            r"initialize.*project",
            r"create.*new.*project",
            r"setup.*project",
            r"初始化.*项目",
            r"创建.*项目",
        ],
        skill_id="/project/init",
        priority=100,
        confidence_threshold=0.65,
        examples=[
            "initialize new project",
            "初始化项目",
            "create a new project",
            "setup project structure",
        ]
    ),
    TriggerPattern(
        pattern_id="project/migrate",
        name="Migrate Project",
        description="Detects project migration requests",
        category=PatternCategory.PROJECT,
        keywords=["migrate", "migration", "move.*project", "transfer", "迁移", "转移", "搬家"],
        regex_patterns=[
            r"migrate.*project",
            r"project.*migration",
            r"迁移.*项目",
            r"项目.*迁移",
        ],
        skill_id="/project/migrate",
        priority=95,
        confidence_threshold=0.65,
        examples=[
            "migrate project",
            "迁移项目",
            "move project to new location",
            "project migration",
        ]
    ),
    TriggerPattern(
        pattern_id="project/audit",
        name="Audit Project",
        description="Detects project audit requests",
        category=PatternCategory.PROJECT,
        keywords=["audit", "review.*project", "assess.*project", "evaluate", "审计", "评估", "审查"],
        regex_patterns=[
            r"audit.*project",
            r"project.*audit",
            r"review.*project",
            r"项目.*审计",
            r"审计.*项目",
        ],
        skill_id="/project/audit",
        priority=90,
        confidence_threshold=0.65,
        examples=[
            "audit project",
            "审计项目",
            "review project structure",
            "assess project health",
        ]
    ),
    TriggerPattern(
        pattern_id="project/upgrade",
        name="Upgrade Project",
        description="Detects project upgrade requests",
        category=PatternCategory.PROJECT,
        keywords=["upgrade", "update.*version", "bump.*version", "升级", "更新版本"],
        regex_patterns=[
            r"upgrade.*project",
            r"update.*project.*version",
            r"项目.*升级",
            r"升级.*项目",
        ],
        skill_id="/project/upgrade",
        priority=85,
        confidence_threshold=0.6,
        examples=[
            "upgrade project",
            "升级项目",
            "update project version",
            "bump version",
        ]
    ),
    TriggerPattern(
        pattern_id="project/clean",
        name="Clean Project",
        description="Detects project cleanup requests",
        category=PatternCategory.PROJECT,
        keywords=["clean.*project", "purge.*project", "remove.*unused", "清理.*项目", "清理"],
        regex_patterns=[
            r"clean.*project",
            r"purge.*project",
            r"remove.*unused.*files",
            r"清理.*项目",
        ],
        skill_id="/project/clean",
        priority=80,
        confidence_threshold=0.6,
        examples=[
            "clean project",
            "清理项目",
            "remove unused files",
            "purge project artifacts",
        ]
    ),
    TriggerPattern(
        pattern_id="project/status",
        name="Project Status",
        description="Detects project status check requests",
        category=PatternCategory.PROJECT,
        keywords=["status", "check.*status", "project.*health", "info", "状态", "健康", "信息"],
        regex_patterns=[
            r"check.*project.*status",
            r"project.*health",
            r"project.*info",
            r"项目.*状态",
            r"检查.*状态",
        ],
        skill_id="/project/status",
        priority=85,
        confidence_threshold=0.6,
        examples=[
            "check project status",
            "检查项目状态",
            "project health check",
            "get project info",
        ]
    ),
]


# ============================================================================
# Default Patterns Library
# ============================================================================

DEFAULT_PATTERNS = (
    SECURITY_PATTERNS +
    CONFIG_PATTERNS +
    DEV_PATTERNS +
    DOCS_PATTERNS +
    PROJECT_PATTERNS
)

"""Default trigger patterns library.

Contains 30 predefined patterns covering common development workflows.
- 5 Security patterns
- 5 Config patterns
- 8 Dev patterns
- 6 Docs patterns
- 6 Project patterns

Usage:
    >>> from vibesop.triggers import DEFAULT_PATTERNS, KeywordDetector
    >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    >>> match = detector.detect_best("scan for security vulnerabilities")
    >>> print(match.pattern_id)  # "security/scan"
"""

__all__ = [
    "SECURITY_PATTERNS",
    "CONFIG_PATTERNS",
    "DEV_PATTERNS",
    "DOCS_PATTERNS",
    "PROJECT_PATTERNS",
    "DEFAULT_PATTERNS",
]
